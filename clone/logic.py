import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import webbrowser

import aiohttp
import requests
import torch
import torchaudio
from pydub import AudioSegment

import clone
from clone import cfg
from clone.cfg import langlist
from TTS.api import TTS
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts
from dotenv import load_dotenv
load_dotenv()

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

# 加载自定义模型 /tts/mymodels


# tts 合成线程
def ttsloop():
    try:
        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(cfg.device)
        print(langlist['lang14'])
        cfg.tts_n=1
    except aiohttp.client_exceptions.ClientOSError as e:
        print(f'{langlist["lang13"]}：{str(e)}')
        if not cfg.setorget_proxy():
            print(f'.env {langlist["lang12"]}')
        else:
            print("\n"+langlist['lang11']+"\n")
        return
    except Exception as e:
        print(f'{langlist["lang13"]}:{str(e)}')
        return

    while 1:
        try:
            obj = cfg.q.get(block=True, timeout=1)
            print(f"[tts][ttsloop]start tts，{obj=}")
            if not os.path.exists(obj['voice']):
                cfg.global_tts_result[obj['filename']] = f'参考声音不存:{obj["voice"]}'
                continue
            try:               
                tts.tts_to_file(text=obj['text'], speaker_wav=obj['voice'], language=obj['language'], file_path=os.path.join(cfg.TTS_DIR, obj['filename']))
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
        print("\n"+langlist['lang10']+"\n")
    except aiohttp.client_exceptions.ClientOSError as e:
        cfg.sts_status=False
        print(f'{langlist["lang9"]}：{str(e)}')
        if not cfg.setorget_proxy():
            print(f'.env {langlist["lang12"]}')
        else:
            print(f'{os.environ.get("HTTP_PROXY")} {langlist["lang11"]}')
        return
    except Exception as e:
        cfg.sts_status=False
        print(f'{langlist["lang9"]}：{str(e)}')
        return
    else:
        cfg.sts_status=True
    while 1:
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
def create_tts(*, text, voice, language, filename, speed=1.0,model=""):
    absofilename = os.path.join(cfg.TTS_DIR, filename)
    if os.path.exists(absofilename) and os.path.getsize(absofilename) > 0:
        print(f"[tts][create_ts]{filename} {speed} has exists")
        cfg.global_tts_result[filename] = 1
        return {"code": 0, "filename": absofilename, 'name': filename}
    try:
        print(f"[tts][create_ts] **{text}** {voice=},{model=}")
        if not model or model =="default":
            cfg.q.put({"voice": voice, "text": text,"speed":speed, "language": language, "filename": filename})
        else:
            #如果不存在该模型，就先启动
            print(f'{model=}')
            if model not in cfg.MYMODEL_QUEUE or not cfg.MYMODEL_QUEUE[model]:
                run_tts(model)
            cfg.MYMODEL_QUEUE[model].put({"text": text,"speed":speed, "language": language, "filename": filename})
    except Exception as e:
        print(e)
        print(f"error，{str(e)}")
        return {"code": 10, "msg": str(e)}
    return None

# join all short audio to one ,eg name.mp4  name.mp4.wav
def merge_audio_segments(text_list,is_srt=True):
    # 获得md5
    md5_hash = hashlib.md5()
    md5_hash.update(f"{json.dumps(text_list)}".encode('utf-8'))
    # 合成后的名字
    filename = md5_hash.hexdigest() + ".wav"
    absofilename = os.path.join(cfg.TTS_DIR, filename)
    if os.path.exists(absofilename):
        return (absofilename, "")
    segments = []
    start_times = []
    errors = []
    merged_audio = AudioSegment.empty()
    print(f'{text_list=}')
    for it in text_list:
        if "filename" in it['result'] and os.path.exists(it['result']['filename']):
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
            errors.append(str(it['result']['msg']))
    #不是srt直接返回
    if not is_srt:
        print(f'{absofilename=},{errors=}')
        merged_audio.export(absofilename, format="wav")
        return (absofilename, " | ".join(errors))

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
    return (absofilename, " | ".join(errors))


def openweb(web_address):
    while cfg.tts_n==0:
        time.sleep(5)
    try:
        webbrowser.open("http://"+web_address)
        print(f"\n{langlist['lang8']} http://{web_address}")
    except Exception as e:
        pass

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

# 将字符串或者字幕文件内容，格式化为有效字幕数组对象
# 格式化为有效的srt格式
#content是每行内容，按\n分割的，
def format_srt(content):
    #去掉空行
    content=[it for it in content if it.strip()]
    if len(content)<1:
        return []
    result=[]
    maxindex=len(content)-1
    # 时间格式
    timepat = r'^\s*?\d+:\d+:\d+([\,\.]\d+?)?\s*?-->\s*?\d+:\d+:\d+([\,\.]\d+?)?\s*?$'
    textpat=r'^[,./?`!@#$%^&*()_+=\\|\[\]{}~\s \n-]*$'
    for i,it in enumerate(content):
        #当前空行跳过
        if not it.strip():
            continue
        it=it.strip()
        is_time=re.match(timepat,it)
        if is_time:
            #当前行是时间格式，则添加
            result.append({"time":it,"text":[]})
        elif i==0:
            #当前是第一行，并且不是时间格式，跳过
            continue
        elif re.match(r'^\s*?\d+\s*?$',it) and i<maxindex and re.match(timepat,content[i+1]):
            #当前不是时间格式，不是第一行，并且都是数字，并且下一行是时间格式，则当前是行号，跳过
            continue
        elif len(result)>0 and not re.match(textpat,it):
            #当前不是时间格式，不是第一行，（不是行号），并且result中存在数据，则是内容，可加入最后一个数据
            result[-1]['text'].append(it)
    #再次遍历，去掉text为空的
    result=[it for it in result if len(it['text'])>0]

    if len(result)>0:
        for i,it in enumerate(result):
            result[i]['line']=i+1
            result[i]['text']="\n".join(it['text'])
            s,e=(it['time'].replace('.',',')).split('-->')
            s=s.strip()
            e=e.strip()
            if s.find(',')==-1:
                s+=',000'
            if len(s.split(':')[0])<2:
                s=f'0{s}'
            if e.find(',')==-1:
                e+=',000'
            if len(e.split(':')[0])<2:
                e=f'0{e}'
            result[i]['time']=f'{s} --> {e}'
    return result


def get_subtitle_from_srt(srtfile):
    timepat = r'^\s*?\d+:\d+:\d+(\,\d+?)?\s*?-->\s*?\d+:\d+:\d+(\,\d+?)?\s*?$'
    if not re.search(timepat,srtfile,re.I|re.M):
        return None
    content = srtfile.strip().splitlines()
    if len(content)<1:
        return None
    result=format_srt(content)
    if len(result)<1:
        return None

    new_result = []
    line = 1
    for it in result:
        if "text" in it and len(it['text'].strip()) > 0:
            it['line'] = line
            startraw, endraw = it['time'].strip().split("-->")
            start = startraw.strip().replace(',', '.').replace('，','.').replace('：',':').split(":")
            end = endraw.strip().replace(',', '.').replace('，','.').replace('：',':').split(":")
            start_time = int(int(start[0]) * 3600000 + int(start[1]) * 60000 + float(start[2]) * 1000)
            end_time = int(int(end[0]) * 3600000 + int(end[1]) * 60000 + float(end[2]) * 1000)
            it['startraw'] = startraw
            it['endraw'] = endraw
            it['start_time'] = start_time
            it['end_time'] = end_time
            new_result.append(it)
            line += 1
    return new_result



def get_subtitle_from_srt0(txt):
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
        #print(f"{res.status_code=}")
        if res.status_code==200:
            d=res.json()
            #print(f"{d=}")
            if d['version_num']>clone.VERSION:
                cfg.updatetips=f'New version {d["version"]}'
    except Exception as e:
        pass

def clear_gpu_cache():
    # clear the GPU cache
    if torch.cuda.is_available():
        torch.cuda.empty_cache()



# 加载自定义模型,name是文件夹名， tts/mymodels/name/
def load_model(name):
    print(f'load_model,{name=}')
    while cfg.MYMODEL_OBJS[name]=="loading":
        time.sleep(3)
    
    xtts_checkpoint, xtts_config, xtts_vocab=os.path.join(cfg.MYMODEL_DIR,name,'model.pth'),os.path.join(cfg.MYMODEL_DIR,name,'config.json'),os.path.join(cfg.MYMODEL_DIR,name,'vocab.json')
    clear_gpu_cache()
    print(f'{xtts_checkpoint=},{xtts_config=},{xtts_vocab=}')
    if cfg.MYMODEL_OBJS[name]=="no" or not os.path.exists(xtts_checkpoint) or not os.path.exists(xtts_config) or not os.path.exists(xtts_vocab):
        cfg.MYMODEL_OBJS[name]="no"
        return "自定义模型下不存在 model.pth或config.json/vocab.json 文件!!"
    if cfg.MYMODEL_OBJS[name]=="error":
        return "模型启动时出错，请重试"
    if cfg.MYMODEL_OBJS[name] and not isinstance(cfg.MYMODEL_OBJS[name],str):
        return "已启动"
    
    cfg.MYMODEL_OBJS[name]="loading"
    try:
        cfg.MYMODEL_QUEUE[name]=queue.Queue(1000)
        config = XttsConfig()
        config.load_json(xtts_config)
        cfg.MYMODEL_OBJS[name] = Xtts.init_from_config(config)
        print("Loading XTTS model! ")
        
        cfg.MYMODEL_OBJS[name].load_checkpoint(config, checkpoint_path=xtts_checkpoint, vocab_path=xtts_vocab, use_deepspeed=False)
        if torch.cuda.is_available():
            cfg.MYMODEL_OBJS[name].cuda()
        threading.Thread(target=run_tts,args=(name,)).start()
    except Exception as e:
        cfg.MYMODEL_QUEUE[name]=None
        cfg.MYMODEL_OBJS[name]="error"
        return str(e)
    return "启动成功!"

def run_tts(name):
    while 1:
        if not cfg.MYMODEL_OBJS[name]:
            load_model(name)
            time.sleep(5)
            continue
        if cfg.MYMODEL_OBJS[name]=='no':
            print(f"自定义模型 {name} 下不存在model.pth或config.json/vocab.json文件!!")
            break
        if cfg.MYMODEL_OBJS[name]=='error':
            print(f"加载自定义模型 {name} 时出错!!")
            break
        if cfg.MYMODEL_OBJS[name]=='loading':
            time.sleep(10)
            continue
        try:
            obj = cfg.MYMODEL_QUEUE[name].get(block=True, timeout=1)
        except:
            time.sleep(1)
            continue
        try:
            print(f'{obj=}')
            lang, tts_text, speaker_audio_file=obj['language'],obj['text'],os.path.join(cfg.MYMODEL_DIR,name,'base.wav')
            gpt_cond_latent, speaker_embedding = cfg.MYMODEL_OBJS[name].get_conditioning_latents(audio_path=speaker_audio_file, gpt_cond_len=cfg.MYMODEL_OBJS[name].config.gpt_cond_len, max_ref_length=cfg.MYMODEL_OBJS[name].config.max_ref_len, sound_norm_refs=cfg.MYMODEL_OBJS[name].config.sound_norm_refs)
            out = cfg.MYMODEL_OBJS[name].inference(
                text=tts_text,
                language=lang,
                gpt_cond_latent=gpt_cond_latent,
                speaker_embedding=speaker_embedding,
                temperature=cfg.MYMODEL_OBJS[name].config.temperature, # Add custom parameters here
                length_penalty=cfg.MYMODEL_OBJS[name].config.length_penalty,
                repetition_penalty=cfg.MYMODEL_OBJS[name].config.repetition_penalty,
                top_k=cfg.MYMODEL_OBJS[name].config.top_k,
                top_p=cfg.MYMODEL_OBJS[name].config.top_p,
            )
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fp:
                out["wav"] = torch.tensor(out["wav"]).unsqueeze(0)
                out_path = fp.name
                torchaudio.save(out_path, out["wav"], 24000)
                shutil.copy2(out_path,os.path.join(cfg.TTS_DIR, obj['filename']))
            cfg.global_tts_result[obj['filename']] = 1
        except Exception as e:
            #出错了
            print(f'run_tts:{name=},{str(e)}')


