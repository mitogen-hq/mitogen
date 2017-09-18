
Internal API Reference
**********************


mitogen.core
============


Side Class
----------

.. autoclass:: mitogen.core.Side
   :members:


Stream Classes
--------------

.. autoclass:: mitogen.core.BasicStream
   :members:

.. autoclass:: mitogen.core.Stream
   :members:

.. autoclass:: mitogen.master.Stream
   :members:

.. autoclass:: mitogen.ssh.Stream
   :members:


Other Stream Subclasses
-----------------------

.. autoclass:: mitogen.core.IoLogger
   :members:

.. autoclass:: mitogen.core.Waker
   :members:



ExternalContext Class
---------------------

.. class:: mitogen.core.ExternalContext

    External context implementation.

    .. attribute:: broker

        The :py:class:`mitogen.core.Broker` instance.

    .. attribute:: context

            The :py:class:`mitogen.core.Context` instance.

    .. attribute:: channel

            The :py:class:`mitogen.core.Channel` over which
            :py:data:`CALL_FUNCTION` requests are received.

    .. attribute:: stdout_log

        The :py:class:`mitogen.core.IoLogger` connected to ``stdout``.

    .. attribute:: importer

        The :py:class:`mitogen.core.Importer` instance.

    .. attribute:: stdout_log

        The :py:class:`IoLogger` connected to ``stdout``.

    .. attribute:: stderr_log

        The :py:class:`IoLogger` connected to ``stderr``.


mitogen.master
===============

.. autoclass:: mitogen.master.ProcessMonitor


Helper Functions
----------------

.. function:: mitogen.core.io_op (func, \*args)

    When connected over a TTY (i.e. sudo), disconnection of the remote end is
    signalled by EIO, rather than an empty read like sockets or pipes. Ideally
    this will be replaced later by a 'goodbye' message to avoid reading from a
    disconnected endpoint, allowing for more robust error reporting.

    When connected over a socket (e.g. mitogen.master.create_child()),
    ECONNRESET may be triggered by any read or write.


.. autofunction:: mitogen.master.create_child
.. autofunction:: mitogen.master.get_child_modules
.. autofunction:: mitogen.master.minimize_source
