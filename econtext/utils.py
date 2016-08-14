"""
A random assortment of utility functions useful on masters and slaves.
"""

import logging

import econtext
import econtext.core
import econtext.master


def log_to_file(path, level=logging.DEBUG):
    """Install a new :py:class:`logging.Handler` writing applications logs to
    the filesystem. Useful when debugging slave IO problems."""
    log = logging.getLogger('')
    fp = open(path, 'w', 1)
    econtext.core.set_cloexec(fp.fileno())
    log.setLevel(level)
    log.handlers.insert(0, logging.StreamHandler(fp))


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
        return run_with_broker(*args, **kwargs)
    wrapper.func_name = func.func_name
    return wrapper
