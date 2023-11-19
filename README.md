
# CV克隆声音

> 
> 这是一个声音克隆工具，可使用你的或者其他声音的音色，将一段文字合成为使用该声音说话的音频。
> 
> 使用非常简单，无需GPU，github下载预编译版本，双击 app.exe 打开一个web界面，鼠标点点快速体验，笔记本电脑就可使用，。
> 
> 支持 **中文**、**英文**、**日语**、**韩语** 4种语言，可在线从麦克风录制声音。
> 
> 为保证合成效果，建议录制时长5秒到20秒，发音清晰准确，不要存在背景噪声。
> 
> 英文效果很棒，中文效果还凑合，下载体验下吧
> 


# 视频演示

https://github.com/jianchang512/clone-voice/assets/3378335/4c180383-bbe1-4301-9890-d50fde15a339



# 使用方法

1. 下载预编译版，window 10/11,Mac下请拉取源码自行编译
2. 下载后解压到某处，比如E:/clone-voice 下
3. 双击 app.exe ，等待自动打开web窗口，如下
![](./images/1.png)
4. 输入文字，选择或录制声音，开始体验吧


# 源码部署

0. 要求 python 3.9+
1. 创建空目录，比如 E:/clone-voice
2. `git clone https://github.com/jianchang512/clone-voice .`
   [下载模型 model.pth 放到 models/tts_models--multilingual--multi-dataset--xtts_v2目录下]()
3. 创建虚拟环境 `python -m venv venv`
4. 激活环境 `cd venv/scripts`,`activate`,`cd ../..`
5. 安装依赖 `pip install -r requirements.txt`
6. 启动 `python app.py`

# 预览图

![](./images/1.png)
![](./images/2.png)


# [Youtube](https://youtu.be/NL5cIoJ9Gjo)