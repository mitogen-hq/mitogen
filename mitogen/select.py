# Copyright 2019, David Wilson
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

# !mitogen: minify_safe

import mitogen.core


class Error(mitogen.core.Error):
    pass


class Select(object):
    """
    Support scatter/gather asynchronous calls and waiting on multiple
    receivers, channels, and sub-Selects. Accepts a sequence of
    :class:`mitogen.core.Receiver` or :class:`mitogen.select.Select` instances
    and returns the first value posted to any receiver or select.

    If `oneshot` is :data:`True`, then remove each receiver as it yields a
    result; since :meth:`__iter__` terminates once the final receiver is
    removed, this makes it convenient to respond to calls made in parallel:

    .. code-block:: python

        total = 0
        recvs = [c.call_async(long_running_operation) for c in contexts]

        for msg in mitogen.select.Select(recvs):
            print('Got %s from %s' % (msg, msg.receiver))
            total += msg.unpickle()

        # Iteration ends when last Receiver yields a result.
        print('Received total %s from %s receivers' % (total, len(recvs)))

    :class:`Select` may drive a long-running scheduler:

    .. code-block:: python

        with mitogen.select.Select(oneshot=False) as select:
            while running():
                for msg in select:
                    process_result(msg.receiver.context, msg.unpickle())
                for context, workfunc in get_new_work():
                    select.add(context.call_async(workfunc))

    :class:`Select` may be nested:

    .. code-block:: python

        subselects = [
            mitogen.select.Select(get_some_work()),
            mitogen.select.Select(get_some_work()),
            mitogen.select.Select([
                mitogen.select.Select(get_some_work()),
                mitogen.select.Select(get_some_work())
            ])
        ]

        for msg in mitogen.select.Select(selects):
            print(msg.unpickle())
    """

    notify = None

    def __init__(self, receivers=(), oneshot=True):
        self._receivers = []
        self._oneshot = oneshot
        self._latch = mitogen.core.Latch()
        for recv in receivers:
            self.add(recv)

    @classmethod
    def all(cls, receivers):
        """
        Take an iterable of receivers and retrieve a :class:`Message` from
        each, returning the result of calling `msg.unpickle()` on each in turn.
        Results are returned in the order they arrived.

        This is sugar for handling batch :meth:`Context.call_async
        <mitogen.parent.Context.call_async>` invocations:

        .. code-block:: python

            print('Total disk usage: %.02fMiB' % (sum(
                mitogen.select.Select.all(
                    context.call_async(get_disk_usage)
                    for context in contexts
                ) / 1048576.0
            ),))

        However, unlike in a naive comprehension such as:

        .. code-block:: python

            recvs = [c.call_async(get_disk_usage) for c in contexts]
            sum(recv.get().unpickle() for recv in recvs)

        Result processing happens in the order results arrive, rather than the
        order requests were issued, so :meth:`all` should always be faster.
        """
        return list(msg.unpickle() for msg in cls(receivers))

    def _put(self, value):
        self._latch.put(value)
        if self.notify:
            self.notify(self)

    def __bool__(self):
        """
        Return :data:`True` if any receivers are registered with this select.
        """
        return bool(self._receivers)

    __nonzero__ = __bool__

    def __enter__(self):
        return self

    def __exit__(self, e_type, e_val, e_tb):
        self.close()

    def __iter__(self):
        """
        Yield the result of :meth:`get` until no receivers remain in the
        select, either because `oneshot` is :data:`True`, or each receiver was
        explicitly removed via :meth:`remove`.
        """
        while self._receivers:
            yield self.get()

    loop_msg = 'Adding this Select instance would create a Select cycle'

    def _check_no_loop(self, recv):
        if recv is self:
            raise Error(self.loop_msg)

        for recv_ in self._receivers:
            if recv_ == recv:
                raise Error(self.loop_msg)
            if isinstance(recv_, Select):
                recv_._check_no_loop(recv)

    owned_msg = 'Cannot add: Receiver is already owned by another Select'

    def add(self, recv):
        """
        Add the :class:`mitogen.core.Receiver` or :class:`Select` `recv` to the
        select.

        :raises mitogen.select.Error:
            An attempt was made to add a :class:`Select` to which this select
            is indirectly a member of.
        """
        if isinstance(recv, Select):
            recv._check_no_loop(self)

        self._receivers.append(recv)
        if recv.notify is not None:
            raise Error(self.owned_msg)

        recv.notify = self._put
        # Avoid race by polling once after installation.
        if not recv.empty():
            self._put(recv)

    not_present_msg = 'Instance is not a member of this Select'

    def remove(self, recv):
        """
        Remove the :class:`mitogen.core.Receiver` or :class:`Select` `recv`
        from the select. Note that if the receiver has notified prior to
        :meth:`remove`, it will still be returned by a subsequent :meth:`get`.
        This may change in a future version.
        """
        try:
            if recv.notify != self._put:
                raise ValueError
            self._receivers.remove(recv)
            recv.notify = None
        except (IndexError, ValueError):
            raise Error(self.not_present_msg)

    def close(self):
        """
        Remove the select's notifier function from each registered receiver,
        mark the associated latch as closed, and cause any thread currently
        sleeping in :meth:`get` to be woken with
        :class:`mitogen.core.LatchError`.

        This is necessary to prevent memory leaks in long-running receivers. It
        is called automatically when the Python :keyword:`with` statement is
        used.
        """
        for recv in self._receivers[:]:
            self.remove(recv)
        self._latch.close()

    def empty(self):
        """
        Return :data:`True` if calling :meth:`get` would block.

        As with :class:`Queue.Queue`, :data:`True` may be returned even though
        a subsequent call to :meth:`get` will succeed, since a message may be
        posted at any moment between :meth:`empty` and :meth:`get`.

        :meth:`empty` may return :data:`False` even when :meth:`get` would
        block if another thread has drained a receiver added to this select.
        This can be avoided by only consuming each receiver from a single
        thread.
        """
        return self._latch.empty()

    empty_msg = 'Cannot get(), Select instance is empty'

    def get(self, timeout=None, block=True):
        """
        Fetch the next available value from any receiver, or raise
        :class:`mitogen.core.TimeoutError` if no value is available within
        `timeout` seconds.

        On success, the message's :attr:`receiver
        <mitogen.core.Message.receiver>` attribute is set to the receiver.

        :param float timeout:
            Timeout in seconds.
        :param bool block:
            If :data:`False`, immediately raise
            :class:`mitogen.core.TimeoutError` if the select is empty.
        :return:
            :class:`mitogen.core.Message`
        :raises mitogen.core.TimeoutError:
            Timeout was reached.
        :raises mitogen.core.LatchError:
            :meth:`close` has been called, and the underlying latch is no
            longer valid.
        """
        if not self._receivers:
            raise Error(self.empty_msg)

        while True:
            recv = self._latch.get(timeout=timeout, block=block)
            try:
                msg = recv.get(block=False)
                if self._oneshot:
                    self.remove(recv)
                msg.receiver = recv
                return msg
            except mitogen.core.TimeoutError:
                # A receiver may have been queued with no result if another
                # thread drained it before we woke up, or because another
                # thread drained it between add() calling recv.empty() and
                # self._put(). In this case just sleep again.
                continue
