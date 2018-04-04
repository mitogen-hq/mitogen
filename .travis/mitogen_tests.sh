#!/bin/bash -ex
# Run the Mitogen tests.

MITOGEN_LOG_LEVEL=debug PYTHONPATH=. ${TRAVIS_BUILD_DIR}/test
