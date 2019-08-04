
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


Stream & Side
=============

.. currentmodule:: mitogen.core
.. autoclass:: Stream
   :members:

.. currentmodule:: mitogen.core
.. autoclass:: Side
   :members:


Protocol
========

.. currentmodule:: mitogen.core
.. autoclass:: Protocol
   :members:

.. currentmodule:: mitogen.parent
.. autoclass:: BootstrapProtocol
   :members:

.. currentmodule:: mitogen.core
.. autoclass:: DelimitedProtocol
   :members:

.. currentmodule:: mitogen.core
.. autoclass:: IoLoggerProtocol
   :members:

.. currentmodule:: mitogen.core
.. autoclass:: MitogenProtocol
   :members:

.. currentmodule:: mitogen.parent
.. autoclass:: MitogenProtocol
   :members:

.. currentmodule:: mitogen.core
.. autoclass:: Waker
   :members:


Connection / Options
====================

.. currentmodule:: mitogen.fork
.. autoclass:: Options
   :members:
.. autoclass:: Connection
   :members:

.. currentmodule:: mitogen.parent
.. autoclass:: Options
   :members:
.. autoclass:: Connection
   :members:

.. currentmodule:: mitogen.ssh
.. autoclass:: Options
   :members:
.. autoclass:: Connection
   :members:

.. currentmodule:: mitogen.sudo
.. autoclass:: Options
   :members:
.. autoclass:: Connection
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


Subprocess Functions
---------------------

.. currentmodule:: mitogen.parent
.. autofunction:: create_child
.. autofunction:: hybrid_tty_create_child
.. autofunction:: tty_create_child


Helpers
-------

.. currentmodule:: mitogen.core
.. autofunction:: has_parent_authority
.. autofunction:: io_op
.. autofunction:: pipe
.. autofunction:: set_block
.. autofunction:: set_cloexec
.. autofunction:: set_nonblock
.. autofunction:: to_text

.. currentmodule:: mitogen.parent
.. autofunction:: create_socketpair

.. currentmodule:: mitogen.master
.. autofunction:: get_child_modules

.. currentmodule:: mitogen.minify
.. autofunction:: minimize_source


Signals
=======

:ref:`Please refer to Signals <signals>`.
