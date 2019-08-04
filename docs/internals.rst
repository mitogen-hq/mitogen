
Internal API Reference
**********************

.. note::

   Internal APIs are subject to rapid change even across minor releases. This
   page exists to help users modify and extend the library.

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


Logging
=======

See also :class:`mitogen.core.IoLoggerProtocol`.

.. currentmodule:: mitogen.master
.. autoclass:: LogForwarder
   :members:

.. currentmodule:: mitogen.core
.. autoclass:: PidfulStreamHandler
   :members:


Stream, Side & Protocol
=======================

.. currentmodule:: mitogen.core
.. autoclass:: Stream
   :members:

.. currentmodule:: mitogen.core
.. autoclass:: Side
   :members:

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


Connection & Options
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


Import Mechanism
================

.. currentmodule:: mitogen.core
.. autoclass:: Importer
   :members:

.. currentmodule:: mitogen.master
.. autoclass:: ModuleResponder
   :members:

.. currentmodule:: mitogen.parent
.. autoclass:: ModuleForwarder
   :members:


Module Finders
==============

.. currentmodule:: mitogen.master
.. autoclass:: ModuleFinder
   :members:

.. currentmodule:: mitogen.master
.. autoclass:: FinderMethod
   :members:

.. currentmodule:: mitogen.master
.. autoclass:: DefectivePython3xMainMethod
   :members:

.. currentmodule:: mitogen.master
.. autoclass:: PkgutilMethod
   :members:

.. currentmodule:: mitogen.master
.. autoclass:: SysModulesMethod
   :members:

.. currentmodule:: mitogen.master
.. autoclass:: ParentEnumerationMethod
   :members:


Routing Management
==================

.. currentmodule:: mitogen.parent
.. autoclass:: RouteMonitor
   :members:


Timer Management
================

.. currentmodule:: mitogen.parent
.. autoclass:: TimerList
   :members:

.. currentmodule:: mitogen.parent
.. autoclass:: Timer
   :members:


Context ID Allocation
=====================

.. currentmodule:: mitogen.master
.. autoclass:: IdAllocator
   :members:

.. currentmodule:: mitogen.parent
.. autoclass:: ChildIdAllocator
   :members:


Child Implementation
====================

.. currentmodule:: mitogen.core
.. autoclass:: ExternalContext
    :members:

.. currentmodule:: mitogen.core
.. autoclass:: Dispatcher
    :members:


Process Management
==================

.. currentmodule:: mitogen.parent
.. autoclass:: Process
    :members:

.. currentmodule:: mitogen.parent
.. autoclass:: PopenProcess
    :members:

.. currentmodule:: mitogen.fork
.. autoclass:: Process
    :members:


Helper Functions
================


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
