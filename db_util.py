import bcrypt
import databases
import sqlalchemy
import json
from sqlalchemy import or_

from datatype import Task, User


def extractTask(task):
    if task is not None:
        a = Task()
        [a.taskid, a.img, a.E_path, a.state, a.uid, a.noiseLevel, a.sf, a.customized_kernel_width, a.date,a.preview] = \
            [task[0], task[1], task[2], task[3], task[4], task[5], task[6], task[7], task[8], task[9]]
        return a


def extractUser(user):
    if user is not None:
        a = User()
        [a.id, a.name, a.t_num, a.hashedkey] = [user[0], user[1], user[2], user[3]]
        if len(user[4]):
            a.tasks = user[4].split(' ')
        else:
            a.tasks = []
        return a


def trim(s):
    import re
    if s.startswith(' ') or s.endswith(' '):
        return re.sub(r"^(\s+)|(\s+)$", "", s)
    return s


class DBmng:
    def __init__(self):
        self.metadata = sqlalchemy.MetaData()
        self.DATABASE_URL = "sqlite:///./test1.db"
        self.database = databases.Database(self.DATABASE_URL)
        self.USER = sqlalchemy.Table(
            "USER",
            self.metadata,
            sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True, autoincrement=True),
            sqlalchemy.Column("name", sqlalchemy.String),
            sqlalchemy.Column("t_num", sqlalchemy.Integer),
            sqlalchemy.Column("hashedkey", sqlalchemy.String),
            sqlalchemy.Column("tasks", sqlalchemy.String),
        )

        self.TASK = sqlalchemy.Table(
            "TASK",
            self.metadata,
            sqlalchemy.Column("taskid", sqlalchemy.Integer, primary_key=True, autoincrement=True),
            sqlalchemy.Column("img", sqlalchemy.String),
            sqlalchemy.Column("E_path", sqlalchemy.String),
            sqlalchemy.Column("state", sqlalchemy.Integer),
            sqlalchemy.Column("uid", sqlalchemy.Integer),
            sqlalchemy.Column("noiselevel", sqlalchemy.Float),
            sqlalchemy.Column("sf", sqlalchemy.Integer),
            sqlalchemy.Column("customized_kernel_width", sqlalchemy.Integer),
            sqlalchemy.Column("date", sqlalchemy.TIMESTAMP, nullable=False, default=sqlalchemy.func.now()),
            sqlalchemy.Column("preview", sqlalchemy.String),
        )
        self.engine = sqlalchemy.create_engine(
            self.DATABASE_URL, connect_args={"check_same_thread": False}
        )
        self.metadata.create_all(self.engine)
        self.conn = self.engine.connect()

    def newUser(self, name, t_num, key):
        user = self.findUser(name)
        if user is None:
            hashedkey = bcrypt.hashpw(key.encode('utf-8'), bcrypt.gensalt())
            ins = self.USER.insert()
            self.conn.execute(ins,
                              {"name": name, "t_num": t_num, "hashedkey": hashedkey, "tasks": ""})
            return "success"
        else:
            return "duplicate_user"

    def newTask(self, img, E_path, uid, noise, sf, width, previewdir):
        self.conn.execute(self.TASK.insert(),
                          {"img": img, "E_path": E_path, "uid": uid, "noiselevel": noise,
                           "sf": sf, "customized_kernel_width": width, 'state': 0, 'preview':previewdir})
        task = extractTask(self.conn.execute(
            self.TASK.select().order_by(self.TASK.c.taskid.desc()).limit(1)).fetchone())
        user_task = self.conn.execute(self.USER.select().where(self.USER.c.id == uid)).fetchone()[4]
        user_task = user_task + ' ' + str(task.taskid)
        self.conn.execute(self.USER.update().
                          where(self.USER.c.id == uid).
                          values(tasks=user_task))
        return task

    def deltask(self, taskid):
        task = self.picTask(taskid)
        print(task)
        if task is None:
            return

        self.conn.execute(self.TASK.delete()
                          .where(self.TASK.c.taskid == taskid))

        s = self.USER.select().where(self.USER.c.id == task.uid)
        line = self.conn.execute(s).fetchone()
        print(line)
        newline = ""
        taskid = int(taskid)
        tasks = line[4].split(' ')
        for task_id in tasks:
            if taskid != task_id:
                newline = newline + ' ' + task_id
        self.conn.execute(self.USER.update().
                          where(self.USER.c.id == task.uid).
                          values(tasks=newline))

    def collectTODO(self):  # 0:not in pipe, 1:finished 2:in pipe
        task_orig = self.conn.execute(self.TASK.select().where(
            or_(self.TASK.c.state == 0, self.TASK.c.state == 2)
        )).fetchall()
        tasks = []
        for line in task_orig:
            if len(tasks) >= 10:
                return tasks
            else:
                task = extractTask(line)
                self.toState(task, 2)
                tasks.append(task)
        return tasks

    def collectFin(self):  # 0:not in pipe, 1:finished 2:in pipe
        task_orig = self.conn.execute(self.TASK.select().where(
            self.TASK.c.state == 1)).fetchall()
        tasks = []
        for line in task_orig:
            tasks.append(extractTask(line))
        return tasks

    def toState(self, task, state):
        self.conn.execute(self.TASK.update().
                          where(self.TASK.c.taskid == task.taskid).
                          values(state=state))

    def taskFin(self, task):
        self.toState(task, 1)
        self.conn.execute(self.TASK.update().
                          where(self.TASK.c.taskid == task.taskid).
                          values(img=task.img, E_path=task.E_path))

    def check_username_password(self, uname, psw):
        user = self.findUser(uname)
        if user is not None:
            if bcrypt.checkpw(psw.encode('utf-8'), user.hashedkey):
                return user
        return False

    def findUser(self, uname):
        s = self.USER.select().where(self.USER.c.name == uname)
        return extractUser(self.conn.execute(s).fetchone())

    def findTasks(self, uid):
        s = self.USER.select().where(self.USER.c.id == uid)
        task_ = {}
        row = self.conn.execute(s).fetchone()
        taskLine = row[4]
        taskLine = trim(taskLine)
        if len(taskLine):
            print(taskLine)
            taskIDs = taskLine.split(' ')
            for taskID in taskIDs:
                task = self.conn.execute(self.TASK.select().
                                         where(self.TASK.c.taskid == int(taskID))). \
                    fetchone()
                task_[taskID] = task
        return task_

    def picFinTask(self, taskid):
        s = self.TASK.select().where(self.TASK.c.taskid == taskid)
        row = self.conn.execute(s).fetchone()
        if row[3] == 1:  # if finished
            return extractTask(row)

    def picTask(self, taskid):
        s = self.TASK.select().where(self.TASK.c.taskid == taskid)
        row = self.conn.execute(s).fetchone()
        return extractTask(row)
