imgs = {'jpg', 'png', 'tiff', 'tif', 'jpeg', 'bmp'}
videos = {'mp4', 'avi', 'flv'}

def detect(filename):
    ext = [filename.split(".")[-1].lower()]
    ext = set(ext)
    if ext & imgs:
        return 0
        #images
    elif ext & videos:
        return 1
    else:
        return 2
