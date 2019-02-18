#!/bin/bash

export NOCOVERAGE=1
export DISTROS="debian*4"

# Make Docker containers once.
/usr/bin/time -v ./.ci/ansible_tests.py "$@"
export KEEP=1

i=0
while :
do
    i=$((i + 1))
    /usr/bin/time -v ./.ci/ansible_tests.py "$@" || break
done

echo $i
