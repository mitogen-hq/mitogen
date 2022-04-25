#!/usr/bin/env python

import sys
import os

import mitogen.core


times = []
for x in range(5):
    t0 = mitogen.core.now()
    os.spawnvp(os.P_WAIT, sys.argv[1], sys.argv[1:])
    t = mitogen.core.now() - t0
    times.append(t)
    print('+++', t)

print('all:', times)
print('min %s max %s diff %s' % (min(times), max(times), (max(times) - min(times))))
