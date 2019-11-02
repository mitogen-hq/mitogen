
Internal API Reference
**********************

.. note::

   Internal APIs are subject to rapid change even across minor releases. This
   page exists to help users modify and extend the library.


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

.. currentmodule:: mitogen.core
.. autoclass:: LogHandler
   :members:

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
.. autoclass:: BufferedWriter
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

.. currentmodule:: mitogen.parent
.. autoclass:: LogProtocol
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
.. autoclass:: Reaper
    :members:

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


.. _signals:

Signals
=======

Mitogen contains a simplistic signal mechanism to decouple its components. When
a signal is fired by an instance of a class, functions registered to receive it
are called back.

.. warning::

    As signals execute on the Broker thread, and without exception handling,
    they are generally unsafe for consumption by user code, as any bugs could
    trigger crashes and hangs for which the broker is unable to forward logs,
    or ensure the buggy context always shuts down on disconnect.


Functions
---------

.. currentmodule:: mitogen.core

.. autofunction:: listen
.. autofunction:: unlisten
.. autofunction:: fire


List
----

These signals are used internally by Mitogen.

.. list-table::
    :header-rows: 1
    :widths: auto

    * - Class
      - Name
      - Description

    * - :py:class:`mitogen.core.Stream`
      - ``disconnect``
      - Fired on the Broker thread when disconnection is detected.

    * - :py:class:`mitogen.core.Stream`
      - ``shutdown``
      - Fired on the Broker thread when broker shutdown begins.

    * - :py:class:`mitogen.core.Context`
      - ``disconnect``
      - Fired on the Broker thread during shutdown (???)

    * - :py:class:`mitogen.parent.Process`
      - ``exit``
      - Fired when :class:`mitogen.parent.Reaper` detects subprocess has fully
        exitted.

    * - :py:class:`mitogen.core.Broker`
      - ``shutdown``
      - Fired after Broker.shutdown() is called, but before ``shutdown`` event
        fires. This can be used to trigger any behaviour that relies on the
        process remaining intact, as processing of ``shutdown`` races with any
        parent sending the child a signal because it is not shutting down in
        reasonable time.

    * - :py:class:`mitogen.core.Broker`
      - ``shutdown``
      - Fired after Broker.shutdown() is called.

    * - :py:class:`mitogen.core.Broker`
      - ``exit``
      - Fired immediately prior to the broker thread exit.
