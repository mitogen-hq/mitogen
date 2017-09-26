
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

.. module:: mitogen.master

This module implements functionality required by master processes, such as
starting new contexts via SSH. Its size is also restricted, since it must
be sent to any context that will be used to establish additional child
contexts.


.. class:: mitogen.master.Select (receivers=(), oneshot=True)

    Support scatter/gather asynchronous calls and waiting on multiple
    receivers, channels, and sub-Selects. Accepts a sequence of
    :py:class:`mitogen.core.Receiver` or :py:class:`mitogen.master.Select`
    instances and returns the first value posted to any receiver or select.

    If `oneshot` is ``True``, then remove each receiver as it yields a result;
    since :py:meth:`__iter__` terminates once the final receiver is removed
    from the select, this makes it convenient to respond to several call
    results with minimal effort:

    .. code-block:: python

        total = 0
        recvs = [c.call_async(long_running_operation) for c in contexts]

        with mitogen.master.Select(recvs) as select:
            for recv, msg in select:
                value = msg.unpickle()
                print 'Got %s from %s' % (value, recv)
                total += value

        # Iteration ends when last Receiver yields a result.
        print 'Received total %s from %s receivers' % (total, len(recvs))

    :py:class:`Select` may also be used to drive a long-running scheduler:

    .. code-block:: python

        with mitogen.master.Select() as select:
            while running():
                for recv, msg in select:
                    process_result(recv.context, msg.unpickle())
                for context, workfunc in get_new_work():
                    select.add(context.call_async(workfunc))

    :py:class:`Select` may be nested:

    .. code-block:: python

        subselects = [
            mitogen.master.Select(get_some_work()),
            mitogen.master.Select(get_some_work())
        ]

        with mitogen.master.Select(selects, oneshot=False) as select:
            while subselects and any(subselects):  # Calls __bool__()
                print select.get()

    .. py:method:: get (timeout=None)

        Fetch the next available value from any receiver, or raise
        :py:class:`mitogen.core.TimeoutError` if no value is available within
        `timeout` seconds.

        :param float timeout:
            Timeout in seconds.

        :return:
            `(receiver, msg)`

    .. py:method:: __bool__ ()

        Return ``True`` if any receivers are registered with this select.

    .. py:method:: close ()

        Remove the select's notifier function from each registered receiver.
        Necessary to prevent memory leaks in long-running receivers. This is
        called automatically when the Python ``with:`` statement is used.

    .. py:method:: empty ()

        Return ``True`` if no items appear to be queued on this receiver. Like
        :py:class:`Queue.Queue`, this function's return value cannot be relied
        upon.

    .. py:method:: __iter__ (self)

        Yield the result of :py:meth:`get` until no receivers remain in the
        select, either because `oneshot` is ``True``, or each receiver was
        explicitly removed via :py:meth:`remove`.

    .. py:method:: add (recv)

        Add the :py:class:`mitogen.core.Receiver` or
        :py:class:`mitogen.core.Channel` `recv` to the select.

    .. py:method:: remove (recv)

        Remove the :py:class:`mitogen.core.Receiver` or
        :py:class:`mitogen.core.Channel` `recv` from the select. Note that if
        the receiver has notified prior to :py:meth:`remove`, then it will
        still be returned by a subsequent :py:meth:`get`. This may change in a
        future version.


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
