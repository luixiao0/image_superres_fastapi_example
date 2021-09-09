import os.path
import numpy as np
import cv2


def cv_imread(file_path):
    cv_img = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), -1)
    return cv_img


def imReadEncode(file_path):
    return cv2.imencode(".jpg", cv_imread(file_path))


def generate_preview(task):
    img = cv_imread(task.get('input'))
    # if img != None:
    #     previewdir = "" #TODO: fill the defalut preview image
    #     return previewdir
    # convert to (*,150) compressed thumbnail
    h, w = img.shape[:2]
    if h < w:
        delta = int((w - h) / 2)
        squareimg = img[:, delta:w - delta, :]
        showimg = squareimg[int(h / 4):int(h / 4 * 3), :, :]
    else:
        delta = int((h - w) / 2)
        squareimg = img[delta:h - delta, :, :]
        showimg = squareimg[int(h / 4):int(h / 4 * 3), :, :]
    dstw = 150
    h, w = showimg.shape[:2]
    if w > dstw:
        dsth = int(h * (dstw / w))
        img = cv2.resize(showimg, (dstw, dsth), interpolation=cv2.INTER_AREA)

    os.makedirs(os.path.join(task.get('root'),'preview'),exist_ok=True)
    previewdir = task.get('preview')
    cv2.imencode('.jpg', img)[1].tofile(previewdir)
