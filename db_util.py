import json

import bcrypt
import databases
import sqlalchemy
from sqlalchemy import and_

import config
from datatype import Task, User


def extractTask(task):
    if task is not None:
        a = Task(task[1],task[4],task[3])
        a.taskid = task[0]
        a.state = task[2]
        a.date = task[5]
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
        self.DATABASE_URL = config.sqlLocation
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
            sqlalchemy.Column("state", sqlalchemy.Integer),
            sqlalchemy.Column("uid", sqlalchemy.Integer),
            sqlalchemy.Column("args", sqlalchemy.String),
            sqlalchemy.Column("date", sqlalchemy.TIMESTAMP, nullable=False, default=sqlalchemy.func.now()),
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

    def newTask(self, filename, uid, args):
        self.conn.execute(self.TASK.insert(),
                          {"img": filename, "uid": uid, "args": json.dumps(args), "state": 0})
        task = extractTask(self.conn.execute(
            self.TASK.select().order_by(self.TASK.c.taskid.desc()).limit(1)).fetchone())
        user_task = self.conn.execute(
            self.USER.select()
                .where(self.USER.c.id == uid)).fetchone()[4].strip().split(' ')

        user_task.append(str(task.taskid))
        user_task = set(user_task)

        self.conn.execute(self.USER.update().
                          where(self.USER.c.id == uid).
                          values(tasks=" ".join(list(user_task))))
        return task

    def deltask(self, taskid):
        task = self.picTask(taskid)
        print(task)
        if task is None:
            return
        origid = int(taskid)
        s = self.USER.select().where(self.USER.c.id == task.uid)
        line = self.conn.execute(s).fetchone()
        print(line)
        taskid = set([taskid])
        tasks = line[4].strip().split(' ')
        tasks = set(tasks)
        tasks = tasks - taskid
        tasks = list(tasks)
        newline = " ".join(tasks)
        self.conn.execute(self.USER.update().
                          where(self.USER.c.id == task.uid).
                          values(tasks=newline))
        self.conn.execute(self.TASK.delete().where(
            self.TASK.c.taskid == origid))

    def collectTODO(self):  # -2:server full -1:proccess failed 0:not assigned, 1:finished 2:assigned 3:in_queue
        task_orig = self.conn.execute(self.TASK.select().where(
            and_(self.TASK.c.state != 1, self.TASK.c.state != -1)
        )).fetchall()
        tasks = []
        for line in task_orig:
            if len(tasks) >= 10:
                return tasks
            else:
                task = extractTask(line)
                task.set(3)
                tasks.append(task)
        return tasks

    def collectFin(self):  # -2:server full -1:proccess failed 0:not assigned, 1:finished 2:assigned 3:in_queue
        task_orig = self.conn.execute(self.TASK.select().where(
            self.TASK.c.state == 1)).fetchall()
        tasks = []
        for line in task_orig:
            tasks.append(extractTask(line))
        return tasks

    def toState(self, id, state):
        self.conn.execute(self.TASK.update().
                          where(self.TASK.c.taskid == id).
                          values(state=state))

    def taskFin(self, task):
        self.toState(task, task.state)

    def check_username_password(self, uname, psw):
        user = self.findUser(uname)
        if user is not None:
            if bcrypt.checkpw(psw.encode('utf-8'), user.hashedkey):
                return user
        return False

    def findUser(self, uname):
        s = self.USER.select().where(self.USER.c.name == uname)
        return extractUser(self.conn.execute(s).fetchone())

    def findTasks(self, page, uid):  # 10task/page
        s = self.USER.select().where(self.USER.c.id == uid)
        task_ = []
        row = self.conn.execute(s).fetchone()
        taskLine = row[4]
        taskLine = trim(taskLine)
        if len(taskLine):
            # print(taskLine)
            taskIDs = taskLine.split(' ')
            taskIDs = [int(e) for e in taskIDs]
            taskIDs.sort(reverse=True)
            try:
                page = int(page)
            except:
                page = 1
            pageL = (page - 1) * 10  # smallest ID
            taskIDs = taskIDs[pageL:pageL + 100]
            for taskID in taskIDs:
                task = self.conn.execute(self.TASK.select().
                                         where(self.TASK.c.taskid == int(taskID))). \
                    fetchone()

                task_.append(extractTask(task).front_dump())
        return task_

    def findTask(self, uid, taskID):
        s = self.USER.select().where(self.USER.c.id == uid)
        row = self.conn.execute(s).fetchone()
        taskLine = row[4]
        taskLine = trim(taskLine)
        if len(taskLine):
            print(taskLine)
            taskIDs = taskLine.split(' ')
            if (taskID in taskIDs):
                task = self.conn.execute(self.TASK.select().
                                         where(self.TASK.c.taskid == int(taskID))). \
                    fetchone()
                return task
            else:
                return {}

    def picFinTask(self, taskid):
        s = self.TASK.select().where(self.TASK.c.taskid == taskid)
        row = self.conn.execute(s).fetchone()
        if row is not None:
            if row[3] == 1:  # if finished
                return extractTask(row)

    def picTask(self, taskid):
        s = self.TASK.select().where(self.TASK.c.taskid == taskid)
        row = self.conn.execute(s).fetchone()
        if row is not None:
            return extractTask(row)
