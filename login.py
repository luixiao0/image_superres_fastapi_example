import os
import time
import io
import cv2
import threading, asyncio

from datetime import datetime, timedelta, date
from typing import Optional, List
from fastapi import Depends, FastAPI, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from starlette.responses import FileResponse,StreamingResponse,RedirectResponse

from datatype import User, regItem
from db_util import DBmng
from realapplication import Worker, generate_preview
import spliter
import uvicorn

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
app = FastAPI()


class TaskPool:
    def __init__(self):
        self.running = False
        self.pool = []
        self.workers = []
        self.exit_after = False

    def addworker(self, worker):
        self.workers.append(worker)

    def get_idle_worker(self):
        for worker in self.workers:
            if worker.is_idle:
                return worker
        return False

    def get_pool_state(self):
        count = len(self.workers)
        busy = 0
        for worker in self.workers:
            if not worker.is_idle:
                busy += 1
        utilize = int((busy/count)*100) # percentage of utilize
        return utilize

    def bg(self):
        self.running = True
        while len(self.pool):
            if self.exit_after:# command exit
                return 1
            worker = self.get_idle_worker()
            if worker:
                print("ready to rock")
                task = self.pool.pop(0)
                db.toState(task, 2)
                task = worker.invoke(task)
                db.taskFin(task)
            else:
                print("all worker busy, waiting")
                # no avaliable worker
                self.running = False
                time.sleep(10)
        self.running = False
        return 0

        # tasks = db.collectTODO()
        # if not len(tasks):
        #     time.sleep(10)
        #     self.pool += tasks

    def collect(self): # cron run this
        global db
        if self.exit_after:  # command exit
            print("exiting")
            exit(0)
        if not (len(self.pool)):
            tasks = db.collectTODO()
            if (len(tasks)):
                self.pool += tasks
                return 1

    def exit(self):
        self.exit_after = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = db.findUser(token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    return current_user


@app.post("/reg")
async def register(item: regItem):
    return db.newUser(item.username, 0, item.password)


@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = db.check_username_password(form_data.username, form_data.password)

    if not user:
        raise HTTPException(

            status_code=status.HTTP_401_UNAUTHORIZED,

            detail="Incorrect username or password",

            headers={"WWW-Authenticate": "Bearer"},

        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    access_token = create_access_token(

        data={"sub": user.name}, expires_delta=access_token_expires

    )

    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/me/")
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user.name, current_user.tasks, current_user.t_num


@app.post("/me/newtask/")
async def file_upload(noise: float, sf: int, width: float, current_user: User = Depends(get_current_active_user),
                      files: List[UploadFile] = File(...)):
    ret = []
    for file in files:
        filename, ext = os.path.splitext(file.filename)
        if spliter.detect(filename) != 0:
            ret.append({"message": "failed"})
            return ret
        res = await file.read()
        root = os.path.join('users', str(current_user.id), 'input')
        os.makedirs(root, exist_ok=True)
        E_path = os.path.join('users', str(current_user.id), 'output')
        os.makedirs(E_path, exist_ok=True)

        fpath = os.path.join(root, str(time.time()).split('.')[0]+ext)
        with open(fpath, "wb") as f:
            f.write(res)
        if sf < 1 or sf > 4:
            sf = 2
        if noise < 0 or noise > 32:
            noise = 2
        previewdir = generate_preview(fpath, current_user.id)
        task = db.newTask(fpath, E_path, current_user.id, noise, int(sf), width, previewdir)
        ret.append({"message": "success", 'taskid': task.taskid})
        # except Exception as e:
        #     ret.append({"message": str(e), 'taskid': -1})
    return ret


@app.post("/me/query")
async def task_query(current_user: User = Depends(get_current_active_user)):
    return db.findTasks(current_user.id)

@app.post("/me/query/single")
async def task_query(taskid: str, current_user: User = Depends(get_current_active_user)):
    return db.findTask(current_user.id, taskid)

@app.get("/me/dload")
async def dload(taskid: str, current_user: User = Depends(get_current_active_user)):
    task = db.picFinTask(taskid)
    if task is not None:
        if task.uid == current_user.id:
            name = os.path.basename(task.E_path)
            print(task.E_path, name)
            return FileResponse(task.E_path,
                                # media_type='application/octet-stream',
                                filename=str(name)
                                )


@app.get("/preview/{taskid}")
async def preview(taskid):#, current_user: User = Depends(get_current_active_user)):
    task = db.picTask(taskid)
    if task is not None:
        # if task.uid == current_user.id:
            print(task.preview)
            img = cv2.imread(task.preview)
            res, im_g = cv2.imencode(".png", img)
            return StreamingResponse(io.BytesIO(im_g.tobytes()), media_type="image/png")


@app.post("/deltask")
async def deltask(taskid: str, current_user: User = Depends(get_current_active_user)):
    task = db.picTask(taskid)
    if task is not None:
        if task.uid == current_user.id:
            db.deltask(taskid)
            try:
                os.remove(task.img)
            except:
                pass
            try:
                os.remove(task.E_path)
            except:
                pass
            return 'success'
        else:
            return 'out_of_range'

@app.post("/cleanall/")
async def clean(current_user: User = Depends(get_current_active_user)):
    if current_user.name in ops:
        tasks = db.collectFin()
        for task in tasks:
            tday = task.date.day
            delta = date.today().day - tday
            if abs(delta) > 7:  # killed over time
                print(str(task.taskid) + 'removed')
                os.remove(task.img)
                os.remove(task.E_path)
                db.deltask(task.taskid)
        return 'fin'
    else:
        return 0


if __name__ == "__main__":
    with open('ops') as f:
        ops = f.readlines()
        f.close()

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


    # to get a string like this run:
    # openssl rand -hex 32
    SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 30



    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", "Content-Disposition"],
        expose_headers=["*", "Content-Disposition"]
    )
    global db
    db = DBmng()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.database.connect())

    class threadTaskPool(threading.Thread):  # 继承父类threading.Thread
        def __init__(self):
            global pool
            pool = TaskPool()
            worker = Worker(fallback=False)
            pool.addworker(worker)
            threading.Thread.__init__(self)

        def run(self):  # 把要执行的代码写到run函数里面 线程在创建后会直接运行run函数
            global pool
            while True:
                if(pool.collect()):
                    pool.bg()
                time.sleep(10)
                if pool.exit_after:
                    exit(0)

    class threadAPI(threading.Thread):  # 继承父类threading.Thread
        def __init__(self):
            threading.Thread.__init__(self)

        def run(self):  # 把要执行的代码写到run函数里面 线程在创建后会直接运行run函数
            uvicorn.run(app, host="0.0.0.0", port=8000)

    thread2 = threadAPI()
    thread2.start()
    thread1 = threadTaskPool()
    thread1.start()
    thread1.join()