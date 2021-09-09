import time
import requests
import config


class NetworkWorker:
    def __init__(self, dest=None, name=None):
        self.is_idle = False
        if dest is None:
            self.dest = "http://127.0.0.1:8001/"
        else:
            self.dest = dest
        if name is None:
            self.name = self.dest
        else:
            self.name = name
        self.online = False
        self.status()

    def rock(self, task):
        response = requests.post(self.dest + 'newtask',
                                 data=task.args,
                                 files={"File": (task.img, open(task.get('input'), 'rb').read())})
        filename = response.content.decode('utf-8')
        while True:
            response1 = requests.get(self.dest+'dload', data={"filename": filename})
            if len(response1.content) <= 3:
                status = int(response1.content.decode('utf-8'))
                task.set(status)
            else:
                f = open(task.get('output'), 'wb')
                f.write(response1.content)
                f.close()
                task.set(1)
                break
            time.sleep(config.check_interval)

        requests.get(self.dest + 'del', data={"filename": filename})
        return task

    def invoke(self, task):
        self.status()
        if not (self.online and self.is_idle):
            task.set(0)
            return task
        self.is_idle = False
        task = self.rock(task)
        if task.state == 1:
            print('task', task.taskid, ' Finished')
            task.set(1)
        else:
            print('task_err ', task.taskid)
            task.set(-1)
        self.is_idle = True
        return task

    def shutdown(self):
        pass

    def status(self):
        try:
            response1 = requests.get(self.dest + 'status')
            status = int(response1.content.decode('utf-8'))
            if status == 1:
                self.is_idle = True
                self.online = True
        except:
            print('worker {} offline'.format(self.dest))
            self.online = False
            self.is_idle = True
        return self.is_idle