from pydantic import BaseModel
from typing import Optional
import os
import json
import config

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class Task_front:
    def __init__(self, parent):
        self.id = parent.taskid
        self.s = parent.state
        self.p = parent.args
        self.date = parent.date


class Task:
    def __init__(self, filename, args, uid):
        self.img = filename
        self.args = json.loads(args)
        self.state = 0
        self.date = ""
        self.uid = uid
        self.taskid = 0

    def finished(self):
        if self.state == 1:
            return True
        else:
            return False

    def commit(self):
        task = config.db.newTask(self.img, self.uid, self.args)
        self.taskid = task.taskid
        self.date = task.date

    def set(self, state):
        if state != self.state:
            self.state = state
            config.db.toState(self.taskid, state)

    def front_dump(self):
        return Task_front(self)

    def get(self, c):
        filename, ext = self.img.split('.')
        root = os.path.join(config.storage, str(self.uid))
        if c == 'root':
            return root
        if c == 'input':
            return os.path.join(root, c, self.img)
        elif c == 'output':
            return os.path.join(root, c, "{}.png".format(filename))
        else:
            return os.path.join(root, c, "{}.jpg".format(filename))


class regItem(BaseModel):
    uname:str
    psw:str


class User(BaseModel):
    id = 0
    name = ""
    t_num = 0
    hashedkey = ""
    tasks = ""
