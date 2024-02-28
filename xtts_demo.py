import argparse
import os
import sys
import tempfile

import gradio as gr
import librosa.display
import numpy as np

import os
import torch
import torchaudio
import traceback
from TTS.demos.xtts_ft_demo.utils.formatter import format_audio_list
from TTS.demos.xtts_ft_demo.utils.gpt_train import train_gpt

from TTS.demos.xtts_ft_demo.utils.cfg import TTSMODEL_DIR

from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts


def clear_gpu_cache():
    # clear the GPU cache
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

XTTS_MODEL = None
def load_model(xtts_checkpoint, xtts_config, xtts_vocab):
    global XTTS_MODEL
    clear_gpu_cache()
    if not xtts_checkpoint or not xtts_config or not xtts_vocab:
        return "You need to run the previous steps or manually set the `XTTS checkpoint path`, `XTTS config path`, and `XTTS vocab path` fields !!"
    config = XttsConfig()
    config.load_json(xtts_config)
    XTTS_MODEL = Xtts.init_from_config(config)
    print("Loading XTTS model! ")
    XTTS_MODEL.load_checkpoint(config, checkpoint_path=xtts_checkpoint, vocab_path=xtts_vocab, use_deepspeed=False)
    if torch.cuda.is_available():
        XTTS_MODEL.cuda()

    print("Model Loaded!")
    return "Model Loaded!"

def run_tts(lang, tts_text, speaker_audio_file):
    if XTTS_MODEL is None or not speaker_audio_file:
        return "You need to run the previous step to load the model !!", None, None

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

    return "Speech generated !", out_path, speaker_audio_file




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


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="""XTTS fine-tuning demo\n\n"""
        """
        Example runs:
        set http_proxy=http://127.0.0.1:10809

        python TTS/demos/xtts_ft_demo/xtts_demo.py --port 
        """,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Port to run the gradio demo. Default: 5003",
        default=5003,
    )
    parser.add_argument(
        "--out_path",
        type=str,
        help="Output path (where data and checkpoints will be saved) Default: /tmp/xtts_ft/",
        default=TTSMODEL_DIR,
    )

    parser.add_argument(
        "--num_epochs",
        type=int,
        help="Number of epochs to train. Default: 10",
        default=10,
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        help="Batch size. Default: 4",
        default=4,
    )
    parser.add_argument(
        "--grad_acumm",
        type=int,
        help="Grad accumulation steps. Default: 1",
        default=1,
    )
    parser.add_argument(
        "--max_audio_length",
        type=int,
        help="Max permitted audio size in seconds. Default: 11",
        default=10,
    )

    args = parser.parse_args()

    with gr.Blocks() as demo:
        with gr.Tab("开始训练"):
            model_name = gr.Textbox(
                        label="保存模型名(只允许英文/数字/下S划线):",
                        value="",
            )
            upload_file = gr.File(
                file_count="multiple",
                label="选择训练素材音频文件，仅包含同一个人声，无背景噪声(wav, mp3, and flac)",
            )
            with gr.Row() as r1:
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
                progress_data = gr.Label(
                    label="进度:"
                )
            logs = gr.Textbox(
                label="日志:",
                interactive=False,
            )
            demo.load(read_logs, None, logs, every=1)

            prompt_compute_btn = gr.Button(value="开始训练")
            def train_model(language, train_csv, eval_csv, num_epochs, batch_size, grad_acumm, output_path, max_audio_length):
                clear_gpu_cache()
                if not train_csv or not eval_csv:
                    return "不存在有效的csv文件 !", "", "", "", ""
                try:
                    # convert seconds to waveform frames
                    max_audio_length = int(max_audio_length * 22050)
                    config_path, original_xtts_checkpoint, vocab_file, exp_path, speaker_wav = train_gpt(language, num_epochs, batch_size, grad_acumm, train_csv, eval_csv, output_path=output_path, max_audio_length=max_audio_length)
                except:
                    traceback.print_exc()
                    error = traceback.format_exc()
                    return f"训练出错了: {error}", "", "", "", ""

                # copy original files to avoid parameters changes issues
                os.system(f"cp {config_path} {exp_path}")
                os.system(f"cp {vocab_file} {exp_path}")

                ft_xtts_checkpoint = os.path.join(exp_path, "model.pth")
                print("训练完毕!")
                clear_gpu_cache()
                return "训练完毕!", config_path, vocab_file, ft_xtts_checkpoint, speaker_wav
        
            def preprocess_dataset(audio_path, language,  progress=gr.Progress(track_tqdm=True)):
                clear_gpu_cache()
                out_path = os.path.join(args.out_path, "dataset")
                os.makedirs(out_path, exist_ok=True)
                
                try:
                    train_meta, eval_meta, audio_total_size = format_audio_list(audio_path, target_language=language, out_path=out_path, gradio_progress=progress)
                except:
                    traceback.print_exc()
                    error = traceback.format_exc()
                    return f"处理训练数据出错了! \n Error summary: {error}", "", "","",""

                clear_gpu_cache()

                # if audio total len is less than 2 minutes raise an error
                if audio_total_size < 120:
                    message = "素材总时长不得小于2分钟!"
                    print(message)
                    return message, "", "","",""

                print("数据处理完毕，开始训练!")
                msg, config_path, vocab_file, ft_xtts_checkpoint, speaker_wav=train_model(language, train_meta, eval_meta, args.num_epochs, args.batch_size, args.grad_acumm, args.out_path, args.max_audio_length)
                progress_data, xtts_config, xtts_vocab, xtts_checkpoint, speaker_reference_audio
                msg=load_model(
                    ft_xtts_checkpoint,
                    config_path,
                    vocab_file
                )
                
                return msg, config_path, vocab_file, ft_xtts_checkpoint, speaker_wav

        with gr.Tab("使用已训练好的模型"):
            with gr.Row():
                with gr.Column() as col1:
                    xtts_checkpoint = gr.Textbox(
                        label="XTTS checkpoint path:",
                        value="",
                    )
                    xtts_config = gr.Textbox(
                        label="XTTS config path:",
                        value="",
                    )

                    xtts_vocab = gr.Textbox(
                        label="XTTS vocab path:",
                        value="",
                    )
                    progress_load = gr.Label(
                        label="进度:"
                    )
                    load_btn = gr.Button(value="Step 3 - Load Fine-tuned XTTS model")

                with gr.Column() as col2:
                    speaker_reference_audio = gr.Textbox(
                        label="参考音频:",
                        value="",
                    )
                    tts_language = gr.Dropdown(
                        label="Language",
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
                        value="你好啊，亲爱的朋友.",
                    )
                    tts_btn = gr.Button(value="生成声音")

                with gr.Column() as col3:
                    progress_gen = gr.Label(
                        label="进度:"
                    )
                    tts_output_audio = gr.Audio(label="生成的声音.")
                    reference_audio = gr.Audio(label="参考音频.")

            prompt_compute_btn.click(
                fn=preprocess_dataset,
                inputs=[
                    upload_file,
                    lang
                ],
                outputs=[
                    progress_data, xtts_config, xtts_vocab, xtts_checkpoint, speaker_reference_audio
                ],
            )

           

            tts_btn.click(
                fn=run_tts,
                inputs=[
                    tts_language,
                    tts_text,
                    speaker_reference_audio,
                ],
                outputs=[progress_gen, tts_output_audio, reference_audio],
            )

    demo.launch(
        share=True,
        debug=False,
        server_port=args.port,
        server_name="0.0.0.0"
    )
