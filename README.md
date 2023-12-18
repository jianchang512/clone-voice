[加入Discord讨论](https://discord.gg/TMCM2PfHzQ) / QQ群 902124277
# CV声音克隆工具

该项目所用模型均源于 https://github.com/coqui-ai/TTS  ，模型协议为[CPML](https://coqui.ai/cpml/)只可用于学习研究，不可商用


> 
> 这是一个声音克隆工具，可使用任何人类音色，将一段文字合成为使用该音色说话的声音，或者将一个声音使用该音色转换为另一个声音。
> 
> 使用非常简单，没有N卡GPU也可以使用，下载预编译版本，双击 app.exe 打开一个web界面，鼠标点点就能用。
> 
> 支持 **中文**、**英文**、**日语**、**韩语** 4种语言，可在线从麦克风录制声音。
> 
> 为保证合成效果，建议录制时长5秒到20秒，发音清晰准确，不要存在背景噪声。
> 
> 英文效果很棒，中文效果还凑合。
> 


# 视频演示

https://github.com/jianchang512/clone-voice/assets/3378335/a0b44b50-66b5-47a1-bb13-41f9251ceda8




# 使用方法

1. 右侧[Releases](https://github.com/jianchang512/clone-voice/releases)中下载预编译版，适用于window 10/11(已含全部模型，分为3个压缩卷),Mac下请拉取源码自行编译
2. 下载后解压到某处，比如 E:/clone-voice 下
3. 双击 start.bat ，等待自动打开web窗口，如下
![](./images/0.png)

4. 转换操作步骤
	
	- 在文本框中输入文字、或导入srt文件，或者选择“声音->声音”，选择要转换的声音wav格式文件
	- 然后从“要使用的声音wav文件”下拉框中选择要用的声音，如果没有满意的，也可以点击“本地上传”按钮，选择已录制好的5-20s的wav声音文件。或者点击“开始录制”按钮，在线录制你自己的声音5-20s，录制完成点击使用
	- 点击“立即开始生成”按钮，耐心等待完成。

5. 如需GPU支持，请拉取源码本地编译



# 源码部署/以window为例，其他类似

**源码版需要全局代理，因为要从 https://huggingface.co 下载模型，而这个网址国内无法访问**

0. 要求 python 3.9+
1. 创建空目录，比如 E:/clone-voice
2. 创建虚拟环境 `python -m venv venv`
3. 激活环境 `cd venv/scripts`,`activate`,`cd ../..`
4. 安装依赖 CPU版: `pip install -r requirements.txt`, GPU版:`pip install -r requirements-gpu.txt`
5. 解压 ffmpeg.7z 到项目根目录
6. 下载模型 [**文字到语音(text-to-speech)模型**  和  **语音到语音(speect-to-speech)模型**](https://github.com/jianchang512/clone-voice/releases/tag/v0.0.1)  到项目目录下的tts文件中，然后解压到当前文件夹,或者无需手动下载，挂全局代理，在线下载
7. 启动 `python app.py`
8. CUDA支持：如果你的显卡是 Nvidia，可以根据显卡驱动版本和操作系统版本，去安装对应的 [CUDA Toolkit 11.8](https://developer.nvidia.com/cuda-downloads) ,建议预先将显卡驱动升级到最新版，再去安装。

执行 pip uninstall torch torchaudio torchvision 卸载，然后去 [https://pytorch.org/get-started/locally/](https://github.com/jianchang512/pyvideotrans/blob/main) 根据你的操作系统类型和 CUDA 版本，选择命令

![](https://private-user-images.githubusercontent.com/3378335/285566255-521d8623-fc91-43cb-bed4-e21b9b87f39d.png?jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTEiLCJleHAiOjE3MDA5MDg0MDcsIm5iZiI6MTcwMDkwODEwNywicGF0aCI6Ii8zMzc4MzM1LzI4NTU2NjI1NS01MjFkODYyMy1mYzkxLTQzY2ItYmVkNC1lMjFiOWI4N2YzOWQucG5nP1gtQW16LUFsZ29yaXRobT1BV1M0LUhNQUMtU0hBMjU2JlgtQW16LUNyZWRlbnRpYWw9QUtJQUlXTkpZQVg0Q1NWRUg1M0ElMkYyMDIzMTEyNSUyRnVzLWVhc3QtMSUyRnMzJTJGYXdzNF9yZXF1ZXN0JlgtQW16LURhdGU9MjAyMzExMjVUMTAyODI3WiZYLUFtei1FeHBpcmVzPTMwMCZYLUFtei1TaWduYXR1cmU9MDZlODIyYjc1NjgzNWM0NGM4OWY1M2Y3N2Y3OTk3OTg3NzkxODZiOWIwY2Y4NmM0NjVhMjFkMDNlY2NkZjc5NSZYLUFtei1TaWduZWRIZWFkZXJzPWhvc3QmYWN0b3JfaWQ9MCZrZXlfaWQ9MCZyZXBvX2lkPTAifQ.-WNQR73lwrc-gEHU_-aX5Us-pzeyyRKNMm-5v212CWc)

然后将 pip3 改为 pip，再复制命令去执行。

安装完毕后，在该环境里，执行 python,等待进入后，再分别执行 import torch,torch.cuda.is_available(),如果有输出，说明CUDA配置正确，否则请检查配置或者重新配置CUDA

# 模型单独下载地址

[模型下载地址](https://github.com/jianchang512/clone-voice/releases/tag/v0.0.1)



# 注意事项

模型xtts仅可用于学习研究，不可用于商业，具体见


0. 源码版需要全局代理，因为要从 https://huggingface.co 下载模型，而这个网址国内无法访问
1. 启动后需要冷加载模型，会消耗一些时间，请耐心等待显示出`http://127.0.0.1:9988`， 并自动打开浏览器页面后，稍等两三分钟后再进行转换
2. 功能有：

		文字到语音:即输入文字，用选定的音色生成声音，这个功能预编译已包含模型，开箱即用。
		
		声音到声音：即从本地选择一个音频文件，用选定的音色生成另一个音频文件，为减小预编译版体积，没有包含在内，需要单独下载模型，放在app.exe 同目录下的tts文件夹中，解压到当前文件夹下，解压后会多两个文件夹,`voice_conversion_models--multilingual--vctk--freevc24`和`wavlm`,请确保位置正确
		
3. 如果打开的cmd窗口很久不动，需要在上面按下回车才继续输出，请在cmd左上角图标上单击，选择“属性”，然后取消“快速编辑”和“插入模式”的复选框
![](./images/3.png)
![](./images/4.png)



# [Youtube演示视频](https://youtu.be/NL5cIoJ9Gjo)
