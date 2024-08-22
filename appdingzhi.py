import datetime
import logging
import re
import threading
import time
import sys
from flask import Flask, request, render_template, jsonify, send_file, send_from_directory
import os
from gevent.pywsgi import WSGIServer, WSGIHandler
import glob
import hashlib
from logging.handlers import RotatingFileHandler

import clone
from clone import cfg
from clone.cfg import ROOT_DIR, TTS_DIR, VOICE_MODEL_EXITS, TMP_DIR, VOICE_DIR, TEXT_MODEL_EXITS, langlist
from clone.logic import ttsloop, stsloop, create_tts, openweb, merge_audio_segments, get_subtitle_from_srt, updatecache
from clone import logic
from gevent.pywsgi import LoggingLogAdapter
import shutil
import subprocess
from dotenv import load_dotenv

load_dotenv()

web_address = os.getenv('WEB_ADDRESS', '127.0.0.1:9988')


class CustomRequestHandler(WSGIHandler):
    def log_request(self):
        pass


#updatecache()

# 配置日志
# 禁用 Werkzeug 默认的日志处理器
log = logging.getLogger('werkzeug')
log.handlers[:] = []
log.setLevel(logging.WARNING)

app = Flask(__name__, static_folder=os.path.join(ROOT_DIR, 'static'), static_url_path='/static',
            template_folder=os.path.join(ROOT_DIR, 'templates'))

root_log = logging.getLogger()  # Flask的根日志记录器
root_log.handlers = []
root_log.setLevel(logging.WARNING)

app.logger.setLevel(logging.INFO)  # 设置日志级别为 INFO
# 创建 RotatingFileHandler 对象，设置写入的文件路径和大小限制
file_handler = RotatingFileHandler(os.path.join(ROOT_DIR, 'app.log'), maxBytes=1024 * 1024, backupCount=5)
# 创建日志的格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# 设置文件处理器的级别和格式
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)
# 将文件处理器添加到日志记录器中
app.logger.addHandler(file_handler)


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.config['STATIC_FOLDER'], filename)


@app.route('/')
def index():
    return render_template("index.html",
                           text_model=TEXT_MODEL_EXITS,
                           voice_model=VOICE_MODEL_EXITS,
                           version=clone.ver,
                           language=cfg.LANG,
                           root_dir=ROOT_DIR.replace('\\', '/'))

@app.route('/txt')
def txt():
    return render_template("txt.html",
                           text_model=True,#TEXT_MODEL_EXITS,
                           version=clone.ver,
                           language=cfg.LANG,
                           root_dir=ROOT_DIR.replace('\\', '/'))



# 上传音频
@app.route('/upload', methods=['POST'])
def upload():
    try:
        # 获取上传的文件
        audio_file = request.files['audio']
        save_dir = request.form.get("save_dir")
        save_dir = VOICE_DIR if not save_dir else os.path.join(ROOT_DIR, f'static/{save_dir}')
        app.logger.info(f"[upload]{audio_file.filename=},{save_dir=}")
        # 检查文件是否存在且是 WAV/mp3格式
        noextname, ext = os.path.splitext(os.path.basename(audio_file.filename.lower()))
        noextname = noextname.replace(' ', '')
        if audio_file and ext in [".wav", ".mp3", ".flac"]:
            # 保存文件到服务器指定目录
            name = f'{noextname}{ext}'
            if os.path.exists(os.path.join(save_dir, f'{noextname}{ext}')):
                name = f'{datetime.datetime.now().strftime("%m%d-%H%M%S")}-{noextname}{ext}'
            # mp3 or wav           
            tmp_wav = os.path.join(TMP_DIR, "tmp_" + name)
            audio_file.save(tmp_wav)
            # save to wav
            if ext != '.wav':
                name = f"{name[:-len(ext)]}.wav"
            savename = os.path.join(save_dir, name)
            subprocess.run(['ffmpeg', '-hide_banner', '-y', '-i', tmp_wav, savename], check=True)
            try:
                os.unlink(tmp_wav)
            except:
                pass
            # 返回成功的响应
            return jsonify({'code': 0, 'msg': 'ok', "data": name})
        else:
            # 返回错误的响应
            return jsonify({'code': 1, 'msg': 'not wav'})
    except Exception as e:
        app.logger.error(f'[upload]error: {e}')
        return jsonify({'code': 2, 'msg': 'error'})


# 从 voicelist 目录获取可用的 wav 声音列表
@app.route('/init')
def init():
    wavs = glob.glob(f"{VOICE_DIR}/*.wav")
    result = []
    for it in wavs:
        if os.path.getsize(it) > 0:
            result.append(os.path.basename(it))
    return jsonify(result)


# 判断线程是否启动
@app.route('/isstart', methods=['GET', 'POST'])
def isstart():
    total = cfg.tts_n + cfg.sts_n
    return jsonify({"code": 0, "msg": total, "tts": cfg.langlist['lang15'] if cfg.tts_n < 1 else "",
                    "sts": cfg.langlist['lang16'] if cfg.sts_n < 1 else ""})


# 外部接口
@app.route('/apitts', methods=['GET', 'POST'])
def apitts():
    '''
    audio:原始声音wav,作为音色克隆源
    voice:已有的声音名字，如果存在 voice则先使用，否则使用audio
    text:文字一行
    language：语言代码
    Returns:
    '''
    try:
        langcodelist=["zh-cn","en","ja","ko","es","de","fr","it","tr","ru","pt","pl","nl","ar","hu","cs"]
        text = request.form.get("text").strip()
        text = text.replace("\n", ' . ')
        language = request.form.get("language","").lower()
        if language.startswith("zh"):
            language="zh-cn"
        if language not in langcodelist:
            return jsonify({"code":1,"msg":f"dont support language {language}"})

        md5_hash = hashlib.md5()

        audio_name = request.form.get('voice')
        # 存在传来的声音文件名字
        if audio_name:
            voicename = os.path.join(VOICE_DIR, audio_name)
        else:  # 获取上传的文件
            audio_file = request.files['audio']
            print(f'{audio_file.filename}')
            # 保存临时上传过来的声音文件
            audio_name = f'video_{audio_file.filename}.wav'
            voicename = os.path.join(TMP_DIR, audio_name)
            audio_file.save(voicename)
        md5_hash.update(f"{text}-{language}-{audio_name}".encode('utf-8'))

        app.logger.info(f"[apitts]{voicename=}")
        if re.match(r'^[~`!@#$%^&*()_+=,./;\':\[\]{}<>?\\|"，。？；‘：“”’｛【】｝！·￥、\s\n\r -]*$', text):
            return jsonify({"code": 1, "msg": "lost text for translate"})
        if not text or not language:
            return jsonify({"code": 1, "msg": "text & language params lost"})
        app.logger.info(f"[apitts]{text=},{language=}")

        # 存放结果
        # 合成后的语音文件, 以wav格式存放和返回
        filename = md5_hash.hexdigest() + ".wav"
        app.logger.info(f"[apitts]{filename=}")
        # 合成语音
        rs = create_tts(text=text, speed=1.0, voice=voicename, language=language, filename=filename)
        # 已有结果或错误，直接返回
        if rs is not None:
            result = rs
        else:
            # 循环等待 最多7200s
            time_tmp = 0
            while filename not in cfg.global_tts_result:
                time.sleep(3)
                time_tmp += 3
                if time_tmp % 30 == 0:
                    app.logger.info(f"[apitts][tts]{time_tmp=},{filename=}")

            # 当前行已完成合成
            if cfg.global_tts_result[filename] != 1:
                msg = {"code": 1, "msg": cfg.global_tts_result[filename]}
            else:
                target_wav = os.path.normpath(os.path.join(TTS_DIR, filename))
                msg = {"code": 0, "filename": target_wav, 'name': filename}
            app.logger.info(f"[apitts][tts] {filename=},{msg=}")
            cfg.global_tts_result.pop(filename)
            result = msg
            app.logger.info(f"[apitts]{msg=}")
        if result['code'] == 0:
            result['url'] = f'http://{web_address}/static/ttslist/{filename}'
        return jsonify(result)
    except Exception as e:
        msg=f'{str(e)} {str(e.args)}'
        app.logger.error(f"[apitts]{msg}")
        return jsonify({'code': 2, 'msg': msg})

chuliing={"name":"","line":0,"end":False}

# 获取进度
@app.route('/ttslistjindu',methods=['GET', 'POST'])
def ttslistjindu():
    return jsonify(chuliing)

# 具体起一个新线程执行
def detail_task(*pams):
    global chuliing
    chuliing={"name":"","line":0,"end":False}
    voice, src, dst, speed, language=pams
  
    # 遍历所有txt文件
    for t in os.listdir(src):
        if not t.lower().endswith('.txt'):
            continue
        concat_txt=os.path.join(cfg.TTS_DIR, re.sub(r'[ \s\[\]\{\}\(\)<>\?\, :]+','', t, re.I) + '.txt')
        
        app.logger.info(f'####开始处理文件：{t}, 每行结果保存在:{concat_txt}')
        with open(concat_txt,'w',encoding='utf-8') as f:
            f.write("")
        #需要等待执行完毕的数据 [{}, {}]
        waitlist=[]
        #已执行完毕的 {1:{}, 2:{}}
        result={}
        with open(os.path.join(src,t),'r',encoding='utf-8') as f:
            num=0
            for line in f.readlines():
                num+=1
                line=line.strip()
                if re.match(r'^[~`!@#$%^&*()_+=,./;\':\[\]{}<>?\\|"，。？；‘：“”’｛【】｝！·￥、\s\n\r -]*$', line):
                    app.logger.info(f'\t第{num}不存在有效文字，跳过')
                    continue                
                md5_hash = hashlib.md5()
                md5_hash.update(f"{line}-{voice}-{language}-{speed}".encode('utf-8'))
                filename = md5_hash.hexdigest() + ".wav"
                app.logger.info(f'\t开始合成第{num}行声音:{filename=}')
                # 合成语音
                rs = create_tts(text=line, speed=speed, voice=voice, language=language, filename=filename)
                # 已有结果或错误，直接返回
                if rs is not None and rs['code']==1:
                    app.logger.error(f'\t{t}:文件内容第{num}行【 {line} 】出错了，跳过')
                    continue
                if rs is not None and rs['code']==0:
                    #已存在直接使用
                    result[f'{num}']={"filename":filename, "num":num}
                    chuliing['name']=t
                    chuliing['line']=num
                    app.logger.info(f'\t第{num}行合成完毕:{filename=}')
                    continue
                waitlist.append({"filename":filename, "num":num, "t":t})
        
        #for it in waitlist:
        time_tmp = 0
        chuliing['name']=t
        if len(waitlist)>0:
            chuliing['line']=waitlist[0]['num']
            while len(waitlist)>0:
                it=waitlist.pop(0)
                filename, num, t=it.values()
                
                #需要等待
                if time_tmp>7200:
                    continue
                    
                # 当前行已完成合成
                if filename in cfg.global_tts_result and cfg.global_tts_result[filename] != 1:
                    #出错了
                    app.logger.error(f'\t{t}:文件内容第{num}行出错了,{cfg.global_tts_result[filename]}, 跳过')
                    continue
                if os.path.exists(os.path.join(cfg.TTS_DIR, filename)):
                    chuliing['name']=t
                    chuliing['line']=num
                    app.logger.info(f'\t第{num}行合成完毕:{filename}')
                    #成功了
                    result[f'{num}']={"filename":filename, "num":num}
                    continue
                #未完成，插入重新开
                waitlist.append(it)
                time_tmp+=1
                time.sleep(1)
        if len(result.keys())<1:
            app.logger.error(f'\t该文件合成失败，没有生成任何声音')
            continue    
        sorted_result = {k: result[k] for k in sorted(result, key=lambda x: int(x))}
        for i, it in sorted_result.items():
            theaudio = os.path.normpath(os.path.join(cfg.TTS_DIR, it['filename']))
            with open(concat_txt, 'a', encoding='utf-8') as f:
                f.write(f"file '{theaudio}'\n")
        
        #当前txt执行完成 合并音频
        target_mp3=os.path.normpath((os.path.join(dst,f'{t}.mp3')))
        p=subprocess.run(['ffmpeg',"-hide_banner", "-ignore_unknown", '-y', '-f', 'concat', '-safe', '0', '-i', concat_txt, target_mp3])
        
        if p.returncode!=0:
            app.logger.error(f'\t处理文件:{t},将所有音频连接一起时出错')
            continue
        app.logger.info(f'\t已生成完整音频:{target_mp3}')
        if speed != 1.0 and speed > 0 and speed <= 2.0:
            p= subprocess.run(['ffmpeg', '-hide_banner', '-ignore_unknown', '-y', '-i', target_mp3, '-af', f"atempo={speed}",f'{target_mp3}-speed{speed}.mp3'], encoding="utf-8", capture_output=True)
            if p.returncode != 0:
                app.logger.error(f'\t处理文件{t}:将{target_mp3}音频改变速度{speed}倍时失败')
                continue
            os.unlink(target_mp3)
            target_mp3=f'{target_mp3}-speed{speed}.mp3'
        app.logger.info(f'\t文件:{t} 处理完成，mp3:{target_mp3}')
    app.logger.info('所有文件处理完毕')
    chuliing['end']=True    

@app.route('/ttslist',methods=['GET', 'POST'])
def ttslist():
    
    voice = request.form.get("voice")
    src = request.form.get("src")
    dst = request.form.get("dst")
    speed = 1.0
    try:
        speed = float(request.form.get("speed"))
    except:
        pass
    language = request.form.get("language")

    #根据src获取所有txt
    src=os.path.normpath(src)
    print(f'{src=},{dst=},{language=},{speed=},{voice=}')
    if not src or not dst or not os.path.exists(src) or not os.path.exists(dst):
        return jsonify({"code":1,"msg":"必须正确填写txt所在目录以及目标目录的完整路径"})

    threading.Thread(target=detail_task, args=(voice, src, dst, speed, language)).start()    

    return jsonify({"code":0,"msg":"ok"})







# 根据文本返回tts结果，返回 name=文件名字，filename=文件绝对路径
# 请求端根据需要自行选择使用哪个
# params
# text:待合成文字
# voice：声音文件
# language:语言代码
@app.route('/tts', methods=['GET', 'POST'])
def tts():
    # 原始字符串
    text = request.form.get("text").strip()
    voice = request.form.get("voice")
    speed = 1.0
    try:
        speed = float(request.form.get("speed"))
    except:
        pass
    language = request.form.get("language")
    app.logger.info(f"[tts][tts]recev {text=}\n{voice=},{language=}\n")

    if re.match(r'^[~`!@#$%^&*()_+=,./;\':\[\]{}<>?\\|"，。？；‘：“”’｛【】｝！·￥、\s\n\r -]*$', text):
        return jsonify({"code": 1, "msg": "no text"})
    if not text or not voice or not language:
        return jsonify({"code": 1, "msg": "text/voice/language params lost"})

    # 判断是否是srt
    text_list = get_subtitle_from_srt(text)
    app.logger.info(f"[tts][tts]{text_list=}")
    is_srt = True
    # 不是srt格式,则按行分割
    if text_list is None:
        is_srt = False
        text_list = []
        for it in text.split("\n"):
            text_list.append({"text": it.strip()})
        app.logger.info(f"[tts][tts] its not srt")

    num = 0
    while num < len(text_list):
        t = text_list[num]
        # 换行符改成 .
        t['text'] = t['text'].replace("\n", ' . ')
        md5_hash = hashlib.md5()
        md5_hash.update(f"{t['text']}-{voice}-{language}-{speed}".encode('utf-8'))
        filename = md5_hash.hexdigest() + ".wav"
        app.logger.info(f"[tts][tts]{filename=}")
        # 合成语音
        rs = create_tts(text=t['text'], speed=speed, voice=voice, language=language, filename=filename)
        # 已有结果或错误，直接返回
        if rs is not None:
            text_list[num]['result'] = rs
            num += 1
            continue
        # 循环等待 最多7200s
        time_tmp = 0
        while filename not in cfg.global_tts_result:
            time.sleep(3)
            time_tmp += 3
            if time_tmp % 30 == 0:
                app.logger.info(f"[tts][tts]{time_tmp=},{filename=}")

        # 当前行已完成合成
        if cfg.global_tts_result[filename] != 1:
            msg = {"code": 1, "msg": cfg.global_tts_result[filename]}
        else:
            target_wav = os.path.normpath(os.path.join(TTS_DIR, filename))
            if speed != 1.0 and speed > 0 and speed <= 2.0:
                # 生成的加速音频
                speed_tmp = os.path.join(TMP_DIR, f'speed_{time.time()}.wav')
                p = subprocess.run(
                    ['ffmpeg', '-hide_banner', '-ignore_unknown', '-y', '-i', target_wav, '-af', f"atempo={speed}",
                     os.path.normpath(speed_tmp)], encoding="utf-8", capture_output=True)
                if p.returncode != 0:
                    return jsonify({"code": 1, "msg": str(p.stderr)})
                shutil.copy2(speed_tmp, target_wav)
            msg = {"code": 0, "filename": target_wav, 'name': filename}
        app.logger.info(f"[tts][tts] {filename=},{msg=}")
        cfg.global_tts_result.pop(filename)
        text_list[num]['result'] = msg
        app.logger.info(f"[tts][tts]{num=}")
        num += 1

    filename, errors = merge_audio_segments(text_list, is_srt=is_srt)
    app.logger.info(f"[tts][tts]is srt，{filename=},{errors=}")
    if filename and os.path.exists(filename) and os.path.getsize(filename) > 0:
        res = {"code": 0, "filename": filename, "name": os.path.basename(filename), "msg": errors}
    else:
        res = {"code": 1, "msg": f"error:{filename=},{errors=}"}
    app.logger.info(f"[tts][tts]end result:{res=}")
    return jsonify(res)


# s to s wav->wav
# params
# voice: 声音文件
# filename: 上传的原始声音

@app.route('/sts', methods=['GET', 'POST'])
def sts():
    try:
        # 保存文件到服务器指定目录
        # 目标
        voice = request.form.get("voice")
        filename = request.form.get("name")
        app.logger.info(f"[sts][sts]sts {voice=},{filename=}\n")

        if not voice:
            return jsonify({"code": 1, "msg": "voice params lost"})

        obj = {"filename": filename, "voice": voice}
        # 压入队列，准备转换语音
        app.logger.info(f"[sts][sts]push sts")
        cfg.q_sts.put(obj)
        # 已有结果或错误，直接返回
        # 循环等待 最多7200s
        time_tmp = 0
        while filename not in cfg.global_sts_result:
            time.sleep(3)
            time_tmp += 3
            if time_tmp % 30 == 0:
                app.logger.info(f"{time_tmp=}，{filename=}")

        # 当前行已完成合成
        if cfg.global_sts_result[filename] != 1:
            msg = {"code": 1, "msg": cfg.global_sts_result[filename]}
            app.logger.error(f"[sts][sts]error，{msg=}")
        else:
            msg = {"code": 0, "filename": os.path.join(TTS_DIR, filename), 'name': filename}
            app.logger.info(f"[sts][sts]ok,{msg=}")
        cfg.global_sts_result.pop(filename)
        return jsonify(msg)
    except Exception as e:
        app.logger.error(f"[sts][sts]error:{str(e)}")
        return jsonify({'code': 2, 'msg': f'voice->voice:{str(e)}'})


@app.route('/checkupdate', methods=['GET', 'POST'])
def checkupdate():
    return jsonify({'code': 0, "msg": cfg.updatetips})


if __name__ == '__main__':

    tts_thread = None
    sts_thread = None
    try:
        if 'app.py' == sys.argv[0] and 'app.py' == os.path.basename(__file__):
            print(langlist["lang1"])

        # threading.Thread(target=logic.checkupdate).start()

        if TEXT_MODEL_EXITS:
            print(langlist['lang2'])
            tts_thread = threading.Thread(target=ttsloop)
            tts_thread.start()
        else:
            app.logger.error(f"\n{langlist['lang3']}: {cfg.download_address}\n")
        
        if VOICE_MODEL_EXITS:
            print(langlist['lang4'])
            sts_thread = threading.Thread(target=stsloop)
            sts_thread.start()
        else:
            app.logger.info(
                f"\n{langlist['lang5']}: {cfg.download_address}\n")
        
        if not VOICE_MODEL_EXITS and not TEXT_MODEL_EXITS:
            print(f"\n{langlist['lang6']}: {cfg.download_address}\n")
            input("Press Enter close")
            sys.exit()

        print("===")
        http_server = None
        try:
            host = web_address.split(':')
            print(f'{host=}')
            http_server = WSGIServer((host[0], int(host[1])), app, handler_class=CustomRequestHandler)
            print(f'@@@@@@@@@@@')
            threading.Thread(target=openweb, args=(web_address,)).start()
            http_server.serve_forever()
        finally:
            if http_server:
                http_server.stop()
            # 设置事件，通知线程退出
            cfg.exit_event.set()
            # 等待后台线程结束
            if tts_thread:
                tts_thread.join()
            if sts_thread:
                sts_thread.join()
    except Exception as e:
        print("error:" + str(e))
        app.logger.error(f"[app]start error:{str(e)}")
        sys.exit()
