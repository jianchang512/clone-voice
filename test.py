
import os
import re


def get_models(path):
    objs={}
    for it in os.listdir(path):
        if re.match(r'^[0-9a-zA-Z_-]+$',it):
            objs[it]=None
    return objs

print(get_models(r'E:\python\tts\tts\mymodels\xiaoyi'))