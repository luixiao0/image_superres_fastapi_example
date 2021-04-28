from db_util import DBmng
from typing import List
from datatype import User, Task
import databases
import sqlalchemy
from fastapi import FastAPI, File, UploadFile
import os
from pydantic import BaseModel

# SQLAlchemy specific code, as with any other app

a = DBmng()
app = FastAPI()



@app.on_event("startup")
async def startup():
    await a.database.connect()


@app.on_event("shutdown")
async def shutdown():
    await a.database.disconnect()


@app.get("/users/")
async def read_notes():
    return a.findUser()


@app.post('/reg')
async def reg(uname: str, psw: str):
    return a.newUser(uname, 0, psw)


@app.post("/me/newtask/")
async def file_upload(noise, sf, width,
                      file: UploadFile = File(...)):

        res = await file.read()
        root = os.path.join('users', str(0), 'input')
        os.makedirs(root, exist_ok=True)

        E_path = os.path.join('users', str(0), 'output')
        os.makedirs(E_path, exist_ok=True)
        fpath = os.path.join(root, file.filename)
        with open(fpath, "wb") as f:
            f.write(res)
        task = a.newTask(fpath, E_path, 0, noise, sf, width)
        return {"message": "success", 'taskid': task.taskid}
