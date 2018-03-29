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

trap 'sigint' INT
sigint()
{
    echo "SIGINT received, stopping.."
    exit 1
}

run_test()
{
    echo "Running $1.."
    timeout 10 python $1 || fail=$?
}

run_test tests/ansible_helpers_test.py
run_test tests/call_error_test.py
run_test tests/call_function_test.py
run_test tests/channel_test.py
run_test tests/fakessh_test.py
run_test tests/first_stage_test.py
run_test tests/fork_test.py
run_test tests/id_allocation_test.py
run_test tests/importer_test.py
run_test tests/latch_test.py
run_test tests/local_test.py
run_test tests/master_test.py
run_test tests/module_finder_test.py
run_test tests/nested_test.py
run_test tests/parent_test.py
run_test tests/receiver_test.py
run_test tests/responder_test.py
run_test tests/router_test.py
run_test tests/select_test.py
run_test tests/ssh_test.py
run_test tests/utils_test.py

if [ "$fail" ]; then
    echo "AT LEAST ONE TEST FAILED" >&2
    exit 1
fi
