
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
    since :py:meth:`__iter__` terminates once the final receiver is removed,
    this makes it convenient to respond to calls made in parallel:

    .. code-block:: python

        total = 0
        recvs = [c.call_async(long_running_operation) for c in contexts]

        with mitogen.master.Select(recvs) as select:
            for recv, (msg, data) in select:
                print 'Got %s from %s' % (data, recv)
                total += data

        # Iteration ends when last Receiver yields a result.
        print 'Received total %s from %s receivers' % (total, len(recvs))

    :py:class:`Select` may drive a long-running scheduler:

    .. code-block:: python

        with mitogen.master.Select(oneshot=False) as select:
            while running():
                for recv, (msg, data) in select:
                    process_result(recv.context, msg.unpickle())
                for context, workfunc in get_new_work():
                    select.add(context.call_async(workfunc))

    :py:class:`Select` may be nested:

    .. code-block:: python

        subselects = [
            mitogen.master.Select(get_some_work()),
            mitogen.master.Select(get_some_work()),
            mitogen.master.Select([
                mitogen.master.Select(get_some_work()),
                mitogen.master.Select(get_some_work())
            ])
        ]

        with mitogen.master.Select(selects) as select:
            for _, (msg, data) in select:
                print data

    .. py:method:: get (timeout=None)

        Fetch the next available value from any receiver, or raise
        :py:class:`mitogen.core.TimeoutError` if no value is available within
        `timeout` seconds.

        :param float timeout:
            Timeout in seconds.

        :return:
            `(receiver, (msg, data))`

    .. py:method:: __bool__ ()

        Return ``True`` if any receivers are registered with this select.

    .. py:method:: close ()

        Remove the select's notifier function from each registered receiver.
        Necessary to prevent memory leaks in long-running receivers. This is
        called automatically when the Python ``with:`` statement is used.

    .. py:method:: empty ()

        Return ``True`` if calling :py:meth:`get` would block.

        As with :py:class:`Queue.Queue`, ``True`` may be returned even though a
        subsequent call to :py:meth:`get` will succeed, since a message may be
        posted at any moment between :py:meth:`empty` and :py:meth:`get`.

        :py:meth:`empty` may return ``False`` even when :py:meth:`get` would
        block if another thread has drained a receiver added to this select.
        This can be avoided by only consuming each receiver from a single
        thread.

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
-------------

.. autoclass:: mitogen.master.Context
   :members:
   :inherited-members:


Receiver Class
--------------

.. class:: mitogen.core.Receiver (router, handle=None, persist=True, respondent=None)

    Receivers are used to wait for pickled responses from another context to be
    sent to a handle registered in this context. A receiver may be single-use
    (as in the case of :py:meth:`mitogen.master.Context.call_async`) or
    multiple use.

    :param mitogen.core.Router router:
        Router to register the handler on.

    :param int handle:
        If not ``None``, an explicit handle to register, otherwise an unused
        handle is chosen.

    :param bool persist:
        If ``True``, do not unregister the receiver's handler after the first
        message.

    :param mitogen.core.Context respondent:
        Reference to the context this receiver is receiving from. If not
        ``None``, arranges for the receiver to receive
        :py:data:`mitogen.core._DEAD` if messages can no longer be routed to
        the context, due to disconnection or exit.

    .. attribute:: notify = None

        If not ``None``, a reference to a function invoked as
        `notify(receiver)` when a new message is delivered to this receiver.
        Used by :py:class:`mitogen.master.Select` to implement waiting on
        multiple receivers.

    .. py:method:: empty ()

        Return ``True`` if calling :py:meth:`get` would block.

        As with :py:class:`Queue.Queue`, ``True`` may be returned even though a
        subsequent call to :py:meth:`get` will succeed, since a message may be
        posted at any moment between :py:meth:`empty` and :py:meth:`get`.

        :py:meth:`empty` is only useful to avoid a race while installing
        :py:attr:`notify`:

        .. code-block:: python

            recv.notify = _my_notify_function
            if not recv.empty():
                _my_notify_function(recv)

            # It is guaranteed the receiver was empty after the notification
            # function was installed, or that it was non-empty and the
            # notification function was invoked.

    .. py:method:: close ()

        Cause :py:class:`mitogen.core.ChannelError` to be raised in any thread
        waiting in :py:meth:`get` on this receiver.

    .. py:method:: get (timeout=None)

        Sleep waiting for a message to arrive on this receiver.

        :param float timeout:
            If not ``None``, specifies a timeout in seconds.

        :raises mitogen.core.ChannelError:
            The remote end indicated the channel should be closed, or
            communication with its parent context was lost.

        :raises mitogen.core.TimeoutError:
            Timeout was reached.

        :returns:
            `(msg, data)` tuple, where `msg` is the
            :py:class:`mitogen.core.Message` that was received, and `data` is
            its unpickled data part.

    .. py:method:: get_data (timeout=None)

        Like :py:meth:`get`, except only return the data part.

    .. py:method:: __iter__ ()

        Block and yield `(msg, data)` pairs delivered to this receiver until
        :py:class:`mitogen.core.ChannelError` is raised.


Sender Class
------------

.. class:: mitogen.core.Sender (context, dst_handle)

    Senders are used to send pickled messages to a handle in another context,
    it is the inverse of :py:class:`mitogen.core.Sender`.

    :param mitogen.core.Context context:
        Context to send messages to.
    :param int dst_handle:
        Destination handle to send messages to.

    .. py:method:: close ()

        Send :py:data:`mitogen.core._DEAD` to the remote end, causing
        :py:meth:`ChannelError` to be raised in any waiting thread.

    .. py:method:: put (data)

        Send `data` to the remote end.


Channel Class
-------------

.. class:: mitogen.core.Channel (router, context, dst_handle, handle=None)

    A channel inherits from :py:class:`mitogen.core.Sender` and
    `mitogen.core.Receiver` to provide bidirectional functionality.

    Since all handles aren't known until after both ends are constructed, for
    both ends to communicate through a channel, it is necessary for one end to
    retrieve the handle allocated to the other and reconfigure its own channel
    to match. Currently this is a manual task.



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
