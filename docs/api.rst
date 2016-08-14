
API Reference
*************


econtext Package
================

.. automodule:: econtext

.. autodata:: econtext.slave


econtext.core
=============

.. automodule:: econtext.core


Exceptions
----------

.. autoclass:: econtext.core.Error
.. autoclass:: econtext.core.CallError
.. autoclass:: econtext.core.ChannelError
.. autoclass:: econtext.core.StreamError
.. autoclass:: econtext.core.TimeoutError


Context Class
-------------

.. autoclass:: econtext.core.Context
   :members:


Channel Class
-------------

.. autoclass:: econtext.core.Channel
   :members:


econtext.master
===============

.. automodule:: econtext.master


Helper Functions
----------------

.. autofunction:: econtext.master.create_child
.. autofunction:: econtext.master.get_child_modules
.. autofunction:: econtext.master.minimize_source


Broker Class
------------

.. autoclass:: econtext.master.Broker
   :members:


Stream Classes
--------------

.. autoclass:: econtext.master.LocalStream
   :members:

.. autoclass:: econtext.master.SshStream
   :members:


econtext.utils
==============

.. automodule:: econtext.utils
  :members:
