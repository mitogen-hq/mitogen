
API Reference
*************


Package Layout
==============


econtext Package
----------------

.. automodule:: econtext

.. autodata:: econtext.slave
.. autodata:: econtext.context_id
.. autodata:: econtext.parent_id


econtext.core
-------------

.. automodule:: econtext.core


econtext.master
---------------

.. automodule:: econtext.master


econtext.fakessh
---------------

.. automodule:: econtext.fakessh

.. autofunction:: econtext.fakessh.run_with_fake_ssh


Router Class
============

.. autoclass:: econtext.master.Router
   :members:
   :inherited-members:


Broker Class
============

.. autoclass:: econtext.master.Broker
   :members:
   :inherited-members:


Context Class
=============

.. autoclass:: econtext.master.Context
   :members:
   :inherited-members:


Channel Class
-------------

.. autoclass:: econtext.core.Channel
   :members:


Context Class
-------------

.. autoclass:: econtext.master.Context
   :members:


Utility Functions
=================

.. automodule:: econtext.utils
  :members:


Exceptions
==========

.. autoclass:: econtext.core.Error
.. autoclass:: econtext.core.CallError
.. autoclass:: econtext.core.ChannelError
.. autoclass:: econtext.core.StreamError
.. autoclass:: econtext.core.TimeoutError
