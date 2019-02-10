#!/usr/bin/env python
# I consume 65535 bytes every 10ms, for testing mitogen.core.write_all()

import os
import time

while True:
    os.read(0, 65535)
    time.sleep(0.01)
