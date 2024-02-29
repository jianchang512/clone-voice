import argparse
import os
import sys
import tempfile
import threading
import webbrowser
import time

import gradio as gr
import librosa.display
import numpy as np

import os
import torch
import torchaudio
import traceback
from utils.formatter import format_audio_list
from utils.cfg import TTSMODEL_DIR
from TTS.demos.xtts_ft_demo.utils.gpt_train import train_gpt


from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts
import datetime
import shutil
import json
import random
from dotenv import load_dotenv
load_dotenv()

proxy=os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
if proxy:
    os.environ['HTTP_PROXY']=proxy
    os.environ['HTTPS_PROXY']=proxy

print(f'{proxy=}')


#dataset目录名
dataset_name=f'dataset{int(random.random()*1000000)}'

def clear_gpu_cache():
    # clear the GPU cache
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

XTTS_MODEL = None
def load_model(xtts_checkpoint, xtts_config, xtts_vocab):
    global XTTS_MODEL
    clear_gpu_cache()
    if not xtts_checkpoint or not xtts_config or not xtts_vocab:
        gr.Error('训练尚未结束，请稍等')
        return "训练尚未结束，请稍等"
    config = XttsConfig()
    config.load_json(xtts_config)
    XTTS_MODEL = Xtts.init_from_config(config)
    print("Loading XTTS model! ")
    XTTS_MODEL.load_checkpoint(config, checkpoint_path=xtts_checkpoint, vocab_path=xtts_vocab, use_deepspeed=False)
    if torch.cuda.is_available():
        XTTS_MODEL.cuda()

    print("Model Loaded!")
    return "模型已加载!"

def run_tts(lang, tts_text, speaker_audio_file):
    if XTTS_MODEL is None:
        gr.Error("模型还未训练完毕或尚未加载，请稍等")
        return "模型还未训练完毕或尚未加载，请稍等 !!", None, None
    if speaker_audio_file and not speaker_audio_file.endswith(".wav"):
        speaker_audio_file+='.wav'
    if not speaker_audio_file or  not os.path.exists(speaker_audio_file):
        gr.Error('必须填写参考音频')
        return '必须填写参考音频',None,None
    gpt_cond_latent, speaker_embedding = XTTS_MODEL.get_conditioning_latents(audio_path=speaker_audio_file, gpt_cond_len=XTTS_MODEL.config.gpt_cond_len, max_ref_length=XTTS_MODEL.config.max_ref_len, sound_norm_refs=XTTS_MODEL.config.sound_norm_refs)
    out = XTTS_MODEL.inference(
        text=tts_text,
        language=lang,
        gpt_cond_latent=gpt_cond_latent,
        speaker_embedding=speaker_embedding,
        temperature=XTTS_MODEL.config.temperature, # Add custom parameters here
        length_penalty=XTTS_MODEL.config.length_penalty,
        repetition_penalty=XTTS_MODEL.config.repetition_penalty,
        top_k=XTTS_MODEL.config.top_k,
        top_p=XTTS_MODEL.config.top_p,
    )

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fp:
        out["wav"] = torch.tensor(out["wav"]).unsqueeze(0)
        out_path = fp.name
        torchaudio.save(out_path, out["wav"], 24000)

    return "已创建好了声音 !", out_path, speaker_audio_file




# define a logger to redirect 
class Logger:
    def __init__(self, filename="log.out"):
        self.log_file = filename
        self.terminal = sys.stdout
        self.log = open(self.log_file, "w")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def isatty(self):
        return False

# redirect stdout and stderr to a file
sys.stdout = Logger()
sys.stderr = sys.stdout


# logging.basicConfig(stream=sys.stdout, level=logging.INFO)
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def read_logs():
    sys.stdout.flush()
    with open(sys.stdout.log_file, "r") as f:
        return f.read()

def openweb(port):
    time.sleep(10)
    webbrowser.open(f"http://127.0.0.1:{port}")

if __name__ == "__main__":
    date=datetime.datetime.now()
    param_file=os.path.join(os.getcwd(),'params.json')
    if not os.path.exists(param_file):
        print('不存在配音文件 params.json')
        sys.exit()
    args=json.load(open(param_file,'r',encoding='utf-8'))
    args['out_path']=TTSMODEL_DIR

    with gr.Blocks(css="ul.options[role='listbox']{background:#ffffff}",title="clone-voice trainer") as demo:
        if not proxy:
            gr.Markdown("""**没有配置代理，训练中可能出错，建议在.env文件中 `HTTP_PROXY=`后填写代理地址**""")
        with gr.Tab("训练平台"):
            with gr.Row() as r1:
                model_name= gr.Textbox(
                        label="训练后模型名称(限英文/数字/下划线，禁止空格或特殊符号):",
                        value=f"model{date.day}{date.hour}{date.minute}",
                )
                lang = gr.Dropdown(
                    label="音频发声语言",
                    value="zh",
                    choices=[
                        "zh",
                        "en",
                        "es",
                        "fr",
                        "de",
                        "it",
                        "pt",
                        "pl",
                        "tr",
                        "ru",
                        "nl",
                        "cs",
                        "ar",
                        "hu",
                        "ko",
                        "ja"
                    ],
                )
            with gr.Row() as r1:
                upload_file = gr.File(
                    file_count="multiple",
                    label="选择训练素材音频文件(可多个)，仅可包含同一个人声，并且无背景噪声(wav, mp3, and flac)",
                )
                logs = gr.Textbox(
                    label="日志:",
                    interactive=False,
                )
                demo.load(read_logs, None, logs, every=1)

            prompt_compute_btn = gr.Button(value="第一步：上传音频文件后点击开始整理数据")
            with gr.Row() as r1:
                train_data = gr.Textbox(
                    label="待训练数据集/可修改识别出的文字以便效果更好:",
                    interactive=True,
                    lines=20,
                    placeholder="第一步结束后，会自动在此显示整理好的文字，可修改错别字，以便取得更好效果"
                )
                eval_data = gr.Textbox(
                    label="验证数据集/可修改识别出的文字以便效果概念股或:",
                    interactive=True,
                    lines=20,
                    placeholder="第一步结束后，会自动在此显示整理好的文字，可修改错别字，以便取得更好效果"
                )
            with gr.Row() as r:
                train_file=gr.Textbox(
                    label="待训练数据集csv文件:",
                    interactive=False,
                    visible=False
                    
                )
                eval_file=gr.Textbox(
                    label="验证数据集csv文件:",
                    interactive=False,
                    visible=False
                )
            
            start_train_btn = gr.Button(value="第二步：修改错别字后(或不修改)，点击启动训练")
            
            with gr.Row():
                with gr.Column() as col1:
                    xtts_checkpoint = gr.Textbox(
                        label="训练后模型保存路径:",
                        value="",
                        interactive=False,
                        visible=False
                    )
                    xtts_config = gr.Textbox(
                        label="训练后模型配置文件:",
                        value="",
                        interactive=False,
                        visible=False
                    )

                    xtts_vocab = gr.Textbox(
                        label="vocab文件:",
                        value="",
                        interactive=False,
                        visible=False
                    )
            
            with gr.Row():
                with gr.Column() as col2:
                    speaker_reference_audio = gr.Textbox(
                        label="参考音频/第二步结束后自动填充:",
                        value="",
                        placeholder=f"第二步结束后可以到{os.path.join(args['out_path'], dataset_name,'wavs')}目录下，找到质量更好音频替换"
                    )
                    tts_language = gr.Dropdown(
                        label="文字语言",
                        value="zh",
                        choices=[
                            "zh",
                            "en",
                            "es",
                            "fr",
                            "de",
                            "it",
                            "pt",
                            "pl",
                            "tr",
                            "ru",
                            "nl",
                            "cs",
                            "ar",
                            "hu",
                            "ko",
                            "ja",
                        ]
                    )
                    tts_text = gr.Textbox(
                        label="输入要合成的文字.",
                        value="你好啊，我亲爱的朋友.",
                    )                   

                with gr.Column() as col3:
                    tts_output_audio = gr.Audio(label="生成的声音.")
                    reference_audio = gr.Audio(label="作为参考的音频.")
            tts_btn = gr.Button(value="第三步：自动填充参考音频后，点击测试模型效果")
            copy_label=gr.Label(label="")
            move_btn = gr.Button(value="第四步：效果如果满意，点击复制到clone-voice中使用它")
            
            

            def train_model(language, train_text, eval_text,trainfile,evalfile):
                clear_gpu_cache()
                if not trainfile or not evalfile:
                    gr.Error("请等待数据处理完毕，目前不存在有效的训练数据集!")
                    return "请等待数据处理完毕，目前不存在有效的训练数据集!","", "", "", ""
                try:
                    with open(trainfile,'w',encoding='utf-8') as f:
                        f.write(train_text.replace('\r\n','\n'))
                    with open(evalfile,'w',encoding='utf-8') as f:
                        f.write(eval_text.replace('\r\n','\n'))
                    
                    print(f'{trainfile=}')
                    print(f'{evalfile=}')
                    #sys.exit()
                    # convert seconds to waveform frames
                    max_audio_length = int(args['max_audio_length'] * 22050)
                    config_path, original_xtts_checkpoint, vocab_file, exp_path, speaker_wav = train_gpt(language, args['num_epochs'], args['batch_size'], args['grad_acumm'], trainfile, evalfile, output_path=args['out_path'], max_audio_length=max_audio_length)
                except:
                    traceback.print_exc()
                    error = traceback.format_exc()
                    print(error)
                    gr.Error(f"训练出错了: {error}")
                    return f"训练出错了: {error}","", "", "", ""

                # copy original files to avoid parameters changes issues
                shutil.copy2(config_path,exp_path)
                shutil.copy2(vocab_file,exp_path)

                ft_xtts_checkpoint = os.path.join(exp_path, "best_model.pth")
                print("训练完毕!")
                clear_gpu_cache()               
                
                msg=load_model(
                    ft_xtts_checkpoint,
                    config_path,
                    vocab_file
                )
                gr.Info("训练完毕，可以测试了")
                return "训练完毕，可以测试了",config_path, vocab_file, ft_xtts_checkpoint, speaker_wav
        
            # 处理数据集
            def preprocess_dataset(audio_path, language,  progress=gr.Progress(track_tqdm=True)):
                clear_gpu_cache()
                out_path = os.path.join(args['out_path'], dataset_name)
                os.makedirs(out_path, exist_ok=True)
                
                try:
                    train_meta, eval_meta, audio_total_size = format_audio_list(audio_path, target_language=language, out_path=out_path, gradio_progress=progress)
                except:
                    traceback.print_exc()
                    error = traceback.format_exc()
                    gr.Error(f"处理训练数据出错了! \n Error summary: {error}")
                    return "", "","",""

                clear_gpu_cache()

                # if audio total len is less than 2 minutes raise an error
                if audio_total_size < 120:
                    message = "素材总时长不得小于2分钟!"
                    print(message)
                    gr.Error(message)
                    return "", "","",""

                print("数据处理完毕，开始训练!")
                
                traindata=""
                evaldata=""
                with open(train_meta,'r',encoding="utf-8") as f:
                    traindata=f.read()
                with open(eval_meta,'r',encoding="utf-8") as f:
                    evaldata=f.read()
                return traindata,evaldata,train_meta,eval_meta
                
            
            # 复制到clone
            def move_to_clone(model_name,model_file,vocab,cfg,audio_file):
                if not audio_file or not os.path.exists(audio_file):
                    gr.Warning("必须填写参考音频")
                    return "必须填写参考音频"
                gr.Info('开始复制到clone自定义模型下，请耐心等待提示完成')
                print(f'{model_name=}')
                print(f'{model_file=}')
                print(f'{vocab=}')
                print(f'{cfg=}')
                print(f'{audio_file=}')
                model_dir=os.path.join(os.getcwd(),f'models/mymodels/{model_name}')
                os.makedirs(model_dir,exist_ok=True)
                shutil.copy2(model_file,os.path.join(model_dir,'model.pth'))
                shutil.copy2(vocab,os.path.join(model_dir,'vocab.json'))
                shutil.copy2(cfg,os.path.join(model_dir,'config.json'))
                shutil.copy2(audio_file,os.path.join(model_dir,'base.wav'))
                gr.Info('已复制到clone自定义模型目录下了，可以去使用咯')
                return "已复制到clone自定义模型目录下了，可以去使用咯"
            
            move_btn.click(
                fn=move_to_clone,
                inputs=[
                    model_name,
                    xtts_checkpoint,
                    xtts_vocab,
                    xtts_config,
                    speaker_reference_audio
                ],
                outputs=[
                    copy_label
                ]
            )
            
            prompt_compute_btn.click(
                fn=preprocess_dataset,
                inputs=[
                    upload_file,
                    lang
                ],
                outputs=[
                    train_data,eval_data,train_file,eval_file
                ],
            )
            
            start_train_btn.click(
                fn=train_model,
                inputs=[lang,train_data,eval_data,train_file,eval_file],
                outputs=[copy_label,xtts_config, xtts_vocab, xtts_checkpoint, speaker_reference_audio]
            )

           

            tts_btn.click(
                fn=run_tts,
                inputs=[
                    tts_language,
                    tts_text,
                    speaker_reference_audio,
                ],
                outputs=[copy_label,tts_output_audio, reference_audio],
            )
            
    threading.Thread(target=openweb,args=(args['port'],)).start()
    demo.launch(
        share=True,
        debug=False,
        server_port=args['port'],
        server_name="0.0.0.0"
    )
