#!/bin/bash

export NOCOVERAGE=1

i=0
while :
do
    i=$((i + 1))
    /usr/bin/time -v ./.ci/mitogen_py24_tests.py "$@" || break
done

echo $i
