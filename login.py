import os
import time
import io
import cv2
from datetime import datetime, timedelta, date
from typing import Optional, List
from fastapi import Depends, FastAPI, HTTPException, status, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from starlette.responses import FileResponse,StreamingResponse

from datatype import User, regItem
from db_util import DBmng
from realapplication import Worker, generate_preview


class TaskPool:
    def __init__(self):
        self.running = 0
        self.pool = []
        
        global worker
        try:
            worker = Worker(fallback=False)
        except:
            worker = Worker(fallback=True)

    def get(self):
        if len(self.pool) < 3:
            self.pool += db.collectTODO()
        task = self.pool.pop(0)
        db.toState(task, 2)  # in proccess
        print(self.pool)
        return task

    def fin(self, task):
        db.toState(task, 1)  # finished

    def bg(self):
        global worker
        if worker.fallback:
            GPU = False
        else:
            GPU = True
        while True:
            if len(self.pool):
                task = self.pool.pop(0)
                try:
                    task = worker.invoke(task)
                    db.taskFin(task)
                    #return state
                    if (worker.fallback and GPU):
                        print('back to CUDA')
                        worker = Worker(fallback=True)
                except:
                    print('failed')
                    worker = Worker(fallback=True)
                    task = worker.invoke(task)
                    db.taskFin(task)

            else:
                tasks = db.collectTODO()
                if not len(tasks):
                    time.sleep(10)
                self.pool += tasks


# to get a string like this run:
# openssl rand -hex 32
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
app = FastAPI()
origins = [
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    ret = {"access_token": access_token, "token_type": "bearer"}
    return ret


@app.get("/me/")
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user.name, current_user.tasks, current_user.t_num


@app.post("/me/newtask/")
async def file_upload(noise: float, sf: int, width: float, current_user: User = Depends(get_current_active_user),
                      files: List[UploadFile] = File(...)):
    ret = []
    for file in files:
        # try:
            res = await file.read()
            root = os.path.join('users', str(current_user.id), 'input')
            os.makedirs(root, exist_ok=True)
            E_path = os.path.join('users', str(current_user.id), 'output')
            os.makedirs(E_path, exist_ok=True)
            fpath = os.path.join(root, file.filename)
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


@app.get("/me/dload")
async def dload(taskid: str, current_user: User = Depends(get_current_active_user)):
    task = db.picFinTask(taskid)
    if task is not None:
        if task.uid == current_user.id:
            return FileResponse(task.E_path,
                                media_type='application/octet-stream',
                                filename=os.path.basename(task.E_path))


@app.get("/preview/{taskid}")
async def preview(taskid, current_user: User = Depends(get_current_active_user)):
    task = db.picTask(taskid)
    if task is not None:
        if task.uid == current_user.id:
            print(task.preview)
            img = cv2.imread(task.preview)
            res, im_g = cv2.imencode(".png", img)
            return StreamingResponse(io.BytesIO(im_g.tobytes()), media_type="image/png")


@app.on_event('startup')
async def inital():
    global pool
    pool = TaskPool()


@app.on_event("startup")
async def startup():
    global db
    db = DBmng()
    await db.database.connect()


@app.post("/deltask")
async def deltask(taskid: str, current_user: User = Depends(get_current_active_user)):
    task = db.picTask(taskid)
    if task is not None:
        if task.uid == current_user.id:
            db.deltask(taskid)
            os.remove(task.img)
            os.remove(task.E_path)
            return 'success'
        else:
            return 'out_of_range'


@app.get("/up/")
async def up(background_tasks: BackgroundTasks, current_user: User = Depends(get_current_active_user)):
    # if current_user.name == 'luixiao':
    if not pool.running:
        pool.running = 1
        background_tasks.add_task(pool.bg)
        return 1
    else:
        return 0


@app.post("/cleanall/")
async def clean(current_user: User = Depends(get_current_active_user)):
    if current_user.name == 'luixiao':
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

# uvicorn.run(app, host="0.0.0.0", port=8000)
