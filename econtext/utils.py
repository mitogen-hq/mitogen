"""
A random assortment of utility functions useful on masters and slaves.
"""

import logging
import sys

import econtext
import econtext.core
import econtext.master


LOG = logging.getLogger('econtext')


def disable_site_packages():
    """Remove all entries mentioning site-packages or Extras from the system
    path. Used primarily for testing on OS X within a virtualenv, where OS X
    bundles some ancient version of the 'six' module."""
    for entry in sys.path[:]:
        if 'site-packages' in entry or 'Extras' in entry:
            sys.path.remove(entry)


def log_to_file(path=None, io=True, level=logging.DEBUG):
    """Install a new :py:class:`logging.Handler` writing applications logs to
    the filesystem. Useful when debugging slave IO problems."""
    log = logging.getLogger('')
    if path:
        fp = open(path, 'w', 1)
        econtext.core.set_cloexec(fp.fileno())
    else:
        fp = sys.stderr

    log.setLevel(level)
    if io:
        logging.getLogger('econtext.io').setLevel(level)

    fmt = '%(asctime)s %(levelname).1s %(name)s: %(message)s'
    datefmt = '%H:%M:%S'
    handler = logging.StreamHandler(fp)
    handler.formatter = logging.Formatter(fmt, datefmt)
    log.handlers.insert(0, handler)


def run_with_broker(func, *args, **kwargs):
    """Arrange for `func(broker, *args, **kwargs)` to run with a temporary
    :py:class:`econtext.master.Broker`, ensuring the broker is correctly
    shut down during normal or exceptional return."""
    broker = econtext.master.Broker()
    try:
        return func(broker, *args, **kwargs)
    finally:
        broker.shutdown()
        broker.join()


def with_broker(func):
    """Decorator version of :py:func:`run_with_broker`. Example:

    .. code-block:: python

        @with_broker
        def do_stuff(broker, arg):
            pass

        do_stuff(blah, 123)
    """
    def wrapper(*args, **kwargs):
        return run_with_broker(func, *args, **kwargs)
    wrapper.func_name = func.func_name
    return wrapper
