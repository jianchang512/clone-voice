import hashlib
import json
import os
import re
import time
import webbrowser

import aiohttp
import requests
from pydub import AudioSegment

import clone
from clone import cfg
from clone.cfg import langlist
from TTS.api import TTS

def updatecache():
    # 禁止更新，避免无代理时报错
    file=os.path.join(cfg.ROOT_DIR,'tts_cache/cache')
    if file:
        j=json.load(open(file,'r',encoding='utf-8'))
        for i,it in enumerate(j):
            if "time" in it and "fn" in it:
                cache_file=os.path.join(cfg.ROOT_DIR,f'tts_cache/{it["fn"]}')
                if os.path.exists(cache_file) and os.path.getsize(cache_file)>17000000:
                    it['time']=time.time()
                    j[i]=it
        json.dump(j,open(file,'w',encoding='utf-8'))



# tts 合成线程
def ttsloop():
    try:
        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(cfg.device)
        print(langlist['lang14'])
        cfg.tts_n+=1
    except aiohttp.client_exceptions.ClientOSError as e:
        print(f'{langlist["lang13"]}：{str(e)}')
        if not cfg.setorget_proxy():
            print(f'.env {langlist["lang12"]}')
        else:
            print(langlist['lang11'])
        return
    except Exception as e:
        print(f'{langlist["lang13"]}:{str(e)}')
        return

    while not cfg.exit_event.is_set():
        try:
            obj = cfg.q.get(block=True, timeout=1)
        
            print(f"[tts][ttsloop]start tts，{obj=}")
            try:
                #split_sentences=True
                tts.tts_to_file(text=obj['text'], speaker_wav=os.path.join(cfg.VOICE_DIR, obj['voice']), language=obj['language'], file_path=os.path.join(cfg.TTS_DIR, obj['filename']), split_sentences=False)
                cfg.global_tts_result[obj['filename']] = 1
                print(f"[tts][ttsloop]end: {obj=}")
            except Exception as e:
                print(f"[tts][ttsloop]error:{str(e)}")
                cfg.global_tts_result[obj['filename']] = str(e)
        except Exception:
            continue


# s t s 线程
def stsloop():
    try:
        tts = TTS(model_name='voice_conversion_models/multilingual/vctk/freevc24').to(cfg.device)
        print(langlist['lang10'])
        cfg.sts_n+=1
    except aiohttp.client_exceptions.ClientOSError as e:
        print(f'{langlist["lang9"]}：{str(e)}')
        if not cfg.setorget_proxy():
            print(f'.env {langlist["lang12"]}')
        else:
            print(f'{os.environ.get("HTTP_PROXY")} {langlist["lang11"]}')
        return
    except Exception as e:
        print(f'{langlist["lang9"]}：{str(e)}')
        return
    while not cfg.exit_event.is_set():
        try:
            obj = cfg.q_sts.get(block=True, timeout=1)        
            print(f"[sts][stsloop]start sts，{obj=}")
            try:
                #split_sentences=True
                tts.voice_conversion_to_file(source_wav=os.path.join(cfg.TMP_DIR, obj['filename']),
                                             target_wav=os.path.join(cfg.VOICE_DIR, obj['voice']),
                                             file_path=os.path.join(cfg.TTS_DIR, obj['filename']))
                cfg.global_sts_result[obj['filename']] = 1
                print(f"[sts][stsloop] end {obj=}")
            except Exception as e:
                print(f"[sts][stsloop]error:{str(e)}")
                cfg.global_sts_result[obj['filename']] = str(e)
        except Exception as e:
            continue



# 实际启动tts合成的函数
def create_tts(*, text, voice, language, filename, speed=1.0):
    absofilename = os.path.join(cfg.TTS_DIR, filename)
    if os.path.exists(absofilename) and os.path.getsize(absofilename) > 0:
        print(f"[tts][create_ts]{filename} {speed} has exists")
        cfg.global_tts_result[filename] = 1
        return {"code": 0, "filename": absofilename, 'name': filename}
    try:
        print(f"[tts][create_ts] **{text}** push queue")
        cfg.q.put({"voice": voice, "text": text,"speed":speed, "language": language, "filename": filename})
    except Exception as e:
        print(e)
        print(f"[tts][create_ts] error，{str(e)}")
        return {"code": 1, "msg": str(e)}
    return None

# join all short audio to one ,eg name.mp4  name.mp4.wav
def merge_audio_segments(text_list,is_srt=True):
    # 获得md5
    md5_hash = hashlib.md5()
    md5_hash.update(f"{json.dumps(text_list)}".encode('utf-8'))
    filename = md5_hash.hexdigest() + ".wav"
    absofilename = os.path.join(cfg.TTS_DIR, filename)
    if os.path.exists(absofilename):
        return (absofilename, "")
    segments = []
    start_times = []
    errors = []
    merged_audio = AudioSegment.empty()
    for it in text_list:
        if "filename" in it['result']:
            # 存在音频文件
            seg=AudioSegment.from_wav(it['result']['filename'])
            if "start_time" in it:
                start_times.append(it['start_time'])
                segments.append(seg)
            else:
                merged_audio+=seg
            try:
                os.unlink(it['result']['filename'])
            except:
                pass
        elif "msg" in it['result']:
            # 出错
            errors.append(it['result']['msg'])
    
    if not is_srt:
        merged_audio.export(absofilename, format="wav")
        return (absofilename, "<-->".join(errors))

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


def openweb(web_address):
    while cfg.sts_n==0 and cfg.tts_n==0:
        time.sleep(5)
    webbrowser.open("http://"+web_address)
    print(f"\n{langlist['lang8']} http://{web_address}")

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

def checkupdate():
    try:
        res=requests.get("https://raw.githubusercontent.com/jianchang512/clone-voice/main/version.json")
        print(f"{res.status_code=}")
        if res.status_code==200:
            d=res.json()
            print(f"{d=}")
            if d['version_num']>clone.VERSION:
                cfg.updatetips=f'New version {d["version"]}'
    except Exception as e:
        pass