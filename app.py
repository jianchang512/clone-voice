import datetime
import logging
import queue
import re
import threading
import time
import sys
from flask import Flask, request, render_template, jsonify, send_file, send_from_directory
import os
import glob
import hashlib
from logging.handlers import RotatingFileHandler

import clone
from clone import cfg
from clone.cfg import ROOT_DIR, TTS_DIR, VOICE_MODEL_EXITS, TMP_DIR, VOICE_DIR, TEXT_MODEL_EXITS, langlist
from clone.logic import ttsloop, stsloop, create_tts, openweb, merge_audio_segments, get_subtitle_from_srt, updatecache
from clone import logic
import shutil
import subprocess
from dotenv import load_dotenv
from waitress import serve
load_dotenv()

web_address = os.getenv('WEB_ADDRESS', '127.0.0.1:9988')
enable_sts = int(os.getenv('ENABLE_STS', '0'))



updatecache()

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

app.logger.setLevel(logging.WARNING)  # 设置日志级别为 INFO
# 创建 RotatingFileHandler 对象，设置写入的文件路径和大小限制
file_handler = RotatingFileHandler(os.path.join(ROOT_DIR, 'app.log'), maxBytes=1024 * 1024, backupCount=5)
# 创建日志的格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# 设置文件处理器的级别和格式
file_handler.setLevel(logging.WARNING)
file_handler.setFormatter(formatter)
# 将文件处理器添加到日志记录器中
app.logger.addHandler(file_handler)
app.jinja_env.globals.update(enumerate=enumerate)



@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.config['STATIC_FOLDER'], filename)


@app.route('/')
def index():
    return render_template("index.html",
                           text_model=TEXT_MODEL_EXITS,
                           voice_model=VOICE_MODEL_EXITS,
                           version=clone.ver,
                           mymodels=cfg.MYMODEL_OBJS,
                           language=cfg.LANG,
                           langlist=cfg.langlist,
                           root_dir=ROOT_DIR.replace('\\', '/'))


# 上传音频
@app.route('/upload', methods=['POST'])
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
    result.extend(cfg.MYMODEL_OBJS.keys())
    return jsonify(result)


# 判断线程是否启动
@app.route('/isstart', methods=['GET', 'POST'])
def isstart():
    return jsonify(cfg.MYMODEL_OBJS)


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
        langcodelist = ["zh-cn", "en", "ja", "ko", "es", "de", "fr", "it", "tr", "ru", "pt", "pl", "nl", "ar", "hu", "cs"]
        text = request.form.get("text","").strip()
        model = request.form.get("model","").strip()
        text = text.replace("\n", ' . ')
        language = request.form.get("language", "").lower()
        if language.startswith("zh"):
            language = "zh-cn"
        if language not in langcodelist:
            return jsonify({"code": 1, "msg": f" {language} dont support language "})

        md5_hash = hashlib.md5()

        audio_name = request.form.get('voice','')
        voicename=""
        model=""
        # 存在传来的声音文件名字
        print(f'1,{text=},{model=},{audio_name=},{language=}')
        if audio_name and audio_name.lower().endswith('.wav'):
            voicename = os.path.join(VOICE_DIR, audio_name)
            if not os.path.exists(voicename):
                return jsonify({"code": 2, "msg": f"{audio_name} 不存在"})
            if os.path.isdir(voicename):
                model=audio_name
                voicename=""
        elif audio_name:
            #存在，是新模型
            model=audio_name
        elif not audio_name:  # 不存在，原声复制 clone 获取上传的文件
            audio_file = request.files['audio']
            print(f'{audio_file.filename}')
            # 保存临时上传过来的声音文件
            audio_name = f'video_{audio_file.filename}.wav'
            voicename = os.path.join(TMP_DIR, audio_name)
            audio_file.save(voicename)
        print(f'22={text=},{model=},{audio_name=},{language=}')
        md5_hash.update(f"{text}-{language}-{audio_name}-{model}".encode('utf-8'))

        app.logger.info(f"[apitts]{voicename=}")
        if re.match(r'^[~`!@#$%^&*()_+=,./;\':\[\]{}<>?\\|"，。？；‘：“”’｛【】｝！·￥、\s\n\r -]*$', text):
            return jsonify({"code": 3, "msg": "lost text for translate"})
        if not text or not language:
            return jsonify({"code": 4, "msg": "text & language params lost"})
        app.logger.info(f"[apitts]{text=},{language=}")

        # 存放结果
        # 合成后的语音文件, 以wav格式存放和返回
        filename = md5_hash.hexdigest() + ".wav"
        app.logger.info(f"[apitts]{filename=}")
        # 合成语音
        rs = create_tts(text=text,model=model, speed=1.0, voice=voicename, language=language, filename=filename)
        # 已有结果或错误，直接返回
        if rs is not None:
            print(f'{rs=}')
            result = rs
        else:
            # 循环等待 最多7200s
            time_tmp = 0
            while filename not in cfg.global_tts_result:
                time.sleep(3)
                time_tmp += 3
                if time_tmp % 30 == 0:
                    app.logger.info(f"[apitts][tts]{time_tmp=},{filename=}")
                if time_tmp>3600:
                    return jsonify({"code": 5, "msg": f'error:{text}'})
                    

            # 当前行已完成合成
            target_wav = os.path.normpath(os.path.join(TTS_DIR, filename))
            if not os.path.exists(target_wav):
                msg = {"code": 6, "msg": cfg.global_tts_result[filename] if filename in cfg.global_tts_result else "error"}
            else:
                
                msg = {"code": 0, "filename": target_wav, 'name': filename}
            app.logger.info(f"[apitts][tts] {filename=},{msg=}")
            try:
                cfg.global_tts_result.pop(filename)
            except:
                pass
            result = msg
            app.logger.info(f"[apitts]{msg=}")
        if result['code'] == 0:
            result['url'] = f'http://{web_address}/static/ttslist/{filename}'
        return jsonify(result)
    except Exception as e:
        msg = f'{str(e)} {str(e.args)}'
        app.logger.error(f"[apitts]{msg}")
        return jsonify({'code': 7, 'msg': msg})


# 根据文本返回tts结果，返回 name=文件名字，filename=文件绝对路径
# 请求端根据需要自行选择使用哪个
# params
# text:待合成文字
# voice：声音文件
# language:语言代码
@app.route('/tts', methods=['GET', 'POST'])
def tts():
    # 原始字符串
    text = request.form.get("text","").strip()
    voice = request.form.get("voice",'')
    speed = 1.0
    try:
        speed = float(request.form.get("speed",1))
    except:
        pass
    language = request.form.get("language",'')
    model = request.form.get("model","")
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
        md5_hash.update(f"{t['text']}-{voice}-{language}-{speed}-{model}".encode('utf-8'))
        filename = md5_hash.hexdigest() + ".wav"
        app.logger.info(f"[tts][tts]{filename=}")
        # 合成语音
        rs = create_tts(text=t['text'], model=model,speed=speed, voice=os.path.join(cfg.VOICE_DIR, voice), language=language, filename=filename)
        # 已有结果或错误，直接返回
        if rs is not None:
            text_list[num]['result'] = rs
            num += 1
            continue
        # 循环等待 最多7200s
        time_tmp = 0
        # 生成的目标音频
        target_wav = os.path.normpath(os.path.join(TTS_DIR, filename))
        msg=None
        while filename not in cfg.global_tts_result and not os.path.exists(target_wav):
            time.sleep(3)
            time_tmp += 3
            if time_tmp % 30 == 0:
                app.logger.info(f"[tts][tts]{time_tmp=},{filename=}")
            if time_tmp>3600:
                msg={"code": 1, "msg":f'{filename} error'}
                text_list[num]['result'] = msg
                num+=1
                break
        if msg is not None:
            continue
                

        # 当前行已完成合成
        if not os.path.exists(target_wav):
            msg = {"code": 1, "msg": "not exists"}
        else:
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
        try:
            cfg.global_tts_result.pop(filename)
        except:
            pass
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
        voice = request.form.get("voice",'')
        filename = request.form.get("name",'')
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




# 启动或关闭模型
@app.route('/onoroff',methods=['GET','POST'])
def onoroff():
    name = request.form.get("name",'')
    status_new = request.form.get("status_new",'')
    if status_new=='on':
        if name not in cfg.MYMODEL_OBJS  or not cfg.MYMODEL_OBJS[name] or  isinstance(cfg.MYMODEL_OBJS[name],str):
            try:
                print(f'start {name}...')
                res=logic.load_model(name)
                print(f'{res=}')
                return jsonify({"code":0,"msg":res})
            except Exception as e:
                return jsonify({"code":1,"msg":str(e)})
        elif cfg.MYMODEL_OBJS[name] in ['error','no']:
            return jsonify({"code":0,"msg":"模型启动出错或不存在"})
        return jsonify({"code":0,"msg":"已启动"})
    else:
        #关闭
        cfg.MYMODEL_OBJS[name]=None
        #删除队列
        cfg.MYMODEL_QUEUE[name]=None
        return jsonify({"code":0,"msg":"已停止"})

@app.route('/checkupdate', methods=['GET', 'POST'])
def checkupdate():
    return jsonify({'code': 0, "msg": cfg.updatetips})

@app.route('/stsstatus', methods=['GET', 'POST'])
def stsstatus():
    return jsonify({'code': 0, "msg": "start" if cfg.sts_status else "stop"})



if __name__ == '__main__':

    tts_thread = None
    sts_thread = None
    try:
        if 'app.py' == sys.argv[0] and 'app.py' == os.path.basename(__file__):
            print(langlist["lang1"])

        threading.Thread(target=logic.checkupdate).start()

        # 如果存在默认模型则启动
        
        if TEXT_MODEL_EXITS:
            print("\n"+langlist['lang2'])
            tts_thread = threading.Thread(target=ttsloop)
            tts_thread.start()
        else:
            app.logger.error(
                f"\n{langlist['lang3']}: {cfg.download_address}\n")
            input(f"\n{langlist['lang3']}: {cfg.download_address}\n")
            sys.exit()
        
        if enable_sts==1 and VOICE_MODEL_EXITS:
            print(langlist['lang4'])
            sts_thread = threading.Thread(target=stsloop)
            sts_thread.start()
        #else:
        #    app.logger.error(
        #        f"\n{langlist['lang5']}: {cfg.download_address}\n")
        
        print(langlist['lang7'])
        try:
            host = web_address.split(':')
            threading.Thread(target=openweb, args=(web_address,)).start()
            serve(app,host=host[0], port=int(host[1]))
        finally:
           print('exit')
    except Exception as e:
        print("error:" + str(e))
        app.logger.error(f"[app]start error:{str(e)}")
        time.sleep(30)
        sys.exit()
