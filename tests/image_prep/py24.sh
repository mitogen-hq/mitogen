#!/bin/bash

docker run \
    -it --rm \
    -v `pwd`:`pwd` \
    ubuntu:trusty \
    bash -c "set -ex; sudo apt-get update; sudo apt-get -y install zlib1g-dev build-essential wget; cd `pwd`; bash py24-build.sh"
