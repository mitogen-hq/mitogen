#!/bin/bash

#
# Wrap a run of Ansible playbook so that CPU usage counters and network
# activity are logged to files.
#

[ ! "$1" ] && exit 1
name="$1"; shift


sudo tcpdump -i any -w $name-net.pcap -s 66 port 22 or port 9122 &
sleep 0.5

perf stat -x, -I 100 \
    -e branches \
    -e instructions \
    -e task-clock \
    -e context-switches \
    -e page-faults \
    -e cpu-migrations \
    -o $name-perf.csv "$@"
pkill -f ssh:; sleep 0.1
sudo pkill -f tcpdump
