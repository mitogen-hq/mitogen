
API Reference
*************


Package Layout
==============


mitogen Package
---------------

.. automodule:: mitogen

.. autodata:: mitogen.master
.. autodata:: mitogen.context_id
.. autodata:: mitogen.parent_id


mitogen.core
------------

.. automodule:: mitogen.core


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
