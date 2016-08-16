
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


Stream Classes
--------------

.. autoclass:: econtext.core.Stream
   :members:


Broker Class
------------

.. autoclass:: econtext.core.Broker
   :members:


Context Class
-------------

.. autoclass:: econtext.core.Context
   :members:


Channel Class
-------------

.. autoclass:: econtext.core.Channel
   :members:


ExternalContext Class
---------------------

.. class:: econtext.core.ExternalContext

    External context implementation.

    .. attribute:: broker

        The :py:class:`econtext.core.Broker` instance.

    .. attribute:: context

            The :py:class:`econtext.core.Context` instance.

    .. attribute:: channel

            The :py:class:`econtext.core.Channel` over which
            :py:data:`CALL_FUNCTION` requests are received.

    .. attribute:: stdout_log

        The :py:class:`econtext.core.IoLogger` connected to ``stdout``.

    .. attribute:: importer

        The :py:class:`econtext.core.Importer` instance.

    .. attribute:: stdout_log

        The :py:class:`IoLogger` connected to ``stdout``.

    .. attribute:: stderr_log

        The :py:class:`IoLogger` connected to ``stderr``.


econtext.master
===============

.. automodule:: econtext.master


Broker Class
------------

.. autoclass:: econtext.master.Broker
   :members:


Context Class
-------------

.. autoclass:: econtext.master.Context
   :members:


econtext.utils
==============

.. automodule:: econtext.utils
  :members:
