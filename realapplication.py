import gc
import os.path
# import threading

import cv2
import numpy as np
import torch

#from srnet.models.network_usrnet import USRNet as net  # for pytorch version <= 1.7.1
from srnet.models.network_usrnet_v1 import USRNet as net  # for pytorch version >= 1.8.1
from srnet.utils import utils_deblur
from srnet.utils import utils_image as util
from srnet.utils import utils_sisr as sr

# shared_resource_lock = threading.Lock()


def generate_preview(imgpath, uid):
    print(imgpath)
    img = util.cv_imread(imgpath)
    # if img != None:
    #     previewdir = "" #TODO: fill the defalut preview image
    #     return previewdir
    # convert to (*,150) compressed thumbnail
    h, w = img.shape[:2]
    dsth = 150
    if h>dsth:
        dstw = int(w * (dsth / h))
        img = cv2.resize(img, (dstw, dsth),interpolation=cv2.INTER_AREA)
    
    root = os.path.join('users', str(uid), 'preview')
    os.makedirs(root, exist_ok=True)
    img_name, ext = os.path.splitext(os.path.basename(imgpath))
    previewdir = os.path.join(root, img_name+'.jpg')
    cv2.imencode('.jpg', img)[1].tofile(previewdir)

    return previewdir

class Worker:
    def __init__(self, fallback=False):
        gc.collect()
        if not torch.cuda.is_available():
            fallback = 1
        if fallback:
            self.device = torch.device('cpu')
            print('cpu')
        else:
            torch.backends.cudnn.benchmark = True
            torch.cuda.empty_cache()
            self.device = torch.device('cuda')
            print('cuda')

        self.fallback = fallback
        self.model_name = 'usrnet_tiny'
        self.model_pool = 'srnet/model_zoo'
        self.model_path = os.path.join(self.model_pool, self.model_name + '.pth')

        self.model = net(n_iter=6, h_nc=32, in_nc=4, out_nc=3, nc=[16, 32, 64, 64],
                         nb=2, act_mode="R", downsample_mode='strideconv', upsample_mode="convtranspose")

        # if not fallback:
        #     self.model = self.model.cuda()

        # self.model = torch.jit.script(self.model)
        self.model.load_state_dict(torch.load(self.model_path), strict=True)
        self.model.to(self.device)
        self.model.eval()
        for key, v in self.model.named_parameters():
            v.requires_grad = False

        self.kernel_width_default_x1234 = [0.4, 0.7, 1.5, 2.0]

        self.is_idle = True #need for task_pool

    def rock(self, img, E_path, noiseLevel, sf, customized_kernel_width=False):  # orig img full path #need for task_pool
        if True:
            sf = int(sf)
            noise_level_model = noiseLevel / 255.  # noise level of model
            if customized_kernel_width:
                kernel_width = customized_kernel_width
            else:
                kernel_width = self.kernel_width_default_x1234[sf - 1]

            k = utils_deblur.fspecial('gaussian', 25, kernel_width)
            k = sr.shift_pixel(k, sf)  # shift the kernel
            k /= np.sum(k)
            kernel = util.single2tensor4(k[..., np.newaxis]).to(self.device)

            # ------------------------------------
            # (1) img_L
            # ------------------------------------

            img_name, ext = os.path.splitext(os.path.basename(img))

            # try:
            img_L = util.imread_uint(img, n_channels=3)
            # except:
                # return -1
            img_L = util.uint2single(img_L)
            w, h = img_L.shape[:2]

            # boundary handling
            boarder = 8  # default setting for kernel size 25x25
            img = cv2.resize(img_L, (sf * h, sf * w), interpolation=cv2.INTER_NEAREST)
            img = utils_deblur.wrap_boundary_liu(img, [int(np.ceil(sf * w / boarder + 2) * boarder),
                                                       int(np.ceil(sf * h / boarder + 2) * boarder)])
            img_wrap = sr.downsample_np(img, sf, center=False)
            img_wrap[:w, :h, :] = img_L
            img_L = img_wrap

            img_L = util.single2tensor4(img_L)
            img_L = img_L.to(self.device)

            sigma = torch.tensor(noise_level_model).float().view([1, 1, 1, 1]).to(self.device)
            [img_L, kernel, sigma] = [el.to(self.device) for el in [img_L, kernel, sigma]]

            # module = torch.jit.trace(self.model,(img_L, kernel, sf, sigma))

            img_E = self.model(img_L, kernel, sf, sigma)

            img_E = util.tensor2uint(img_E)[:sf * w, :sf * h, ...]
        path = img_name + '_x' + str(sf) + '.png'
        util.imsave(img_E, os.path.join(E_path, path))
        return path

    def invoke(self, task): #need for task_pool
        self.is_idle = False
        path = self.rock(task.img, task.E_path,
                         task.noiseLevel, task.sf,
                         task.customized_kernel_width)

        task.E_path = os.path.join(task.E_path, path)
        if path == -1 :
            task.state = -1
            print('worker_err at task ', task.taskid)
        else:
            task.state = 1
            print('task', task.taskid, ' Finished')

        self.is_idle = True
        return task
