#!/usr/bin/env python

"""
For use by the Travis scripts, just print out the hostname of the Docker
daemon from the environment.
"""

import docker
import testlib

docker = docker.from_env(version='auto')
print testlib.get_docker_host(docker)
