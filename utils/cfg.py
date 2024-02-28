import os,sys
rootdir=os.getcwd()

ZH_PROMPT="生亦何欢，生亦何哀，不亦快哉。"

TTSMODEL_DIR=os.path.join(rootdir,'models','tts')
if not os.path.exists(TTSMODEL_DIR):
    os.makedirs(TTSMODEL_DIR,exist_ok=True)

FASTERMODEL_DIR=os.path.join(rootdir,'models','faster')
if not os.path.exists(FASTERMODEL_DIR):
    os.makedirs(FASTERMODEL_DIR,exist_ok=True)

# ffmpeg
if sys.platform == 'win32':
    os.environ['PATH'] = rootdir + f';{rootdir}\\ffmpeg;' + os.environ['PATH']
else:
    os.environ['PATH'] = rootdir + f':{rootdir}/ffmpeg:' + os.environ['PATH']
    