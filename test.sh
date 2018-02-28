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
    if proc.returncode:
        print
        print >> sys.stderr, "Command failed:", sys.argv[2:]
        print
    sys.exit(proc.returncode)
proc.terminate()
print
print >> sys.stderr, "Timeout! Command was:", sys.argv[2:]
print
sys.exit(1)
    ' "$@"
}

timeout 05.0 python tests/call_function_test.py
timeout 05.0 python tests/channel_test.py
timeout 05.0 python tests/first_stage_test.py
timeout 05.0 python tests/id_allocation_test.py
timeout 05.0 python tests/importer_test.py
timeout 05.0 python tests/local_test.py
timeout 05.0 python tests/master_test.py
timeout 05.0 python tests/module_finder_test.py
timeout 05.0 python tests/nested_test.py
timeout 05.0 python tests/parent_test.py
timeout 05.0 python tests/responder_test.py
timeout 05.0 python tests/utils_test.py
timeout 20.0 python tests/select_test.py
timeout 20.0 python tests/ssh_test.py
timeout 30.0 python tests/fakessh_test.py
