#!/bin/bash
# workaround from https://stackoverflow.com/a/26082445 to handle Travis 4MB log limit
set -e

export PING_SLEEP=30s
export WORKDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export BUILD_OUTPUT=$WORKDIR/build.out

touch $BUILD_OUTPUT

dump_output() {
    echo Tailing the last 1000 lines of output:
    tail -1000 $BUILD_OUTPUT  
}
error_handler() {
    echo ERROR: An error was encountered with the build.
    dump_output
    kill $PING_LOOP_PID
    exit 1
}
# If an error occurs, run our error handler to output a tail of the build
trap 'error_handler' ERR

# Set up a repeating loop to send some output to Travis.

bash -c "while true; do echo \$(date) - building ...; sleep $PING_SLEEP; done" &
PING_LOOP_PID=$!

.ci/${MODE}_tests.py >> $BUILD_OUTPUT 2>&1

# The build finished without returning an error so dump a tail of the output
dump_output

# nicely terminate the ping output loop
kill $PING_LOOP_PID
