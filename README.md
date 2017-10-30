

# Running The Tests

[![Build Status](https://api.travis-ci.org/dw/mitogen.svg?branch=master)](https://travis-ci.org/dw/mitogen)

Your computer should have an Internet connection, and the ``docker`` command
line tool should be able to connect to a working Docker daemon (localhost or
elsewhere for OS X etc.) that can run new images.

The IP address of the Docker daemon must allow exposing ports from running
containers, e.g. it should not be firewalled or port forwarded.

If in doubt, just install Docker on a Linux box in the default configuration
and run the tests there.

## Steps To Prepare Development Environment

1. Get the code ``git clone https://github.com/dw/mitogen.git``
1. Go into the working directory ``cd mitogen``
1. Establish the docker image ``./tests/build_docker_image.py``
1. Build the virtual environment ``virtualenv ../venv``
1. Enable the virtual environment we just built ``source ../venv/bin/activate``
1. Install Mitogen in pip editable mode ``pip install -e .``
1. Run ``test.sh``
