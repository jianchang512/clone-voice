import torch
import os
os.environ['TTS_HOME']=os.getcwd()

from TTS.api import TTS

from dotenv import load_dotenv

load_dotenv()
'''
torch==2.1.2+cu121
torchaudio==2.1.2+cu121
pydub
flask
tts
requests
'''
'''
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
'''

print("源码部署需要先运行该文件，以便同意coqou-ai协议，当弹出协议时，请输入 y ")
print("同时需要连接墙外下载或更新模型，请配置全局代理 ")

device = "cuda" if torch.cuda.is_available() else "cpu"



tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

tts = TTS(model_name='voice_conversion_models/multilingual/vctk/freevc24').to(device)

# test
tts.tts_to_file(text='我是中国人', speaker_wav='./cn1.wav',language='zh', file_path='ha.wav')

#target_wav is voice file 
tts.voice_conversion_to_file(source_wav="./cn1.wav", target_wav="./sx1.wav", file_path="./out.wav")

