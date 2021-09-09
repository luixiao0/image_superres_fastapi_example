imgs = ['jpg', 'png', 'tiff', 'tif', 'jpeg', 'bmp']
videos = ['mp4', 'avi', 'flv']

allowed_exts = imgs

preview = ""
storage = './users'
default_temp = "./temp"
sqlLocation = "sqlite:///./test1.db"
check_interval = 3
wake_interval = 10

# to get a string like this run:
# openssl rand -hex 32
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

ops = ['lux', 'luixiao']

from db_util import DBmng
global db
db = DBmng()

worker_location = [['http://127.0.0.1:8001/', imgs],
                   ['http://127.0.0.1:8002/', imgs],
                   ['http://127.0.0.1:8003/', imgs]]