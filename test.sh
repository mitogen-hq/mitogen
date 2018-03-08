#!/bin/bash

timeout()
{
    python -c '
import subprocess
import sys
import time

deadline = time.time() + float(sys.argv[1])
proc = subprocess.Popen(sys.argv[2:])
while time.time() < deadline and proc.poll() is None:
    time.sleep(1.0)

if proc.poll() is not None:
    sys.exit(proc.returncode)
proc.terminate()
print
print >> sys.stderr, "Timeout! Command was:", sys.argv[2:]
print
sys.exit(1)
    ' "$@"
}

for f in tests/*_test.py; do
    echo $f
    timeout 10 python $f
done
