import time
import requests
import json

url = 'http://127.0.0.1:8001/newtask/'
path = r"C:\Users\Administrator\Downloads\0.png"
fname = '0.jpg'

arg = {"sf": 2, "n": 2, "kw": 0}
args = json.dumps(arg)
response = requests.post(url, params={"arg": args}, files={"File": (fname, open(path, 'rb').read())})
filename = response.content.decode('utf-8')
print(filename)
while True:
    response = requests.get('http://127.0.0.1:8001/dload', data={"filename": filename})
    a = response.content
    time.sleep(3)
    if len(a) <= 3:
        a = str(response.content.decode('utf-8'))
        print(a)
    else:
        f = open('./test.png', 'wb')
        f.write(a)
        f.close()
        requests.get('http://127.0.0.1:8001/del', data={"filename": filename})
