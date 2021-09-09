import asyncio
import gc
import io
import shutil
import threading
from datetime import datetime, timedelta, date

import config
from NetworkWorker import NetworkWorker
import time
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from starlette.responses import FileResponse, StreamingResponse
from config import db
from img_util import *
import spliter
from datatype import *

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
app = FastAPI()


class worker_template:
    def __init__(self, worker):
        proto = worker[0].split("://")[0]
        if proto == "http":
            self.template = NetworkWorker
        self.dest = worker[0]
        self.allowed = set(worker[1])
        self.instance = None

    def get_instance(self):
        if self.instance is None:
            self.instance = self.template(self.dest)
        return self.instance

    def shutdown(self):
        while True:
            if self.instance is None:
                break
            elif self.instance.is_idle:
                self.instance.shutdown()
                break
            else:
                print("waiting {} until idle, shutdown".format(self.instance.name))
                time.sleep(3)

    def is_idle(self):
        if self.instance is None:
            return True
        else:
            self.instance.status()
            if not self.instance.is_idle:
                return False
        return True

    def fit(self, task):
        ext = task.img.split('.')[1]
        if ext in self.allowed:
            return True


class TaskPool:
    def __init__(self):
        self.running = False
        self.pool = []
        self.workers = []
        self.exit_after = False
        self.sleeping = False
        self.workers_offline = []

    def addworker(self, workers):
        for worker in workers:
            self.workers.append(worker_template(worker))
            print('worker added')

    def get_idle_worker(self, task):
        self.running = True
        self.sleeping = False
        for worker in self.workers:
            instance = worker.get_instance()
            if not worker.instance.online:
                self.workers.remove(worker)
                self.workers_offline.append(worker)
            else:
                return instance
        return False

    def get_pool_state(self):
        count = len(self.workers)
        busy = 0
        for worker in self.workers:
            if not worker.is_idle():
                busy += 1
        utilize = int((busy / count) * 100)
        return utilize

    def worker_wake(self):
        print('waking')
        for worker in self.workers_offline:
            instance = worker.get_instance()
            instance.status()
            if instance.online:
                self.workers_offline.remove(worker)
                self.addworker(worker)

    def bg(self):
        self.running = True
        self.sleeping = False
        while len(self.pool):
            if self.exit_after:  # command exit
                return 1
            task = self.pool[0]
            instance = self.get_idle_worker(task)
            if instance:
                print("ready to rock")
                task = self.pool.pop(0)
                task.set(2)
                instance.invoke(task)
            else:
                print("all worker busy, waiting")
                self.running = False
                self.worker_wake()
                time.sleep(config.wake_interval)
        self.running = False
        return 0

    def collect(self):  # cron run this
        if self.exit_after:  # command exit
            print("exiting")
            exit(0)
        if not (len(self.pool)):
            tasks = db.collectTODO()
            if (len(tasks)):
                self.pool += tasks
                return 1
            else:
                return 0

    def sleep(self):
        if self.sleeping:
            return
        print('pool sleep triggered')
        for worker in self.workers:
            worker.shutdown()
        self.sleeping = True
        gc.collect()

    def exit(self):
        self.exit_after = True


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.SECRET_KEY, algorithm=config.ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
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
    return db.newUser(item.uname, 0, item.psw)

@app.post("/status")
async def register():
    global pool
    return


@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = db.check_username_password(form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.name}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/me/")
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user.name, current_user.tasks, current_user.t_num


@app.post("/me/newtask/")
async def file_upload(args: str, current_user: User = Depends(get_current_active_user),
                      files: UploadFile = File(...)):
    ret = []
    # print(type(files))
    if files.file:
        file = files
        filename, ext = os.path.splitext(file.filename)
        if spliter.detect(ext) != 0:
            return {"message": "failed"}
        inpath = os.path.join(config.storage, str(current_user.id), 'input')
        outpath = os.path.join(config.storage, str(current_user.id), 'output')
        os.makedirs(inpath, exist_ok=True)
        os.makedirs(outpath, exist_ok=True)
        e_filename = "{}_{}{}".format(filename, "".join(str(time.time()).split('.'))[:-2][:8], ext)
        task = Task(e_filename, args, current_user.id)
        # try:
        if True:
            res = await file.read()
            with open(task.get('input'), "wb") as f:
                f.write(res)
                f.close()
                del res
                task.commit()
                generate_preview(task)
        # except Exception as e:
        #     print(e)
        #     return {"message": "failed", 'taskid': "null"}

        # if sf < 1 or sf > 4: TODO: move to workers
        #     sf = 2
        # if noise < 0 or noise > 32:
        #     noise = 2
        # args = [noise, sf, width]
        ret.append({"message": "success", 'taskid': task.taskid})
    return ret


@app.post("/me/query/{page}")
async def task_query(page, current_user: User = Depends(get_current_active_user)):
    return db.findTasks(page, current_user.id)


@app.get("/me/dload")
async def dload(taskid: str, current_user: User = Depends(get_current_active_user)):
    task = db.picFinTask(taskid)
    if task is not None:
        if task.uid == current_user.id:
            return FileResponse(task.get('output'),
                                # media_type='application/octet-stream',
                                filename=task.img.split('.')[0]+'.png'
                                )


@app.get("/preview/{taskid}")
async def preview(taskid, current_user: User = Depends(get_current_active_user)):
    task = db.picTask(taskid)
    if task is not None:
        if task.uid == current_user.id:
            res, im_g = imReadEncode(task.get('preview'))
            return StreamingResponse(io.BytesIO(im_g.tobytes()), media_type="image/jpg")
        else:
            raise HTTPException(status_code=404, detail="not found")


@app.post("/deltask")
async def deltask(taskid: str, current_user: User = Depends(get_current_active_user)):
    task = db.picTask(taskid)
    if task is not None:
        if task.uid == current_user.id:
            db.deltask(taskid)
            shutil.rmtree(task.get('input'), ignore_errors=True)
            shutil.rmtree(task.get('output'), ignore_errors=True)
            shutil.rmtree(task.get('preview'), ignore_errors=True)
            return 'success'
        else:
            raise HTTPException(status_code=403, detail="out of range")


@app.post("/cleanall/")
async def clean(current_user: User = Depends(get_current_active_user)):
    if current_user.name in config.ops:
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


class threadTaskPool(threading.Thread):  # 继承父类threading.Thread
    def __init__(self):
        self.pool = TaskPool()
        threading.Thread.__init__(self)

    def run(self):  # 把要执行的代码写到run函数里面 线程在创建后会直接运行run函数
        self.pool.addworker(config.worker_location)
        idlecount = 0
        while True:
            if (self.pool.collect()):
                idlecount = 0
                self.pool.bg()
            else:
                idlecount += 1
            time.sleep(config.check_interval)
            if idlecount > 10:
                self.pool.sleep()
            if self.pool.exit_after:
                exit(0)


class threadAPI(threading.Thread):  # 继承父类threading.Thread
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):  # 把要执行的代码写到run函数里面 线程在创建后会直接运行run函数
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


if __name__ == "__main__":
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", "Content-Disposition"],
        expose_headers=["*", "Content-Disposition"]
    )


    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.database.connect())

    thread2 = threadAPI()
    thread2.start()
    thread1 = threadTaskPool()
    thread1.start()
    thread2.join()
    thread1.join()
