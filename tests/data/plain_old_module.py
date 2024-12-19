"""
I am a plain old module with no interesting dependencies or import machinery
fiddlery.
"""

import math


class MyError(Exception):
    pass


def get_sentinel_value():
    # Some proof we're even talking to the mitogen-test Docker image
    with open('/etc/sentinel', 'rb') as f:
        return f.read().decode()


def add(x, y):
    return x + y


def pow(x, y):
    return x ** y
