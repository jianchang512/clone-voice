import datetime
import json
import logging
import re
import shutil
import threading
import time

from flask import Flask, request, render_template, jsonify, send_file
import os
import glob
import hashlib
import torch
from pydub import AudioSegment
from logging.handlers import RotatingFileHandler


from TTS.api import TTS
import queue
import webbrowser

shutil.copytree("./venv/Lib/site-packages/numpy-1.26.2.dist-info","./dist/app/_internal/numpy-1.26.2.dist-info",dirs_exist_ok=True)
shutil.copytree("./venv/Lib/site-packages/packaging-23.2.dist-info","./dist/app/_internal/packaging-23.2.dist-info",dirs_exist_ok=True)
shutil.copytree("./venv/Lib/site-packages/PyYAML-6.0.1.dist-info","./dist/app/_internal/PyYAML-6.0.1.dist-info",dirs_exist_ok=True)
shutil.copytree("./venv/Lib/site-packages/regex-2023.10.3.dist-info","./dist/app/_internal/regex-2023.10.3.dist-info",dirs_exist_ok=True)
shutil.copytree("./venv/Lib/site-packages/requests-2.31.0.dist-info","./dist/app/_internal/requests-2.31.0.dist-info",dirs_exist_ok=True)
shutil.copytree("./venv/Lib/site-packages/safetensors-0.4.0.dist-info","./dist/app/_internal/safetensors-0.4.0.dist-info",dirs_exist_ok=True)
shutil.copytree("./venv/Lib/site-packages/torch","./dist/app/_internal/torch",dirs_exist_ok=True)
shutil.copytree("./venv/Lib/site-packages/torch-2.1.1.dist-info","./dist/app/_internal/torch-2.1.1.dist-info",dirs_exist_ok=True)
shutil.copytree("./venv/Lib/site-packages/tqdm-4.66.1.dist-info","./dist/app/_internal/tqdm-4.66.1.dist-info",dirs_exist_ok=True)
shutil.copytree("./venv/Lib/site-packages/trainer","./dist/app/_internal/trainer",dirs_exist_ok=True)
shutil.copytree("./venv/Lib/site-packages/trainer-0.0.32.dist-info","./dist/app/_internal/trainer-0.0.32.dist-info",dirs_exist_ok=True)
shutil.copytree("./venv/Lib/site-packages/transformers","./dist/app/_internal/transformers",dirs_exist_ok=True)
shutil.copytree("./venv/Lib/site-packages/transformers-4.35.2.dist-info","./dist/app/_internal/transformers-4.35.2.dist-info",dirs_exist_ok=True)
shutil.copytree("./venv/Lib/site-packages/TTS-0.20.6.dist-info","./dist/app/_internal/TTS-0.20.6.dist-info",dirs_exist_ok=True)
shutil.copytree("./venv/Lib/site-packages/TTS","./dist/app/_internal/TTS",dirs_exist_ok=True)

shutil.copytree("./tts","./dist/app/tts",dirs_exist_ok=True)
shutil.copytree("./tts_cache","./dist/app/tts_cache",dirs_exist_ok=True)
shutil.copytree("./static","./dist/app/static",dirs_exist_ok=True)
shutil.copytree("./templates","./dist/app/templates",dirs_exist_ok=True)