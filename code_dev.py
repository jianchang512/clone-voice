import torch
import os
os.environ['TTS_HOME']=os.getcwd()

from TTS.api import TTS

from dotenv import load_dotenv

load_dotenv()
print(os.environ.get('HTTP_PROXY'))
# exit()
print("源码部署需要先运行该文件，以便同意coqou-ai协议，当弹出协议时，请输入 y ")
print("同时需要连接墙外下载或更新模型，请在 .env 中 HTTP_PROXY=设置代理地址")


device = "cuda" if torch.cuda.is_available() else "cpu"



tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

tts = TTS(model_name='voice_conversion_models/multilingual/vctk/freevc24').to(device)

# test
#tts.tts_to_file(text='我是中国人，你呢我的宝贝。今天天气看起来很不错啊', speaker_wav='./cn1.wav',language='zh', file_path='hafalse2.wav', speed=2.0,split_sentences=False)

#tts.tts_to_file(text='我是中国人，你呢我的宝贝。今天天气看起来很不错啊', speaker_wav='./cn1.wav',language='zh', file_path='hafalse0.2.wav', speed=0.2,split_sentences=False)

#target_wav is voice file 
# tts.voice_conversion_to_file(source_wav="./cn1.wav", target_wav="./sx1.wav", file_path="./out.wav")



