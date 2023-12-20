import torch
from TTS.api import TTS
import os
print("源码部署需要先运行该文件，以便同意coqou-ai协议，当弹出协议时，请输入 y ")
print("同时需要连接墙外下载或更新模型，请配置全局代理 ")
os.environ['TTS_HOME']=os.getcwd()
device = "cuda" if torch.cuda.is_available() else "cpu"

tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

tts = TTS(model_name='voice_conversion_models/multilingual/vctk/freevc24').to(device)

