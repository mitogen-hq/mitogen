
Internal API Reference
**********************


mitogen.core
============


Side Class
----------

.. currentmodule:: mitogen.core

.. autoclass:: Side
   :members:


Stream Classes
--------------

.. currentmodule:: mitogen.core

.. autoclass:: BasicStream
   :members:

.. autoclass:: Stream
   :members:

.. currentmodule:: mitogen.master

.. autoclass:: Stream
   :members:

.. currentmodule:: mitogen.ssh

.. autoclass:: Stream
   :members:

.. currentmodule:: mitogen.sudo

.. autoclass:: Stream
   :members:


Other Stream Subclasses
-----------------------

.. currentmodule:: mitogen.core

.. autoclass:: IoLogger
   :members:

.. autoclass:: Waker
   :members:


Importer Class
--------------

.. currentmodule:: mitogen.core
.. autoclass:: Importer
   :members:


ExternalContext Class
---------------------

.. currentmodule:: mitogen.core

.. class:: ExternalContext

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

    .. method:: _dispatch_calls

        Implementation for the main thread in every child context.

mitogen.master
==============

.. currentmodule:: mitogen.master

.. class:: ProcessMonitor

    Install a :py:data:`signal.SIGCHLD` handler that generates callbacks when a
    specific child process has exitted.

    .. method:: add (pid, callback)

        Add a callback function to be notified of the exit status of a process.

        :param int pid:
            Process ID to be notified of.

        :param callback:
            Function invoked as `callback(status)`, where `status` is the raw
            exit status of the child process.


Blocking I/O Functions
----------------------

These functions exist to support the blocking phase of setting up a new
context. They will eventually be replaced with asynchronous equivalents.


.. currentmodule:: mitogen.master

.. function:: iter_read(fd, deadline=None)

    Return a generator that arranges for up to 4096-byte chunks to be read at a
    time from the file descriptor `fd` until the generator is destroyed.

    :param fd:
        File descriptor to read from.

    :param deadline:
        If not ``None``, an absolute UNIX timestamp after which timeout should
        occur.

    :raises mitogen.core.TimeoutError:
        Attempt to read beyond deadline.

    :raises mitogen.core.StreamError:
        Attempt to read past end of file.


.. currentmodule:: mitogen.master

.. function:: write_all (fd, s, deadline=None)

    Arrange for all of bytestring `s` to be written to the file descriptor
    `fd`.

    :param int fd:
        File descriptor to write to.

    :param bytes s:
        Bytestring to write to file descriptor.

    :param float deadline:
        If not ``None``, an absolute UNIX timestamp after which timeout should
        occur.

    :raises mitogen.core.TimeoutError:
        Bytestring could not be written entirely before deadline was exceeded.

    :raises mitogen.core.StreamError:
        File descriptor was disconnected before write could complete.


Helper Functions
----------------

.. currentmodule:: mitogen.core

.. function:: io_op (func, \*args)

    When connected over a TTY (i.e. sudo), disconnection of the remote end is
    signalled by EIO, rather than an empty read like sockets or pipes. Ideally
    this will be replaced later by a 'goodbye' message to avoid reading from a
    disconnected endpoint, allowing for more robust error reporting.

    When connected over a socket (e.g. mitogen.master.create_child()),
    ECONNRESET may be triggered by any read or write.


.. currentmodule:: mitogen.master

.. function:: create_child (\*args)

    Create a child process whose stdin/stdout is connected to a socket,
    returning `(pid, socket_obj)`.


.. currentmodule:: mitogen.master

.. function:: tty_create_child (\*args)

    Return a file descriptor connected to the master end of a pseudo-terminal,
    whose slave end is connected to stdin/stdout/stderr of a new child process.
    The child is created such that the pseudo-terminal becomes its controlling
    TTY, ensuring access to /dev/tty returns a new file descriptor open on the
    slave end.

    :param list args:
        :py:func:`os.execl` argument list.

    :returns:
        `(pid, fd)`


.. currentmodule:: mitogen.master

.. function:: get_child_modules (path, fullname)

    Return the canonical names of all submodules of a package `module`.

    :param str path:
        Path to the module's source code on disk, or some PEP-302-recognized
        equivalent. Usually this is the module's ``__file__`` attribute, but
        is specified explicitly to avoid loading the module.

    :param str fullname:
        The module's canonical name. This is the module's ``__name__``
        attribute, but is specified explicitly to avoid loading the module.

    :return:
        List of canonical submodule names.


.. currentmodule:: mitogen.master

.. autofunction:: minimize_source (source)

    Remove comments and docstrings from Python `source`, preserving line
    numbers and syntax of empty blocks.

    :param str source:
        The source to minimize.

    :returns str:
        The minimized source.
