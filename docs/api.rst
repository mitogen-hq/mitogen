
API Reference
*************


Package Layout
==============


econtext Package
----------------

.. automodule:: econtext


econtext.core
-------------

.. automodule:: econtext.core


econtext.master
---------------

.. automodule:: econtext.master



Context Factories
=================

.. autofunction:: econtext.master.connect
.. autofunction:: econtext.ssh.connect
.. autofunction:: econtext.sudo.connect


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


Detecting A Slave
=================

.. autodata:: econtext.slave


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
