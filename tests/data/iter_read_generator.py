#!/usr/bin/env python
# I produce text every 100ms, for testing mitogen.core.iter_read()

import sys
import time


i = 0
while True:
    i += 1
    sys.stdout.write(str(i))
    sys.stdout.flush()
    time.sleep(0.1)
