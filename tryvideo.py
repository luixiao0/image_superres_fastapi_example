from realapplication import Worker
import os
from datatype import Task
import cv2
# worker = Worker(fallback=False)

def videoiter(videopth, E_path, sf=2, noise=3, width=0.6):
    cap = cv2.VideoCapture(videopth)
    tmppath = 'tmp'
    count = 0
    while True:
        ret, img = cap.read()
        if not ret:
            break
        fname = os.path.join(E_path, str(count)+'.png')
        cv2.imwrite(fname, img)
        count += 1


work_dir = r"C:\Users\1\Desktop\210709\sel"
videos = os.listdir(work_dir)
os.makedirs(os.path.join(work_dir, 'output'), exist_ok=True)

for v in videos:
    E_path = os.path.join(work_dir, 'output', v.split('.')[0])
    os.makedirs(E_path, exist_ok=True)
    videoiter(os.path.join(work_dir, v), E_path, 2, 5, 0.6)