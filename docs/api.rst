
API Reference
*************


Package Layout
==============


mitogen Package
---------------

.. automodule:: mitogen

.. autodata:: mitogen.is_master
.. autodata:: mitogen.context_id
.. autodata:: mitogen.parent_id


mitogen.core
------------

.. module:: mitogen.core

This module implements most package functionality, but remains separate from
non-essential code in order to reduce its size, since it is also serves as the
bootstrap implementation sent to every new slave context.

.. function:: mitogen.core.takes_econtext

    Decorator that marks a function or class method to automatically receive a
    kwarg named `econtext`, referencing the
    :py:class:`econtext.core.ExternalContext` active in the context in which
    the function is being invoked in. The decorator is only meaningful when the
    function is invoked via :py:data:`econtext.core.CALL_FUNCTION`.

    When the function is invoked directly, `econtext` must still be passed to it
    explicitly.

.. function:: mitogen.core.takes_router

    Decorator that marks a function or class method to automatically receive a
    kwarg named `router`, referencing the :py:class:`econtext.core.Router`
    active in the context in which the function is being invoked in. The
    decorator is only meaningful when the function is invoked via
    :py:data:`econtext.core.CALL_FUNCTION`.

    When the function is invoked directly, `router` must still be passed to it
    explicitly.


mitogen.master
--------------

.. automodule:: mitogen.master


mitogen.fakessh
---------------

.. automodule:: mitogen.fakessh

.. autofunction:: mitogen.fakessh.run


Router Class
============

.. autoclass:: mitogen.master.Router
   :members:
   :inherited-members:


Broker Class
============

.. autoclass:: mitogen.master.Broker
   :members:
   :inherited-members:


Context Class
=============

.. autoclass:: mitogen.master.Context
   :members:
   :inherited-members:


Channel Class
-------------

.. autoclass:: mitogen.core.Channel
   :members:


Context Class
-------------

.. autoclass:: mitogen.master.Context
   :members:


Utility Functions
=================

.. automodule:: mitogen.utils
  :members:


Exceptions
==========

.. class:: mitogen.core.Error (fmt, \*args)

    Base for all exceptions raised by Mitogen.

.. class:: mitogen.core.CallError (e)

    Raised when :py:meth:`Context.call() <mitogen.master.Context.call>` fails.
    A copy of the traceback from the external context is appended to the
    exception message.

.. class:: mitogen.core.ChannelError (fmt, \*args)

    Raised when a channel dies or has been closed.

.. class:: mitogen.core.StreamError (fmt, \*args)

    Raised when a stream cannot be established.

.. autoclass:: mitogen.core.TimeoutError (fmt, \*args)

    Raised when a timeout occurs on a stream.
