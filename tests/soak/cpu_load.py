#!/usr/bin/env python
"""
Put the machine's CPUs under pressure to increase the likelihood of scheduling
weirdness. Useful for exposing otherwise difficult to hit races in the library.
"""

import multiprocessing

def burn():
    while 1: pass

mul = 2
count = int(mul * multiprocessing.cpu_count())
print count

procs = [multiprocessing.Process(target=burn)
         for _ in range(count)]

for i, proc in enumerate(procs):
    print([i])
    proc.start()
