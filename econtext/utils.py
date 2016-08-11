
import logging

import econtext
import econtext.core
import econtext.master


def log_to_file(path, level=logging.DEBUG):
    log = logging.getLogger('')
    fp = open(path, 'w', 1)
    econtext.core.set_cloexec(fp.fileno())
    log.setLevel(level)
    log.handlers.insert(0, logging.StreamHandler(fp))


def run_with_broker(func, *args, **kwargs):
    broker = econtext.master.Broker()
    try:
        return func(broker, *args, **kwargs)
    finally:
        broker.Shutdown()
        broker.Wait()


def with_broker(func):
    def wrapper(*args, **kwargs):
        return run_with_broker(*args, **kwargs)
    wrapper.func_name = func.func_name
    return wrapper
