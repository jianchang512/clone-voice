import datetime
import json
import logging
import re
import threading
import time
import sys

import aiohttp
from flask import Flask, request, render_template, jsonify, send_file, send_from_directory
import os
from dotenv import load_dotenv

load_dotenv()
ROOT_DIR = os.getcwd()  # os.path.dirname(os.path.abspath(__file__))
print(f"当前项目路径：{ROOT_DIR}")
os.environ['TTS_HOME'] = ROOT_DIR
if sys.platform == 'win32':
    os.environ['PATH'] = ROOT_DIR + ';' + os.environ['PATH']
else:
    os.environ['PATH'] = ROOT_DIR + ':' + os.environ['PATH']
import glob
import hashlib
import torch
from pydub import AudioSegment
from logging.handlers import RotatingFileHandler
from TTS.api import TTS
import queue
import webbrowser

def setorget_proxy():
    proxy = os.environ.get("http_proxy", '') or os.environ.get("HTTP_PROXY", '')
    if proxy:
        os.environ['AIOHTTP_PROXY'] = "http://" + proxy.replace('http://', '')
        return proxy
    if not proxy:
        proxy = os.getenv('HTTP_PROXY', '')
        if proxy:
            os.environ['HTTP_PROXY'] = "http://" + proxy.replace('http://', '')
            os.environ['HTTPS_PROXY'] = "http://" + proxy.replace('http://', '')
            os.environ['AIOHTTP_PROXY'] = "http://" + proxy.replace('http://', '')
            return proxy
    return proxy
# 存放录制好的素材，5-15s的语音 wav
VOICE_DIR = os.path.join(ROOT_DIR, 'static/voicelist')
# 存放经过tts转录后的wav文件
TTS_DIR = os.path.join(ROOT_DIR, 'static/ttslist')
# 临时目录
TMP_DIR = os.path.join(ROOT_DIR, 'static/tmp')
# 声音转声音 模型是否存在
if os.path.exists(os.path.join(ROOT_DIR, "tts/voice_conversion_models--multilingual--vctk--freevc24/model.pth")):
    VOICE_MODEL_EXITS = True
else:
    VOICE_MODEL_EXITS = False


if not os.path.exists(VOICE_DIR):
    os.makedirs(VOICE_DIR)
if not os.path.exists(TTS_DIR):
    os.makedirs(TTS_DIR)
if not os.path.exists(TMP_DIR):
    os.makedirs(TMP_DIR)

q = queue.Queue(maxsize=100)
q_sts = queue.Queue(maxsize=100)
device = "cuda" if torch.cuda.is_available() else "cpu"
global_tts_result = {}
global_sts_result = {}
# 用于通知线程退出的事件
exit_event = threading.Event()


# tts 合成线程
def ttsloop():
    global global_tts_result
    try:
        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
        print(f'启动 文字->声音 线程成功')
    except aiohttp.client_exceptions.ClientOSError as e:
        print(f'启动 文字->声音 线程失败：{str(e)}')
        if not setorget_proxy():
            print(f'请在 .env 文件中正确设置 http 代理，以便能从 https://huggingface.co 下载模型')
        else:
            print(f'你设置的代理不可用，请设置正确的代理，以便能从 https://huggingface.co 下载模型')
        return
    except Exception as e:
        print(f'启动 文字->声音 线程失败：{str(e)}')
        return

    while not exit_event.is_set():
        try:
            obj = q.get(block=True, timeout=1)
        except Exception:
            continue
        app.logger.info(f"[tts][ttsloop]开始合成，{obj=}")
        try:
            tts.tts_to_file(text=obj['text'], speaker_wav=os.path.join(VOICE_DIR, obj['voice']),
                            language=obj['language'], file_path=os.path.join(TTS_DIR, obj['filename']))
            global_tts_result[obj['filename']] = 1
            app.logger.info(f"[tts][ttsloop]合成结束{obj=}")
        except Exception as e:
            app.logger.error(f"[tts][ttsloop]合成失败:{str(e)}")
            global_tts_result[obj['filename']] = str(e)


# s t s 线程
def stsloop():
    global global_sts_result
    try:
        tts = TTS(model_name='voice_conversion_models/multilingual/vctk/freevc24').to(device)
        print(f'启动 声音->声音 线程成功')
    except aiohttp.client_exceptions.ClientOSError as e:
        print(f'启动 声音->声音 线程失败：{str(e)}')
        if not setorget_proxy():
            print(f'请在 .env 文件中正确设置 http 代理，以便能从 https://huggingface.co 下载模型')
        else:
            print(f'你设置的代理{os.environ.get("HTTP_PROXY")} 不可用，请设置正确的代理，以便能从 https://huggingface.co 下载模型')
        return
    except Exception as e:
        print(f'启动 声音->声音 线程失败：{str(e)}')
        app.logger.error(f"启动声音->声音线程失败{str(e)}")
        return
    while not exit_event.is_set():
        try:
            obj = q_sts.get(block=True, timeout=1)
        except Exception as e:
            continue
        app.logger.info(f"[sts][stsloop]开始转换声音，{obj=}")
        try:
            tts.voice_conversion_to_file(source_wav=os.path.join(TMP_DIR, obj['filename']),
                                         target_wav=os.path.join(VOICE_DIR, obj['voice']),
                                         file_path=os.path.join(TTS_DIR, obj['filename']))
            global_sts_result[obj['filename']] = 1
            app.logger.info(f"[sts][stsloop]合成结束{obj=}")
        except Exception as e:
            app.logger.error(f"[sts][stsloop]转换声音失败:{str(e)}")
            global_sts_result[obj['filename']] = str(e)



# 实际启动tts合成的函数
def create_tts(*, text, voice, language, filename):
    global global_tts_result
    absofilename = os.path.join(TTS_DIR, filename)
    if os.path.exists(absofilename) and os.path.getsize(absofilename) > 0:
        app.logger.info(f"[tts][create_ts]{filename}已存在，直接返回")
        global_tts_result[filename] = 1
        return {"code": 0, "filename": absofilename, 'name': filename}
    try:
        app.logger.info(f"[tts][create_ts]{text}压入队列，准备合成")
        q.put({"voice": voice, "text": text, "language": language, "filename": filename})
    except Exception as e:
        print(e)
        app.logger.error(f"[tts][create_ts]合成出错，{str(e)}")
        return {"code": 1, "msg": str(e)}
    return None


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
    return render_template("index.html", voice_model=voice_model, root_dir=ROOT_DIR.replace('\\','/'))


# 上传音频
@app.route('/upload', methods=['POST'])
def upload():
    try:
        # 获取上传的文件
        audio_file = request.files['audio']
        save_dir = request.form.get("save_dir")
        save_dir = VOICE_DIR if not save_dir else os.path.join(ROOT_DIR, f'static/{save_dir}')
        app.logger.info(f"[upload]上传文件{audio_file.filename=},{save_dir=}")
        # 检查文件是否存在且是 WAV 格式
        if audio_file and audio_file.filename.endswith('.wav'):
            # 保存文件到服务器指定目录
            name = f"{os.path.basename(audio_file.filename.replace(' ', ''))}"
            if os.path.exists(os.path.join(save_dir, name)):
                name = f'{datetime.datetime.now().strftime("%m%d-%H%M%S")}-{name}'

            savename = os.path.join(save_dir, name)
            tmp_wav = os.path.join(TMP_DIR, "tmp_"+name)
            audio_file.save(tmp_wav)
            os.system(f'ffmpeg -y -i "{tmp_wav}" "{savename}"')
            os.unlink(tmp_wav)
            # 返回成功的响应
            return {'code': 0, 'msg': '上传成功', "data": name}
        else:
            # 返回错误的响应
            return {'code': 1, 'msg': '上传的文件不是 wav 格式'}
    except Exception as e:
        app.logger.error(f'[upload]上传错误: {e}')
        return {'code': 2, 'msg': '上传失败'}


# 从 voicelist 目录获取可用的 wav 声音列表
@app.route('/init')
def init():
    wavs = glob.glob(f"{VOICE_DIR}/*.wav")
    result = []
    for it in wavs:
        if os.path.getsize(it) > 0:
            result.append(os.path.basename(it))
    return jsonify(result)


# 判断是否符合字幕格式，如果是，则直接返回
# 从字幕文件获取格式化后的字幕信息
'''
[
{'line': 13, 'time': '00:01:56,423 --> 00:02:06,423', 'text': '因此，如果您准备好停止沉迷于不太理想的解决方案并开始构建下一个
出色的语音产品，我们已准备好帮助您实现这一目标。深度图。没有妥协。唯一的机会..', 'startraw': '00:01:56,423', 'endraw': '00:02:06,423', 'start_time'
: 116423, 'end_time': 126423}, 
{'line': 14, 'time': '00:02:06,423 --> 00:02:07,429', 'text': '机会..', 'startraw': '00:02:06,423', 'endraw': '00:02
:07,429', 'start_time': 126423, 'end_time': 127429}
]
'''


def get_subtitle_from_srt(txt):
    # 行号
    line = 0
    maxline = len(txt)
    # 行格式
    linepat = r'^\s*?\d+\s*?$'
    # 时间格式
    timepat = r'^\s*?\d+:\d+:\d+\,?\d*?\s*?-->\s*?\d+:\d+:\d+\,?\d*?$'
    txt = txt.strip().split("\n")
    # 先判断是否符合srt格式，不符合返回None
    if len(txt) < 3:
        return None
    if not re.match(linepat, txt[0]) or not re.match(timepat, txt[1]):
        return None
    result = []
    for i, t in enumerate(txt):
        # 当前行 小于等于倒数第三行 并且匹配行号，并且下一行匹配时间戳，则是行号
        if i < maxline - 2 and re.match(linepat, t) and re.match(timepat, txt[i + 1]):
            #   是行
            line += 1
            obj = {"line": line, "time": "", "text": ""}
            result.append(obj)
        elif re.match(timepat, t):
            # 是时间行
            result[line - 1]['time'] = t
        elif len(t.strip()) > 0:
            # 是内容
            result[line - 1]['text'] += t.strip().replace("\n", '')
    # 再次遍历，删掉美元text的行
    new_result = []
    line = 1
    for it in result:
        if "text" in it and len(it['text'].strip()) > 0 and not re.match(r'^[,./?`!@#$%^&*()_+=\\|\[\]{}~\s \n-]*$',
                                                                         it['text']):
            it['line'] = line
            startraw, endraw = it['time'].strip().split(" --> ")
            start = startraw.replace(',', '.').split(":")
            start_time = int(int(start[0]) * 3600000 + int(start[1]) * 60000 + float(start[2]) * 1000)
            end = endraw.replace(',', '.').split(":")
            end_time = int(int(end[0]) * 3600000 + int(end[1]) * 60000 + float(end[2]) * 1000)
            it['startraw'] = startraw
            it['endraw'] = endraw
            it['start_time'] = start_time
            it['end_time'] = end_time
            new_result.append(it)
            line += 1
    return new_result


# 根据文本返回tts结果，返回 name=文件名字，filename=文件绝对路径
# 请求端根据需要自行选择使用哪个
@app.route('/tts', methods=['GET', 'POST'])
def tts():
    global global_tts_result
    # 原始字符串
    text = request.form.get("text").strip()
    voice = request.form.get("voice")
    language = request.form.get("language")
    app.logger.info(f"[tts][tts]接收到 {text=}\n{voice=},{language=}\n")

    if re.match(r'^[~`!@#$%^&*()_+=,./;\':\[\]{}<>?\\|"，。？；‘：“”’｛【】｝！·￥、\s\n\r -]*$', text):
        return jsonify({"code": 1, "msg": "不存在有效text，无法合成"})
    if not text or not voice or not language:
        return jsonify({"code": 1, "msg": "text，voice，language 参数缺一不可"})

    # 判断是否是srt
    text_list = get_subtitle_from_srt(text)
    app.logger.info(f"[tts][tts]{text_list=}")
    is_srt = False
    # 不是srt格式
    if text_list is None:
        text_list = [{"text": text}]
        app.logger.info(f"[tts][tts]不是srt格式")
    else:
        # 是字幕
        is_srt = True
        app.logger.info(f"[tts][tts]是srt格式")
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
        while filename not in global_tts_result:
            time.sleep(3)
            time_tmp += 3
            if time_tmp % 30 == 0:
                app.logger.info(f"[tts][tts]{time_tmp=}，{filename=}")

        # 当前行已完成合成
        if global_tts_result[filename] != 1:
            msg = {"code": 1, "msg": global_tts_result[filename]}
        else:
            msg = {"code": 0, "filename": os.path.join(TTS_DIR, filename), 'name': filename}
        app.logger.info(f"[tts][tts]当前结果,{filename=},{msg=}")
        global_tts_result.pop(filename)
        if not is_srt:
            response_json = msg
            break

        text_list[num]['result'] = msg
        app.logger.info(f"[tts][tts]{num=}")
        num += 1
    # 不是字幕则返回
    if not is_srt:
        app.logger.info(f"[tts][tts] 不是srt字幕，最终结果 {response_json=}")
        return jsonify(response_json)
    # 继续处理字幕

    filename, errors = merge_audio_segments(text_list)
    app.logger.info(f"[tts][tts]是srt字幕格式，{filename=},{errors=}")
    if filename and os.path.exists(filename) and os.path.getsize(filename) > 0:
        res = {"code": 0, "filename": filename, "name": os.path.basename(filename), "msg": errors}
    else:
        res = {"code": 1, "msg": f"合成出错了:{filename=},{errors=}"}
    app.logger.info(f"[tts][tts]最终合成结果:{res=}")
    return jsonify(res)


# s to s wav->wav
@app.route('/sts', methods=['GET', 'POST'])
def sts():
    global global_sts_result
    try:
        # 保存文件到服务器指定目录
        # 目标
        voice = request.form.get("voice")
        filename = request.form.get("name")
        app.logger.info(f"[sts][sts]获取到 sts {voice=},{filename=}\n")

        if not voice:
            return jsonify({"code": 1, "msg": "voice 参数不可缺少"})

        obj = {"filename": filename, "voice": voice}
        # 压入队列，准备转换语音
        app.logger.info(f"[sts][sts]压入 sts队列，准备转换")
        q_sts.put(obj)
        # 已有结果或错误，直接返回
        # 循环等待 最多7200s
        time_tmp = 0
        while filename not in global_sts_result:
            time.sleep(3)
            time_tmp += 3
            if time_tmp % 30 == 0:
                app.logger.info(f"{time_tmp=}，{filename=}")

        # 当前行已完成合成
        if global_sts_result[filename] != 1:
            msg = {"code": 1, "msg": global_sts_result[filename]}
            app.logger.error(f"[sts][sts]转换失败，{msg=}")
        else:
            msg = {"code": 0, "filename": os.path.join(TTS_DIR, filename), 'name': filename}
            app.logger.info(f"[sts][sts]转换成功，{msg=}")
        global_sts_result.pop(filename)
        return jsonify(msg)
    except Exception as e:
        app.logger.error(f"[sts][sts]转换失败:{str(e)}")
        return jsonify({'code': 2, 'msg': f'声音转声音失败:{str(e)}'})


# join all short audio to one ,eg name.mp4  name.mp4.wav
def merge_audio_segments(text_list):
    # 获得md5
    md5_hash = hashlib.md5()
    md5_hash.update(f"{json.dumps(text_list)}".encode('utf-8'))
    filename = md5_hash.hexdigest() + ".wav"
    absofilename = os.path.join(TTS_DIR, filename)
    if os.path.exists(absofilename):
        return (absofilename, "")
    segments = []
    start_times = []
    errors = []
    for it in text_list:
        if "filename" in it['result']:
            # 存在音频文件
            segments.append(AudioSegment.from_wav(it['result']['filename']))
            start_times.append(it['start_time'])
        elif "msg" in it['result']:
            # 出错
            errors.append(it['result']['msg'])

    merged_audio = AudioSegment.empty()
    # start is not 0
    if int(start_times[0]) != 0:
        silence_duration = start_times[0]
        silence = AudioSegment.silent(duration=silence_duration)
        merged_audio += silence

    # join
    for i in range(len(segments)):
        segment = segments[i]
        start_time = start_times[i]
        # add silence
        if i > 0:
            previous_end_time = start_times[i - 1] + len(segments[i - 1])
            silence_duration = start_time - previous_end_time
            # 可能存在字幕 语音对应问题
            if silence_duration > 0:
                silence = AudioSegment.silent(duration=silence_duration)
                merged_audio += silence

        merged_audio += segment

    merged_audio.export(absofilename, format="wav")
    return (absofilename, "<-->".join(errors))


def openweb():
    time.sleep(5)
    webbrowser.open(web_address)
    print(f"已打开浏览器窗口")


if __name__ == '__main__':
    web_address='http://'+os.getenv('WEB_ADDRESS','127.0.0.1:9988')
    tts_thread=None
    sts_thread=None
    try:
        print(f"本地web地址: {web_address}")
        print("开始启动，请稍后...")
        app.logger.info(f"本地web地址: {web_address}")
        print("准备启动 文字->声音 线程")
        tts_thread=threading.Thread(target=ttsloop)
        tts_thread.start()
        if VOICE_MODEL_EXITS:
            print("准备启动 声音->声音 线程")
            sts_thread=threading.Thread(target=stsloop)
            sts_thread.start()
        elif os.path.exists(os.path.join(ROOT_DIR, 'tts/speech-to-speech')):
            print("语音到语音模型直接解压到 tts 目录下，而非 tts/speech-to-speech 目录")
        #stsloop()
        threading.Thread(target=openweb).start()
        print("启动后加载模型可能需要几分钟，请耐心等待,当显示 【启动xxx线程成功】后，可使用")
    except Exception as e:
        print("执行出错:" + str(e))
        app.logger.error(f"[app]启动出错:{str(e)}")
    try:
        app.run(port=web_address.split(':')[-1])
    finally:
        # 设置事件，通知线程退出
        exit_event.set()
        # 等待后台线程结束
        if tts_thread:
            tts_thread.join()
        if sts_thread:
            sts_thread.join()

