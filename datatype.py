from pydantic import BaseModel


class Task(BaseModel):
    taskid = 0
    img = ""
    E_path = ""
    state = 0
    uid = 0
    noiseLevel = 0.0
    sf = 2
    customized_kernel_width = 0
    date = ""
    preview = ""

class regItem(BaseModel):
    username:str
    password:str

class User(BaseModel):
    id = 0
    name = ""
    t_num = 0
    hashedkey = ""
    tasks = ""
