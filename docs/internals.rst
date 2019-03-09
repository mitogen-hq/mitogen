
Internal API Reference
**********************

.. toctree::
    :hidden:

    signals


Constants
=========

.. currentmodule:: mitogen.core
.. autodata:: CHUNK_SIZE


Pollers
=======

.. currentmodule:: mitogen.core
.. autoclass:: Poller
    :members:

.. currentmodule:: mitogen.parent
.. autoclass:: KqueuePoller

.. currentmodule:: mitogen.parent
.. autoclass:: EpollPoller

.. currentmodule:: mitogen.parent
.. autoclass:: PollPoller


Latch
=====

.. currentmodule:: mitogen.core
.. autoclass:: Latch
   :members:


PidfulStreamHandler
===================

.. currentmodule:: mitogen.core
.. autoclass:: PidfulStreamHandler
   :members:


Side
====

.. currentmodule:: mitogen.core
.. autoclass:: Side
   :members:


Stream
======

.. currentmodule:: mitogen.core
.. autoclass:: BasicStream
   :members:

.. autoclass:: Stream
   :members:

.. currentmodule:: mitogen.fork
.. autoclass:: Stream
   :members:

.. currentmodule:: mitogen.parent
.. autoclass:: Stream
   :members:

.. currentmodule:: mitogen.ssh
.. autoclass:: Stream
   :members:

.. currentmodule:: mitogen.sudo
.. autoclass:: Stream
   :members:

.. currentmodule:: mitogen.core
.. autoclass:: IoLogger
   :members:

.. currentmodule:: mitogen.core
.. autoclass:: Waker
   :members:


Importer
========

.. currentmodule:: mitogen.core
.. autoclass:: Importer
   :members:


ModuleResponder
===============

.. currentmodule:: mitogen.master
.. autoclass:: ModuleResponder
   :members:


RouteMonitor
============

.. currentmodule:: mitogen.parent
.. autoclass:: RouteMonitor
   :members:


TimerList
=========

.. currentmodule:: mitogen.parent
.. autoclass:: TimerList
   :members:


Timer
=====

.. currentmodule:: mitogen.parent
.. autoclass:: Timer
   :members:


Forwarder
=========

.. currentmodule:: mitogen.parent
.. autoclass:: ModuleForwarder
   :members:


ExternalContext
===============

.. currentmodule:: mitogen.core
.. autoclass:: ExternalContext
    :members:


Process
=======

.. currentmodule:: mitogen.parent
.. autoclass:: Process
    :members:


Helpers
=======

Blocking I/O
------------

These functions exist to support the blocking phase of setting up a new
context. They will eventually be replaced with asynchronous equivalents.


.. currentmodule:: mitogen.parent
.. autofunction:: discard_until
.. autofunction:: iter_read
.. autofunction:: write_all


Subprocess Functions
------------

.. currentmodule:: mitogen.parent
.. autofunction:: create_child
.. autofunction:: hybrid_tty_create_child
.. autofunction:: tty_create_child


Helpers
-------

.. currentmodule:: mitogen.core
.. autofunction:: to_text
.. autofunction:: has_parent_authority
.. autofunction:: set_cloexec
.. autofunction:: set_nonblock
.. autofunction:: set_block
.. autofunction:: io_op

.. currentmodule:: mitogen.parent
.. autofunction:: close_nonstandard_fds
.. autofunction:: create_socketpair

.. currentmodule:: mitogen.master
.. autofunction:: get_child_modules

.. currentmodule:: mitogen.minify
.. autofunction:: minimize_source


Signals
=======

:ref:`Please refer to Signals <signals>`.
