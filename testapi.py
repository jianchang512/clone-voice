import datetime
import json
import logging
import re
import threading
import time
import sys

from flask import Flask, request, render_template, jsonify, send_file, send_from_directory
import os

import glob
import hashlib
import torch
from pydub import AudioSegment
from logging.handlers import RotatingFileHandler
from TTS.api import TTS
import queue
import webbrowser

from asgiref.wsgi import WsgiToAsgi

ROOT_DIR=os.getcwd()


app = Flask(__name__,static_folder=os.path.join(ROOT_DIR, 'static'), static_url_path='/static', template_folder=os.path.join(ROOT_DIR, 'templates'))

# 配置日志
app.logger.setLevel(logging.INFO)  # 设置日志级别为 INFO

# 创建 RotatingFileHandler 对象，设置写入的文件路径和大小限制
file_handler = RotatingFileHandler(os.path.join(ROOT_DIR, 'app.log'), maxBytes=1024*1024, backupCount=5)

# 创建日志的格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 设置文件处理器的级别和格式
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# 将文件处理器添加到日志记录器中
app.logger.addHandler(file_handler)

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.config['STATIC_FOLDER'], filename)

@app.route('/')
def index():
    voice_model="yes"
    return render_template("index2.html",voice_model=voice_model,root_dir="")

asapp=WsgiToAsgi(app)

if __name__ == '__main__':
    try:        
        #print("本地web地址: http://127.0.0.1:9988")
        app.run(port=9988)
    except Exception as e:
        print("执行出错:"+str(e))
        app.logger.error(f"[app]启动出错:{str(e)}")
