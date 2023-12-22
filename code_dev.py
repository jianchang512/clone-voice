import torch
import os
os.environ['TTS_HOME']=os.getcwd()

from TTS.api import TTS

from dotenv import load_dotenv

load_dotenv()
print("源码部署需要先运行该文件，以便同意coqou-ai协议，当弹出协议时，请输入 y ")
print("同时需要连接墙外下载或更新模型，请配置全局代理 ")

device = "cuda" if torch.cuda.is_available() else "cpu"



tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

tts = TTS(model_name='voice_conversion_models/multilingual/vctk/freevc24').to(device)

