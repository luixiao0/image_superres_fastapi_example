import config


def detect(fileext):
    fileext = [fileext.split(".")[-1].lower()]
    ext = set(fileext)
    if ext & set(config.allowed_exts):
        return 0
        # images
    else:
        return -1