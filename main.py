import json
import os
import threading
import time
from typing import Optional
import shutil
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from starlette.responses import FileResponse

import config
from realapplication import Worker

app = FastAPI()


def detect(ext):
    ext = ext[1:].lower()
    if ext in config.exts:
        return True
    else:
        return False


class WorkerTemplate:
    def __init__(self, w):
        self.template = w
        self.instance = None

    def get_instance(self):
        if self.instance is None:
            self.instance = self.template()
        return self.instance

    def shutdown(self):
        while True:
            if self.instance is None:
                break
            elif self.instance.is_idle:
                print('shutting down')
                self.instance.shutdown()
                self.instance = None
                break
            else:
                print("waiting {} until idle, shutdown".format(self.instance.model_name))
                time.sleep(3)

    def is_idle(self):
        if (self.instance is not None) and not self.instance.is_idle:
            return 0
        return 1


class Pipe:
    def __init__(self):
        self.tasks = []
        self.exit = False

    def add(self, task):
        self.tasks.append(task)

    def get(self):
        if self.exit:
            return None
        for i in range(len(self.tasks)):
            if self.tasks[i].finished():
                try:
                    os.remove(self.tasks[i].input)
                except Exception as e:
                    print(e)
                del self.tasks[i]
                i += 1
        if len(self.tasks):
            return self.tasks[0]
        else:
            return None


class Task:
    def __init__(self, filename, args):
        filename, ext = os.path.splitext(filename)
        self.input = os.path.join(config.input, "".join(str(time.time()).split('.')) + ext)
        self.output = os.path.join(config.output,
                                   "{}_{}{}".format(filename, "".join(str(time.time()).split('.'))[:-2][:8], ext))
        self.args = args
        self.state = 0

    def finished(self):
        if self.state == 1:
            return True
        else:
            return False

    def set(self, state):
        self.state = state


class WorkerThread(threading.Thread):  # 继承父类threading.Thread
    def __init__(self):
        global pipeline
        pipeline = Pipe()
        threading.Thread.__init__(self)
        global worker
        worker = WorkerTemplate(Worker)

    def run(self):
        global pipeline
        global worker
        sleeping_sheep_count = 0
        while True:
            if not len(pipeline.tasks):
                sleeping_sheep_count += 1
                time.sleep(config.check_interval)
            else:
                sleeping_sheep_count = 0
                instance = worker.get_instance()
                task = pipeline.get()
                if task is not None:
                    instance.invoke(task)
                else:
                    sleeping_sheep_count += 1
            if sleeping_sheep_count >= 10:
                worker.shutdown()
                time.sleep(config.sleeping_check_interval)


class API(threading.Thread):  # 继承父类threading.Thread
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):  # 把要执行的代码写到run函数里面 线程在创建后会直接运行run函数
        # webbrowser.open('http://127.0.0.1:8001/docs', new=2)
        uvicorn.run(app, host="0.0.0.0", port=8001, log_level="warning")


@app.post("/newtask")
async def file_upload(arg: Optional[str] = None,
                      File: UploadFile = File(...)):
    global pipeline
    ret = ''
    if arg is None: args = {}
    else:args = json.loads(arg)
    if File.file:
        filename, ext = os.path.splitext(File.filename)
        if detect(ext):
            task = Task(File.filename, args)
            res = await File.read()
            with open(task.input, "wb") as f:
                f.write(res)
                f.close()
            del res
            pipeline.add(task)
            ret = task.output.split('/')[-1]
    return ret


@app.get("/del")
async def delete(filename: str = Form(...)):
    filename = filename[1:-1]
    if filename is not None:
        path = os.path.join(config.output, filename)
        if os.path.exists(path):
            os.remove(path)
            return '1'


@app.get("/dload")
async def dload(filename: str = Form(...)):
    filename = filename[1:-1]
    if filename is not None:
        path = os.path.join(config.output, filename)
        if os.path.exists(path):
            return FileResponse(path, filename=str(filename))
        else:
            global pipeline
            for task in pipeline.tasks:
                t = os.path.basename(task.output)
                if t == filename:
                    return task.state
            return -1


@app.get("/status")
async def status():
    global worker
    return worker.is_idle()


if __name__ == "__main__":
    shutil.rmtree(config.input)
    os.makedirs(config.input, exist_ok=True)
    os.makedirs(config.output, exist_ok=True)

    thread2 = API()
    thread2.start()
    thread1 = WorkerThread()
    thread1.start()
    thread2.join()
    thread1.join()
