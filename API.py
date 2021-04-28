import json
import os.path
import threading
import uuid

from fastapi import FastAPI

from realapplication import Worker



app = FastAPI()
root = 'users'
Users = {}


@app.post('/inject/')
async def inject(fname: str, uid: str):
    global w
    a = task()
    a.img = os.path.join('users', uid, 'input', fname)
    a.E_path = os.path.join('users', uid, 'output')
    a.uid = uid
    w.inject(a)
    return 1


@app.get('/status/')
async def stat(uid: str):
    global w
    if uid in w.finished.keys():
        for task in w.finished[uid]:
            Users[uid].tasks
            return Users[uid]
    else:
        return []


@app.post('/upload/')
async def upload(uid: str, picname):
    newname = uuid.uuid1() + picname
    root = os.path.join('users', uid, 'input')
    os.rename(os.path.join(root, picname), os.path.join(root, newname))
    return newname


@app.on_event('startup')
def start():
    with open('db.txt', 'r') as f:
        lines = f.readlines()
        for line in lines:
            u = json.load(line)
            n = User()
            n.uname = u.uname
            n.uid = u.uid
            n.t_num = u.t_num
            n.tasks = u.tasks
            n.finished = u.finished
            n.hashed_key = u.hashed_key
            Users[u.uid] = n
    global w
    w = Worker()
    thread = threading.Thread(target=w.invoke)
    thread.start()


@app.on_event('shutdown')
def down():
    with open('db.txt', 'w') as f:
        for user in Users.items():
            f.write(user.dump + '\n')
