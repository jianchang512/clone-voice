import datetime
import logging
import re
import threading
import time
import sys
from flask import Flask, request, render_template, jsonify, send_file, send_from_directory
import os
from gevent.pywsgi import WSGIServer
import glob
import hashlib
from logging.handlers import RotatingFileHandler
from clone import cfg
from clone.cfg import ROOT_DIR, TTS_DIR, VOICE_MODEL_EXITS, TMP_DIR, VOICE_DIR, TEXT_MODEL_EXITS,langlist
from clone.logic import ttsloop, stsloop, create_tts, openweb, merge_audio_segments, get_subtitle_from_srt
from clone import logic

app = Flask(__name__, static_folder=os.path.join(ROOT_DIR, 'static'), static_url_path='/static',
            template_folder=os.path.join(ROOT_DIR, 'templates'))
# 配置日志
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
    voice_model = "yes" if VOICE_MODEL_EXITS else "no"
    text_model = "yes" if TEXT_MODEL_EXITS else "no"
    return render_template("index.html", text_model=text_model, voice_model=voice_model,
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
        # 检查文件是否存在且是 WAV 格式
        if audio_file and audio_file.filename.endswith('.wav'):
            # 保存文件到服务器指定目录
            name = f"{os.path.basename(audio_file.filename.replace(' ', ''))}"
            if os.path.exists(os.path.join(save_dir, name)):
                name = f'{datetime.datetime.now().strftime("%m%d-%H%M%S")}-{name}'

            savename = os.path.join(save_dir, name)
            tmp_wav = os.path.join(TMP_DIR, "tmp_" + name)
            audio_file.save(tmp_wav)
            os.system(f'ffmpeg -y -i "{tmp_wav}" "{savename}"')
            os.unlink(tmp_wav)
            # 返回成功的响应
            return {'code': 0, 'msg': 'ok', "data": name}
        else:
            # 返回错误的响应
            return {'code': 1, 'msg': 'not wav'}
    except Exception as e:
        app.logger.error(f'[upload]error: {e}')
        return {'code': 2, 'msg': 'error'}


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
    return jsonify({"code": 0, "msg": total, "tts": cfg.langlist['lang15'] if cfg.tts_n<1 else "", "sts":cfg.langlist['lang16'] if cfg.sts_n<1 else ""})


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
    language = request.form.get("language")
    app.logger.info(f"[tts][tts]recev {text=}\n{voice=},{language=}\n")

    if re.match(r'^[~`!@#$%^&*()_+=,./;\':\[\]{}<>?\\|"，。？；‘：“”’｛【】｝！·￥、\s\n\r -]*$', text):
        return jsonify({"code": 1, "msg": "no text"})
    if not text or not voice or not language:
        return jsonify({"code": 1, "msg": "text/voice/language params lost"})

    # 判断是否是srt
    text_list = get_subtitle_from_srt(text)
    app.logger.info(f"[tts][tts]{text_list=}")
    is_srt = False
    # 不是srt格式
    if text_list is None:
        text_list = [{"text": text}]
        app.logger.info(f"[tts][tts] its not srt")
    else:
        # 是字幕
        is_srt = True
    num = 0
    response_json = {}
    while num < len(text_list):
        t = text_list[num]
        # 换行符改成 .
        t['text'] = t['text'].replace("\n", ' . ')
        md5_hash = hashlib.md5()
        md5_hash.update(f"{t['text']}-{voice}-{language}".encode('utf-8'))
        filename = md5_hash.hexdigest() + ".wav"
        app.logger.info(f"[tts][tts]{filename=}")
        # 合成语音
        rs = create_tts(text=t['text'], voice=voice, language=language, filename=filename)
        # 已有结果或错误，直接返回
        if rs is not None:
            if not is_srt:
                response_json = rs
                break
            else:
                text_list[num]['result'] = rs
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
            msg = {"code": 0, "filename": os.path.join(TTS_DIR, filename), 'name': filename}
        app.logger.info(f"[tts][tts] {filename=},{msg=}")
        cfg.global_tts_result.pop(filename)
        if not is_srt:
            response_json = msg
            break

        text_list[num]['result'] = msg
        app.logger.info(f"[tts][tts]{num=}")
        num += 1
    # 不是字幕则返回
    if not is_srt:
        app.logger.info(f"[tts][tts] {response_json=}")
        return jsonify(response_json)
    # 继续处理字幕

    filename, errors = merge_audio_segments(text_list)
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
    return jsonify({'code':0,"msg":cfg.updatetips})

if __name__ == '__main__':
    web_address = os.getenv('WEB_ADDRESS', '127.0.0.1:9988')
    tts_thread = None
    sts_thread = None
    try:
        if 'app.py' == sys.argv[0] and 'app.py' == os.path.basename(__file__):
            print(langlist["lang1"])

        threading.Thread(target=logic.checkupdate).start()

        if TEXT_MODEL_EXITS:
            print(langlist['lang2'])
            tts_thread = threading.Thread(target=ttsloop)
            tts_thread.start()
        else:
            app.logger.error(
                f"{langlist['lang3']}: {cfg.download_address}\n\n")

        if VOICE_MODEL_EXITS:
            print(langlist['lang4'])
            sts_thread = threading.Thread(target=stsloop)
            sts_thread.start()
        else:
            app.logger.error(
                f"{langlist['lang5']}: {cfg.download_address}\n\n")

        if not VOICE_MODEL_EXITS and not TEXT_MODEL_EXITS:
            print(f"{langlist['lang6']}: {cfg.download_address}\n\n")
        else:
            print(langlist['lang7'])
            http_server = None
            try:
                host = web_address.split(':')
                http_server = WSGIServer((host[0], int(host[1])), app)
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
