import config
from login import worker_template
a = []

for dest in config.worker_location:
    a.append(worker_template(dest))

d = a[2]
a.remove(d)
print(a)