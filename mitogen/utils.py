
import logging
import sys

import mitogen
import mitogen.core
import mitogen.master


LOG = logging.getLogger('mitogen')


def disable_site_packages():
    for entry in sys.path[:]:
        if 'site-packages' in entry or 'Extras' in entry:
            sys.path.remove(entry)


def log_to_file(path=None, io=True, level='INFO'):
    log = logging.getLogger('')
    if path:
        fp = open(path, 'w', 1)
        mitogen.core.set_cloexec(fp.fileno())
    else:
        fp = sys.stderr

    level = getattr(logging, level, logging.INFO)
    log.setLevel(level)
    if io:
        logging.getLogger('mitogen.io').setLevel(level)

    fmt = '%(asctime)s %(levelname).1s %(name)s: %(message)s'
    datefmt = '%H:%M:%S'
    handler = logging.StreamHandler(fp)
    handler.formatter = logging.Formatter(fmt, datefmt)
    log.handlers.insert(0, handler)


def run_with_router(func, *args, **kwargs):
    broker = mitogen.master.Broker()
    router = mitogen.master.Router(broker)
    try:
        return func(router, *args, **kwargs)
    finally:
        broker.shutdown()
        broker.join()


def with_router(func):
    def wrapper(*args, **kwargs):
        return run_with_router(func, *args, **kwargs)
    wrapper.func_name = func.func_name
    return wrapper
