
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

.. automodule:: mitogen.core

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

.. autoclass:: mitogen.core.Error
.. autoclass:: mitogen.core.CallError
.. autoclass:: mitogen.core.ChannelError
.. autoclass:: mitogen.core.StreamError
.. autoclass:: mitogen.core.TimeoutError
