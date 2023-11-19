import datetime
import json
import logging
import re
import threading
import time

from flask import Flask, request, render_template, jsonify, send_file
import os
import glob
import hashlib
import torch
from pydub import AudioSegment
from logging.handlers import RotatingFileHandler


from TTS.api import TTS
import queue
import webbrowser

ROOT_DIR=os.getcwd().replace('\\', '/')

#logging.basicConfig(
#            level=logging.INFO,
#            filename=f'{ROOT_DIR}/tts.log',
#            encoding="utf-8",
#            filemode="a"
#)
#print(f'{ROOT_DIR}/tts.log')
#logger = logging.getLogger('TTS')

# 存放录制好的素材，5-15s的语音mp3
VOICE_DIR = os.path.join(ROOT_DIR, 'static/voicelist').replace('\\', '/')
# 存放经过tts转录后的wav文件
TTS_DIR = os.path.join(ROOT_DIR, 'static/ttslist').replace('\\', '/')
os.environ['PATH'] = ROOT_DIR + ';' + os.environ['PATH']

if not os.path.exists(VOICE_DIR):
    os.makedirs(VOICE_DIR)
if not os.path.exists(TTS_DIR):
    os.makedirs(TTS_DIR)

q=queue.Queue(maxsize=100)
device = "cuda" if torch.cuda.is_available() else "cpu"

globa_result={}

# 合成线程
def ttsloop():
    global globa_result
    
    tts = TTS(
            model_path=f"{ROOT_DIR}/models/tts_models--multilingual--multi-dataset--xtts_v2",
            config_path=f"{ROOT_DIR}/models/tts_models--multilingual--multi-dataset--xtts_v2/config.json").to(device)
    while True:
        try:
            obj=q.get(block=True,timeout=1)
            app.logger.info(f"开始合成，{obj=}")
            try:
                tts.tts_to_file(text=obj['text'], speaker_wav=os.path.join(VOICE_DIR, obj['voice']), language=obj['language'], file_path=f"{TTS_DIR}/{obj['filename']}")
                globa_result[obj['filename']]=1
                app.logger.info(f"合成结束{obj=}")
            except Exception as e:
                print(f"合成失败:{str(e)}")
                app.logger.error(f"合成失败:{str(e)}")
                globa_result[obj['filename']]=str(e)           
        except Exception as e:
            pass
            # print(e)


# 实际启动tts合成的函数
def create_tts(*,text,voice,language,filename):
    global globa_result
    if os.path.exists(f"{TTS_DIR}/{filename}") and os.path.getsize(f"{TTS_DIR}/{filename}") > 0:
        app.logger.info(f"{filename}已存在，直接返回")
        globa_result[filename]=1
        return {"code": 0, "filename": f"{TTS_DIR}/{filename}", 'name': filename}
    try:
        app.logger.info(f"{text}压入队列，准备合成")
        q.put({"voice": voice, "text": text, "language": language, "filename": filename})
    except Exception as e:
        print(e)
        return {"code": 1, "msg": str(e)}
    return None



app = Flask(__name__,static_folder=f'{ROOT_DIR}/static', static_url_path='/static', template_folder=f'{ROOT_DIR}/templates')

# 配置日志
app.logger.setLevel(logging.INFO)  # 设置日志级别为 INFO

# 创建 RotatingFileHandler 对象，设置写入的文件路径和大小限制
file_handler = RotatingFileHandler(f'{ROOT_DIR}/app.log', maxBytes=1024*1024, backupCount=5)

# 创建日志的格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 设置文件处理器的级别和格式
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# 将文件处理器添加到日志记录器中
app.logger.addHandler(file_handler)

# 在应用程序中记录一条日志
app.logger.info('这是一条日志信息')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.config['STATIC_FOLDER'], filename)

@app.route('/')
def index():
    info=f"host={request.host}"
    app.logger.info(f"{info=}")
    return render_template("index.html",info=info)

# 上传音频
@app.route('/upload', methods=['POST'])
def upload():
    try:
        # 获取上传的文件
        audio_file = request.files['audio']

        # 检查文件是否存在且是 WAV 格式
        if audio_file and audio_file.filename.endswith('.mp3'):
            # 保存文件到服务器指定目录
            name=f"{os.path.basename(audio_file.filename)}"
            if os.path.exists(f"{VOICE_DIR}/{name}"):
                name = f'{datetime.datetime.now().strftime("%m%d-%H%M%S")}-{name}'
            audio_file.save(f"{VOICE_DIR}/{name}")
            # 返回成功的响应
            return {'code': 0, 'message': '上传成功',"data":name}
        else:
            # 返回错误的响应
            return {'code': 1, 'message': '上传的文件不是 mp3 格式'}
    except Exception as e:
        print(f'上传错误: {e}')
        return {'code': 2, 'message': '上传失败'}

# 从 voicelist 目录获取可用的mp3声音列表
@app.route('/init')
def init():
    mp3s = glob.glob(f"{VOICE_DIR}/*.mp3")
    result = []
    for it in mp3s:
        if os.path.getsize(it) > 0:
            result.append(os.path.basename(it))
    return jsonify(result)

# 根据名称 ?name=wav文件名，返回音频的二进制数据流，用于前端shiy  /ttslist?name=文件名请求
@app.route('/ttslist')
def getfile():
    filename=request.args.get("name")
    if os.path.exists(f"{TTS_DIR}/{filename}"):
        return send_file(f"{TTS_DIR}/{filename}", as_attachment=True)
    return None
# 根据名称 ?name=mp3文件名，返回音频的二进制数据流，用于前端shiy  /ttslist?name=文件名请求
@app.route('/voicelist')
def getmp3():
    filename=request.args.get("name")
    if os.path.exists(f"{VOICE_DIR}/{filename}"):
        return send_file(f"{VOICE_DIR}/{filename}", as_attachment=True)
    return None

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
    line=0
    maxline=len(txt)
    # 行格式
    linepat=r'^\s*?\d+\s*?$'
    # 时间格式
    timepat=r'^\s*?\d+:\d+:\d+\,?\d*?\s*?-->\s*?\d+:\d+:\d+\,?\d*?$'
    txt=txt.strip().split("\n")
    # 先判断是否符合srt格式，不符合返回None
    if len(txt)<3:
        return None
    if not re.match(linepat,txt[0]) or not re.match(timepat,txt[1]):
        return None
    result=[]
    for i,t in enumerate(txt):
        # 当前行 小于等于倒数第三行 并且匹配行号，并且下一行匹配时间戳，则是行号
        if i < maxline-2 and re.match(linepat,t) and re.match(timepat,txt[i+1]):
            #   是行
            line+=1
            obj={"line":line,"time":"","text":""}
            result.append(obj)
        elif re.match(timepat,t):
            # 是时间行
            result[line-1]['time']=t
        elif len(t.strip())>0:
            # 是内容
            result[line-1]['text']+=t.strip().replace("\n",'')
    # 再次遍历，删掉美元text的行
    new_result=[]
    line=1
    for it in result:
        if "text" in it and len(it['text'].strip())>0 and not re.match(r'^[,./?`!@#$%^&*()_+=\\|\[\]{}~\s \n-]*$',it['text']):
            it['line']=line
            startraw, endraw = it['time'].strip().split(" --> ")
            start = startraw.replace(',', '.').split(":")
            start_time = int(int(start[0]) * 3600000 + int(start[1]) * 60000 + float(start[2]) * 1000)
            end = endraw.replace(',', '.').split(":")
            end_time = int(int(end[0]) * 3600000 + int(end[1]) * 60000 + float(end[2]) * 1000)
            it['startraw']=startraw
            it['endraw']=endraw
            it['start_time']=start_time
            it['end_time']=end_time
            new_result.append(it)
            line+=1
    return new_result


# 根据文本返回tts结果，返回 name=文件名字，filename=文件绝对路径
# 请求端根据需要自行选择使用哪个
@app.route('/tts', methods=['GET', 'POST'])
def tts():
    global globa_result
    # 原始字符串
    text=request.form.get("text").strip()
    voice=request.form.get("voice")
    language=request.form.get("language")

    app.logger.info(f"start->{text=}\n{voice=}\n{language=}\n\n")


    if re.match(r'^[~`!@#$%^&*()_+=,./;\':\[\]{}<>?\\|"，。？；‘：“”’｛【】｝！·￥、\s\n\r -]*$',text):
        return jsonify({"code":1,"msg":"不存在有效text，无法合成"})
    if not text or not voice or not language:
        return jsonify({"code":1,"msg":"text，voice，language 参数缺一不可"})

    # 判断是否是srt
    text_list=get_subtitle_from_srt(text)
    app.logger.info(f"{text_list=}")
    is_srt=False
    # 不是srt格式
    if text_list is None:
        text_list=[{"text":text}]
    else:
        # 是字幕
        is_srt=True
    num=0
    response_json={}
    while num<len(text_list):
        t=text_list[num]
        #换行符
        t['text']=t['text'].replace("\n",'.')
        md5_hash = hashlib.md5()
        md5_hash.update(f"{t['text']}-{voice}-{language}".encode('utf-8'))
        filename = md5_hash.hexdigest()+".wav"
        app.logger.info(f"{filename=}")
        # 合成语音
        rs=create_tts(text= t['text'],voice=voice,language=language,filename=filename)
        # 已有结果或错误，直接返回
        if rs is not None :
            if not is_srt:
                response_json=rs
                break
            else:
                text_list[num]['result']=rs

        # 循环等待 最多7200s
        time_tmp=0
        while filename not in globa_result:        
            time.sleep(10)
            time_tmp+=10
            app.logger.info(f"{time_tmp=}，{filename=}")

        # 当前行已完成合成
        if globa_result[filename]!=1:
            msg={"code":1,"msg":globa_result[filename]}
        else:
            msg={"code":0,"filename":f"{TTS_DIR}/{filename}",'name':filename}
        globa_result.pop(filename)
        if not is_srt:
            response_json=msg            
            break
        
        text_list[num]['result']=msg
        app.logger.info(f"{num=}")
        num+=1
    # 不是字幕则返回
    app.logger.info(f"{response_json=}")
    if not is_srt:
        return jsonify(response_json)
    # 继续处理字幕
    # filename=""
    filename,errors=merge_audio_segments(text_list)
    app.logger.info(f"{filename=},{errors=}")
    if filename and os.path.exists(filename) and os.path.getsize(filename)>0:
        return jsonify({"code":0,"filename":filename,"name":os.path.basename(filename),"msg":errors})
    return jsonify({"code":1,"msg":f"合成出错了:{filename=},{errors=}"})

# join all short audio to one ,eg name.mp4  name.mp4.wav
def merge_audio_segments(text_list):
    # 获得md5
    md5_hash = hashlib.md5()
    md5_hash.update(f"{json.dumps(text_list)}".encode('utf-8'))
    filename = md5_hash.hexdigest() + ".wav"
    if os.path.exists(f"{TTS_DIR}/{filename}"):
        return (f"{TTS_DIR}/{filename}","")
    segments=[]
    start_times=[]
    errors=[]
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

    merged_audio.export(f"{TTS_DIR}/{filename}", format="wav")
    return (f"{TTS_DIR}/{filename}","<-->".join(errors))


def openweb():
    time.sleep(5)
    webbrowser.open('http://127.0.0.1:9988')

if __name__ == '__main__':
    try:        
        print("地址: http://127.0.0.1:9988")
        threading.Thread(target=ttsloop).start()
        threading.Thread(target=openweb).start()
        app.run(port=9988)
    except Exception as e:
        print("执行出错:"+str(e))
