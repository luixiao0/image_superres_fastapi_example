import gc
import os.path

import cv2
import numpy as np
import torch

# from srnet.models.network_usrnet import USRNet as net  # for pytorch version <= 1.7.1
from srnet.models.network_usrnet_v1 import USRNet as Net  # for pytorch version >= 1.8.1
from srnet.utils import utils_deblur
from srnet.utils import utils_image as util
from srnet.utils import utils_sisr as sr


class Worker:
    def __init__(self, fallback=False):
        gc.collect()
        if not torch.cuda.is_available():
            fallback = 1
        if fallback:
            self.device = torch.device('cpu')
            print('cpu')
        else:
            torch.cuda.empty_cache()
            self.device = torch.device('cuda')
            print('cuda')

        self.fallback = fallback
        self.model_name = 'usrnet_tiny'
        self.model_pool = 'srnet/model_zoo'
        self.model_path = os.path.join(self.model_pool, self.model_name + '.pth')

        self.model = Net(n_iter=6, h_nc=32, in_nc=4, out_nc=3, nc=[16, 32, 64, 64],
                         nb=2, act_mode="R", downsample_mode='strideconv', upsample_mode="convtranspose")

        self.model.load_state_dict(torch.load(self.model_path), strict=True)
        self.model.to(self.device)
        self.model.eval()
        for key, v in self.model.named_parameters():
            v.requires_grad = False
        self.kernel_width_default_x1234 = [0.4, 0.7, 1.5, 2.0]
        self.is_idle = True  # need for task_pool
        self.defaults = {"sf":2, "kw":0.0, "n":2.0}
        self.args = ['n', 'sf', 'kw']
    def rock(self, img, e_path, noiselevel, sf,
             customized_kernel_width=0.0):  # orig img full path #need for task_pool
        if True:
            noise_level_model = float(noiselevel) / 255.  # noise level of model
            if customized_kernel_width != 0.0 and customized_kernel_width >= 0:
                kernel_width = float(customized_kernel_width)
            else:
                kernel_width = self.kernel_width_default_x1234[sf - 1]

            if sf is not None:
                if sf > 4 or sf < 2:
                    sf = 2
            else:
                sf = 2

            k = utils_deblur.fspecial('gaussian', 25, kernel_width)
            k = sr.shift_pixel(k, sf)  # shift the kernel
            k /= np.sum(k)
            kernel = util.single2tensor4(k[..., np.newaxis]).to(self.device)

            try:
                img_l = util.imread_uint(img, n_channels=3)
            except Exception as e:
                print(e)
                return -1
            img_l = util.uint2single(img_l)
            w, h = img_l.shape[:2]

            # boundary handling
            boarder = 8  # default setting for kernel size 25x25
            img = cv2.resize(img_l, (sf * h, sf * w), interpolation=cv2.INTER_NEAREST)
            img = utils_deblur.wrap_boundary_liu(img, [int(np.ceil(sf * w / boarder + 2) * boarder),
                                                       int(np.ceil(sf * h / boarder + 2) * boarder)])
            img_wrap = sr.downsample_np(img, sf, center=False)
            img_wrap[:w, :h, :] = img_l

            img_l = util.single2tensor4(img_wrap).to(self.device)

            sigma = torch.tensor(noise_level_model).float().view([1, 1, 1, 1]).to(self.device)
            [img_l, kernel, sigma] = [el.to(self.device) for el in [img_l, kernel, sigma]]

            img_e = self.model(img_l, kernel, sf, sigma)

            img_e = util.tensor2uint(img_e)[:sf * w, :sf * h, ...]
        util.imsave(img_e, e_path)
        return 0

    def invoke(self, task):  # need for task_pool
        self.is_idle = False
        task.state = 2
        try:
            for p in self.args:
                if not hasattr(task.args, p):
                    task.args[p] = self.defaults[p]
            ret = self.rock(task.input,
                            task.output,
                            float(task.args['n']),
                            int(task.args['sf']),
                            float(task.args['kw'])
                            )
            if ret == -1:
                task.state = -1
        except Exception as e:
            print(e)
            task.state = -1
            print('worker_err at task ', task.input)
            return task

        task.state = 1
        print('task', task.input, ' Finished')

        self.is_idle = True
        return task

    def shutdown(self):
        del self.model
        if not self.fallback:
            torch.cuda.empty_cache()
