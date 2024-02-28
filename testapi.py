import requests
import os
#
# res=requests.post("http://127.0.0.1:9988/apitts",data={"text":"hello,everyone,you are my friend","language":"en"},files={"audio":open("./10.wav","rb")})
# res=requests.get("http://127.0.0.1:9988/init")
#
# print(res.text)

for t in os.listdir("f:/python/pyvideo"):
    print(t)