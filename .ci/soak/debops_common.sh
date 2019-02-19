#!/bin/bash

export NOCOVERAGE=1

# Make Docker containers once.
/usr/bin/time -v ./.ci/debops_common_tests.py "$@" || break
export KEEP=1

i=0
while :
do
    i=$((i + 1))
    /usr/bin/time -v ./.ci/debops_common_tests.py "$@" || break
done

echo $i
