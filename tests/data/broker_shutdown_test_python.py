#!/usr/bin/env python
# Delete a semaphore file to allow the main thread to wake up, then sleep for
# 30 seconds before starting the real Python.
import os
import time
import sys
os.unlink(os.environ['BROKER_SHUTDOWN_SEMAPHORE'])
time.sleep(30)
os.execl(sys.executable, sys.executable, *sys.argv[1:])
