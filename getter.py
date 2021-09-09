import os
import time

import requests
import json

url = 'http://127.0.0.1:8001/newtask/'
# url = 'http://httpbin.org/post'
path = r"C:\Users\Administrator\Downloads\0.png"
fname = '0.jpg'

args = {"sf": 2, "n": 2, "kw": 0}
response = requests.post(url, data=args, files={"File": (fname, open(path, 'rb').read())})
filename = response.content.decode('utf-8')
# while True:
if True:
    response = requests.get('http://127.0.0.1:8001/dload', data={"filename": filename})
    a = response.content
    print(response)
    # if len(response.content) == 1:
    #     task.set(int(response.content.decode('utf-8')))
    # else:
    #     open('./test.png', 'wb').write(response.content)