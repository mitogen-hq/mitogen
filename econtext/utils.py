
import logging

import econtext


def log_to_file(path, level=logging.DEBUG):
    log = logging.getLogger('')
    fp = open(path, 'w', 1)
    log.setLevel(level)
    log.handlers.insert(0, logging.StreamHandler(fp))


def run_with_broker(func, *args, **kwargs):
    broker = econtext.Broker()
    try:
        return func(broker, *args, **kwargs)
    finally:
        broker.Finalize()


def with_broker(func):
    def wrapper(*args, **kwargs):
        return run_with_broker(*args, **kwargs)
    wrapper.func_name = func.func_name
    return wrapper
