import torch
from TTS.api import TTS
import os
os.environ['TTS_HOME']=os.getcwd()
# Get device
device = "cuda" if torch.cuda.is_available() else "cpu"

# List available 🐸TTS models
#print(TTS().list_models())

# exit()
# Init TTS
#tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

# Run TTS
# ❗ Since this model is multi-lingual voice cloning model, we must set the target speaker_wav and language
# Text to speech list of amplitude values as output
#wav = tts.tts(text="Text to speech list of amplitude values as output!", speaker_wav="sx.mp3", language="en")
# Text to speech to a file
#['en', 'es', 'fr', 'de', 'it', 'pt', 'pl', 'tr', 'ru', 'nl', 'cs', 'ar', 'zh-cn', 'hu', 'ko', 'ja']
#tts = TTS(model_path=f"./models/tts_models--multilingual--multi-dataset--xtts_v2",config_path=f"./models/tts_models--multilingual--multi-dataset--xtts_v2/config.json").to(device)
tts = TTS(model_name='voice_conversion_models/multilingual/vctk/freevc24').to(device)
#tts = TTS(model_name='voice_conversion_models/multilingual/vctk/freevc24',model_path=f"E:/python/tts/models/voice_conversion_models--multilingual--vctk--freevc24",config_path="E:/python/tts/models/voice_conversion_models--multilingual--vctk--freevc24/config.json").to(device)
#tts.tts_to_file(text="我是中国人, 你是哪里人呢，我的朋友!", speaker_wav="cn1.mp3", language="zh-cn", file_path="output1.wav")
print(f"=======")
#tts.voice_conversion_to_file(source_wav="cn1.wav", target_wav="sx1.wav", file_path="output.wav")

#tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2"
            #model_path=f"{ROOT_DIR}/models/tts_models--multilingual--multi-dataset--xtts_v2",
            #config_path=f"{ROOT_DIR}/models/tts_models--multilingual--multi-dataset--xtts_v2/config.json"
#            ).to(device)

# pip install torch==2.0.1+cu118 torchvision=0.16.1+cu118 torchaudio===0.13.0 -f https://download.pytorch.org/whl/torch_stable.html#