
API Reference
*************

.. toctree::
    :hidden:

    signals


Package Layout
==============


mitogen Package
---------------

.. automodule:: mitogen

.. autodata:: mitogen.is_master
.. autodata:: mitogen.context_id
.. autodata:: mitogen.parent_id
.. autodata:: mitogen.parent_ids
.. autofunction:: mitogen.main


mitogen.core
------------

.. module:: mitogen.core

This module implements most package functionality, but remains separate from
non-essential code in order to reduce its size, since it is also serves as the
bootstrap implementation sent to every new slave context.

.. currentmodule:: mitogen.core
.. decorator:: takes_econtext

    Decorator that marks a function or class method to automatically receive a
    kwarg named `econtext`, referencing the
    :py:class:`mitogen.core.ExternalContext` active in the context in which the
    function is being invoked in. The decorator is only meaningful when the
    function is invoked via :py:data:`CALL_FUNCTION
    <mitogen.core.CALL_FUNCTION>`.

    When the function is invoked directly, `econtext` must still be passed to
    it explicitly.

.. currentmodule:: mitogen.core
.. decorator:: takes_router

    Decorator that marks a function or class method to automatically receive a
    kwarg named `router`, referencing the :py:class:`mitogen.core.Router`
    active in the context in which the function is being invoked in. The
    decorator is only meaningful when the function is invoked via
    :py:data:`CALL_FUNCTION <mitogen.core.CALL_FUNCTION>`.

    When the function is invoked directly, `router` must still be passed to it
    explicitly.


mitogen.master
--------------

.. module:: mitogen.master

This module implements functionality required by master processes, such as
starting new contexts via SSH. Its size is also restricted, since it must
be sent to any context that will be used to establish additional child
contexts.


.. currentmodule:: mitogen.master

.. class:: Select (receivers=(), oneshot=True)

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

        for msg in mitogen.master.Select(recvs):
            print 'Got %s from %s' % (msg, msg.receiver)
            total += msg.unpickle()

        # Iteration ends when last Receiver yields a result.
        print 'Received total %s from %s receivers' % (total, len(recvs))

    :py:class:`Select` may drive a long-running scheduler:

    .. code-block:: python

        with mitogen.master.Select(oneshot=False) as select:
            while running():
                for msg in select:
                    process_result(msg.receiver.context, msg.unpickle())
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

        for msg in mitogen.master.Select(selects):
            print msg.unpickle()

    .. py:classmethod:: all (it)

        Take an iterable of receivers and retrieve a :py:class:`Message` from
        each, returning the result of calling `msg.unpickle()` on each in turn.
        Results are returned in the order they arrived.

        This is sugar for handling batch :py:class:`Context.call_async`
        invocations:

        .. code-block:: python

            print('Total disk usage: %.02fMiB' % (sum(
                mitogen.master.Select.all(
                    context.call_async(get_disk_usage)
                    for context in contexts
                ) / 1048576.0
            ),))

        However, unlike in a naive comprehension such as:

        .. code-block:: python

            sum(context.call_async(get_disk_usage).get().unpickle()
                for context in contexts)

        Result processing happens concurrently to new results arriving, so
        :py:meth:`all` should always be faster.

    .. py:method:: get (timeout=None)

        Fetch the next available value from any receiver, or raise
        :py:class:`mitogen.core.TimeoutError` if no value is available within
        `timeout` seconds.

        On success, the message's :py:attr:`receiver
        <mitogen.core.Message.receiver>` attribute is set to the receiver.

        :param float timeout:
            Timeout in seconds.

        :return:
            :py:class:`mitogen.core.Message`
        :raises mitogen.core.TimeoutError:
            Timeout was reached.
        :raises mitogen.core.LatchError:
            :py:meth:`close` has been called, and the underlying latch is no
            longer valid.

    .. py:method:: __bool__ ()

        Return ``True`` if any receivers are registered with this select.

    .. py:method:: close ()

        Remove the select's notifier function from each registered receiver,
        mark the associated latch as closed, and cause any thread currently
        sleeping in :py:meth:`get` to be woken with
        :py:class:`mitogen.core.LatchError`.

        This is necessary to prevent memory leaks in long-running receivers. It
        is called automatically when the Python :keyword:`with` statement is
        used.

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

.. module:: mitogen.fakessh

fakessh is a stream implementation that starts a local subprocess with its
environment modified such that ``PATH`` searches for `ssh` return an mitogen
implementation of the SSH command. When invoked, this tool arranges for the
command line supplied by the calling program to be executed in a context
already established by the master process, reusing the master's (possibly
proxied) connection to that context.

This allows tools like `rsync` and `scp` to transparently reuse the connections
and tunnels already established by the host program to connect to a target
machine, without wasteful redundant SSH connection setup, 3-way handshakes, or
firewall hopping configurations, and enables these tools to be used in
impossible scenarios, such as over `sudo` with ``requiretty`` enabled.

The fake `ssh` command source is written to a temporary file on disk, and
consists of a copy of the :py:mod:`mitogen.core` source code (just like any
other child context), with a line appended to cause it to connect back to the
host process over an FD it inherits. As there is no reliance on an existing
filesystem file, it is possible for child contexts to use fakessh.

As a consequence of connecting back through an inherited FD, only one SSH
invocation is possible, which is fine for tools like `rsync`, however in future
this restriction will be lifted.

Sequence:

    1. ``fakessh`` Context and Stream created by parent context. The stream's
       buffer has a :py:func:`_fakessh_main` :py:data:`CALL_FUNCTION
       <mitogen.core.CALL_FUNCTION>` enqueued.
    2. Target program (`rsync/scp/sftp`) invoked, which internally executes
       `ssh` from ``PATH``.
    3. :py:mod:`mitogen.core` bootstrap begins, recovers the stream FD
       inherited via the target program, established itself as the fakessh
       context.
    4. :py:func:`_fakessh_main` :py:data:`CALL_FUNCTION
       <mitogen.core.CALL_FUNCTION>` is read by fakessh context,

        a. sets up :py:class:`IoPump` for stdio, registers
           stdin_handle for local context.
        b. Enqueues :py:data:`CALL_FUNCTION <mitogen.core.CALL_FUNCTION>` for
           :py:func:`_start_slave` invoked in target context,

            i. the program from the `ssh` command line is started
            ii. sets up :py:class:`IoPump` for `ssh` command line process's
                stdio pipes
            iii. returns `(control_handle, stdin_handle)` to
                 :py:func:`_fakessh_main`

    5. :py:func:`_fakessh_main` receives control/stdin handles from from
       :py:func:`_start_slave`,

        a. registers remote's stdin_handle with local :py:class:`IoPump`.
        b. sends `("start", local_stdin_handle)` to remote's control_handle
        c. registers local :py:class:`IoPump` with
           :py:class:`mitogen.core.Broker`.
        d. loops waiting for `local stdout closed && remote stdout closed`

    6. :py:func:`_start_slave` control channel receives `("start", stdin_handle)`,

        a. registers remote's stdin_handle with local :py:class:`IoPump`
        b. registers local :py:class:`IoPump` with
           :py:class:`mitogen.core.Broker`.
        c. loops waiting for `local stdout closed && remote stdout closed`


.. currentmodule:: mitogen.fakessh
.. function:: run (dest, router, args, daedline=None, econtext=None)

    Run the command specified by the argument vector `args` such that ``PATH``
    searches for SSH by the command will cause its attempt to use SSH to
    execute a remote program to be redirected to use mitogen to execute that
    program using the context `dest` instead.

    :param mitogen.core.Context dest:
        The destination context to execute the SSH command line in.

    :param mitogen.core.Router router:

    :param list[str] args:
        Command line arguments for local program, e.g.
        ``['rsync', '/tmp', 'remote:/tmp']``

    :returns:
        Exit status of the child process.


Message Class
=============

.. currentmodule:: mitogen.core

.. class:: Message

    .. attribute:: router

        The :py:class:`mitogen.core.Router` responsible for routing the
        message. This is :py:data:`None` for locally originated messages.

    .. attribute:: receiver

        The :py:class:`mitogen.core.Receiver` over which the message was last
        received. Part of the :py:class:`mitogen.master.Select` interface.
        Defaults to :py:data:`None`.

    .. attribute:: dst_id

    .. attribute:: src_id

    .. attribute:: auth_id

    .. attribute:: handle

    .. attribute:: reply_to

    .. attribute:: data

    .. py:method:: __init__ (\**kwargs)

        Construct a message from from the supplied `kwargs`. :py:attr:`src_id`
        and :py:attr:`auth_id` are always set to :py:data:`mitogen.context_id`.

    .. py:classmethod:: pickled (obj, \**kwargs)

        Construct a pickled message, setting :py:attr:`data` to the
        serialization of `obj`, and setting remaining fields using `kwargs`.

        :returns:
            The new message.

    .. method:: unpickle (throw=True)

        Unpickle :py:attr:`data`, optionally raising any exceptions present.

        :param bool throw:
            If :py:data:`True`, raise exceptions, otherwise it is the caller's
            responsibility.

        :raises mitogen.core.CallError:
            The serialized data contained CallError exception.
        :raises mitogen.core.ChannelError:
            The serialized data contained :py:data:`mitogen.core._DEAD`.

    .. method:: reply (obj, \**kwargs)

        Compose a pickled reply to this message and send it using
        :py:attr:`router`.

        :param obj:
            Object to serialize.
        :param kwargs:
            Optional keyword parameters overriding message fields in the reply.



Router Class
============


.. currentmodule:: mitogen.core

.. class:: Router

    Route messages between parent and child contexts, and invoke handlers
    defined on our parent context. :py:meth:`Router.route() <route>` straddles
    the :py:class:`Broker <mitogen.core.Broker>` and user threads, it is safe
    to call anywhere.

    **Note:** This is the somewhat limited core version of the Router class
    used by child contexts. The master subclass is documented below this one.

    .. method:: stream_by_id (dst_id)

        Return the :py:class:`mitogen.core.Stream` that should be used to
        communicate with `dst_id`. If a specific route for `dst_id` is not
        known, a reference to the parent context's stream is returned.

    .. method:: add_route (target_id, via_id)

        Arrange for messages whose `dst_id` is `target_id` to be forwarded on
        the directly connected stream for `via_id`. This method is called
        automatically in response to ``ADD_ROUTE`` messages, but remains public
        for now while the design has not yet settled, and situations may arise
        where routing is not fully automatic.

    .. method:: register (context, stream)

        Register a new context and its associated stream, and add the stream's
        receive side to the I/O multiplexer. This This method remains public
        for now while hte design has not yet settled.

    .. method:: add_handler (fn, handle=None, persist=True, respondent=None)

        Invoke `fn(msg)` for each Message sent to `handle` from this context.
        Unregister after one invocation if `persist` is ``False``. If `handle`
        is ``None``, a new handle is allocated and returned.

        :param int handle:
            If not ``None``, an explicit handle to register, usually one of the
            ``mitogen.core.*`` constants. If unspecified, a new unused handle
            will be allocated.

        :param bool persist:
            If ``False``, the handler will be unregistered after a single
            message has been received.

        :param mitogen.core.Context respondent:
            Context that messages to this handle are expected to be sent from.
            If specified, arranges for :py:data:`_DEAD` to be delivered to `fn`
            when disconnection of the context is detected.

            In future `respondent` will likely also be used to prevent other
            contexts from sending messages to the handle.

        :return:
            `handle`, or if `handle` was ``None``, the newly allocated handle.

    .. method:: _async_route(msg, stream=None)

        Arrange for `msg` to be forwarded towards its destination. If its
        destination is the local context, then arrange for it to be dispatched
        using the local handlers.

        This is a lower overhead version of :py:meth:`route` that may only be
        called from the I/O multiplexer thread.

        :param mitogen.core.Stream stream:
            If not ``None``, a reference to the stream the message arrived on.
            Used for performing source route verification, to ensure sensitive
            messages such as ``CALL_FUNCTION`` arrive only from trusted
            contexts.

    .. method:: route(msg)

        Arrange for the :py:class:`Message` `msg` to be delivered to its
        destination using any relevant downstream context, or if none is found,
        by forwarding the message upstream towards the master context. If `msg`
        is destined for the local context, it is dispatched using the handles
        registered with :py:meth:`add_handler`.

        This may be called from any thread.


.. currentmodule:: mitogen.master

.. class:: Router (broker=None)

    Extend :py:class:`mitogen.core.Router` with functionality useful to
    masters, and child contexts who later become masters. Currently when this
    class is required, the target context's router is upgraded at runtime.

    .. note::

        You may construct as many routers as desired, and use the same broker
        for multiple routers, however usually only one broker and router need
        exist. Multiple routers may be useful when dealing with separate trust
        domains, for example, manipulating infrastructure belonging to separate
        customers or projects.

    :param mitogen.master.Broker broker:
        :py:class:`Broker` instance to use. If not specified, a private
        :py:class:`Broker` is created.

    .. data:: profiling

        When enabled, causes the broker thread and any subsequent broker and
        main threads existing in any child to write
        ``/tmp/mitogen.stats.<pid>.<thread_name>.log`` containing a
        :py:mod:`cProfile` dump on graceful exit. Must be set prior to any
        :py:class:`Broker` being constructed, e.g. via:

        .. code::

             mitogen.master.Router.profiling = True

    .. method:: enable_debug

        Cause this context and any descendant child contexts to write debug
        logs to /tmp/mitogen.<pid>.log.

    .. method:: allocate_id

        Arrange for a unique context ID to be allocated and associated with a
        route leading to the active context. In masters, the ID is generated
        directly, in children it is forwarded to the master via an
        ``ALLOCATE_ID`` message that causes the master to emit matching
        ``ADD_ROUTE`` messages prior to replying.

    .. method:: context_by_id (context_id, via_id=None)

        Messy factory/lookup function to find a context by its ID, or construct
        it. In future this will be replaced by a much more sensible interface.

    .. _context-factories:

    **Context Factories**

    .. method:: fork (new_stack=False, on_fork=None, debug=False, profiling=False, via=None)

        Construct a context on the local machine by forking the current
        process. The forked child receives a new identity, sets up a new broker
        and router, and responds to function calls identically to children
        created using other methods.

        For long-lived processes, :py:meth:`local` is always better as it
        guarantees a pristine interpreter state that inherited little from the
        parent. Forking should only be used in performance-sensitive scenarios
        where short-lived children must be spawned to isolate potentially buggy
        code, and only after accounting for all the bad things possible as a
        result of, at a minimum:

        * Files open in the parent remaining open in the child,
          causing the lifetime of the underlying object to be extended
          indefinitely.

          * From the perspective of external components, this is observable
            in the form of pipes and sockets that are never closed, which may
            break anything relying on closure to signal protocol termination.

          * Descriptors that reference temporary files will not have their disk
            space reclaimed until the child exits.

        * Third party package state, such as urllib3's HTTP connection pool,
          attempting to write to file descriptors shared with the parent,
          causing random failures in both parent and child.

        * UNIX signal handlers installed in the parent process remaining active
          in the child, despite associated resources, such as service threads,
          child processes, resource usage counters or process timers becoming
          absent or reset in the child.

        * Library code that makes assumptions about the process ID remaining
          unchanged, for example to implement inter-process locking, or to
          generate file names.

        * Anonymous ``MAP_PRIVATE`` memory mappings whose storage requirement
          doubles as either parent or child dirties their pages.

        * File-backed memory mappings that cannot have their space freed on
          disk due to the mapping living on in the child.

        * Difficult to diagnose memory usage and latency spikes due to object
          graphs becoming unreferenced in either parent or child, causing
          immediate copy-on-write to large portions of the process heap.

        * Locks held in the parent causing random deadlocks in the child, such
          as when another thread emits a log entry via the :py:mod:`logging`
          package concurrent to another thread calling :py:meth:`fork`.

        * Objects existing in Thread-Local Storage of every non-:py:meth:`fork`
          thread becoming permanently inaccessible, and never having their
          object destructors called, including TLS usage by native extension
          code, triggering many new variants of all the issues above.

        * Pseudo-Random Number Generator state that is easily observable by
          network peers to be duplicate, violating requirements of
          cryptographic protocols through one-time state reuse. In the worst
          case, children continually reuse the same state due to repeatedly
          forking from a static parent.

        :py:meth:`fork` cleans up Mitogen-internal objects, in addition to
        locks held by the :py:mod:`logging` package, reseeds
        :py:func:`random.random`, and the OpenSSL PRNG via
        :py:func:`ssl.RAND_add`, but only if the :py:mod:`ssl` module is
        already loaded. You must arrange for your program's state, including
        any third party packages in use, to be cleaned up by specifying an
        `on_fork` function.

        The associated stream implementation is
        :py:class:`mitogen.fork.Stream`.

        :param bool new_stack:
            If :py:data:`True`, arrange for the local thread stack to be
            discarded, by forking from a new thread. Aside from clean
            tracebacks, this has the effect of causing objects referenced by
            the stack to cease existing in the child.

        :param function on_fork:
            Function invoked as `on_fork()` from within the child process. This
            permits supplying a program-specific cleanup function to break
            locks and close file descriptors belonging to the parent from
            within the child.

        :param Context via:
            Same as the `via` parameter for :py:meth:`local`.

        :param bool debug:
            Same as the `debug` parameter for :py:meth:`local`.

        :param bool profiling:
            Same as the `profiling` parameter for :py:meth:`local`.

    .. method:: local (remote_name=None, python_path=None, debug=False, connect_timeout=None, profiling=False, via=None)

        Construct a context on the local machine as a subprocess of the current
        process. The associated stream implementation is
        :py:class:`mitogen.master.Stream`.

        :param str remote_name:
            The ``argv[0]`` suffix for the new process. If `remote_name` is
            ``test``, the new process ``argv[0]`` will be ``mitogen:test``.

            If unspecified, defaults to ``<username>@<hostname>:<pid>``.

            This variable cannot contain slash characters, as the resulting
            ``argv[0]`` must be presented in such a way as to allow Python to
            determine its installation prefix. This is required to support
            virtualenv.

        :param str python_path:
            Path to the Python interpreter to use for bootstrap. Defaults to
            ``python2.7``. In future this may default to ``sys.executable``.

        :param bool debug:
            If ``True``, arrange for debug logging (:py:meth:`enable_debug`) to
            be enabled in the new context. Automatically ``True`` when
            :py:meth:`enable_debug` has been called, but may be used
            selectively otherwise.

        :param float connect_timeout:
            Fractional seconds to wait for the subprocess to indicate it is
            healthy. Defaults to 30 seconds.

        :param bool profiling:
            If ``True``, arrange for profiling (:py:data:`profiling`) to be
            enabled in the new context. Automatically ``True`` when
            :py:data:`profiling` is ``True``, but may be used selectively
            otherwise.

        :param mitogen.core.Context via:
            If not ``None``, arrange for construction to occur via RPCs made to
            the context `via`, and for :py:data:`ADD_ROUTE
            <mitogen.core.ADD_ROUTE>` messages to be generated as appropriate.

            .. code-block:: python

                # SSH to the remote machine.
                remote_machine = router.ssh(hostname='mybox.com')

                # Use the SSH connection to create a sudo connection.
                remote_root = router.sudo(username='root', via=remote_machine)

    .. method:: docker (container=None, image=None, docker_path=None, \**kwargs)

        Construct a context on the local machine within an existing or
        temporary new Docker container. One of `container` or `image` must be
        specified.

        Accepts all parameters accepted by :py:meth:`local`, in addition to:

        :param str container:
            Existing container to connect to. Defaults to ``None``.
        :param str image:
            Image tag to use to construct a temporary container. Defaults to
            ``None``.
        :param str docker_path:
            Filename or complete path to the Docker binary. ``PATH`` will be
            searched if given as a filename. Defaults to ``docker``.

    .. method:: sudo (username=None, sudo_path=None, password=None, \**kwargs)

        Construct a context on the local machine over a ``sudo`` invocation.
        The ``sudo`` process is started in a newly allocated pseudo-terminal,
        and supports typing interactive passwords.

        Accepts all parameters accepted by :py:meth:`local`, in addition to:

        :param str username:
            Username to pass to sudo as the ``-u`` parameter, defaults to
            ``root``.
        :param str sudo_path:
            Filename or complete path to the sudo binary. ``PATH`` will be
            searched if given as a filename. Defaults to ``sudo``.
        :param str password:
            The password to use if/when sudo requests it. Depending on the sudo
            configuration, this is either the current account password or the
            target account password. :py:class:`mitogen.sudo.PasswordError`
            will be raised if sudo requests a password but none is provided.
        :param bool set_home:
            If :py:data:`True`, request ``sudo`` set the ``HOME`` environment
            variable to match the target UNIX account.
        :param bool preserve_env:
            If :py:data:`True`, request ``sudo`` to preserve the environment of
            the parent process.
        :param list sudo_args:
            Arguments in the style of :py:data:`sys.argv` that would normally
            be passed to ``sudo``. The arguments are parsed in-process to set
            equivalent parameters. Re-parsing ensures unsupported options cause
            :py:class:`mitogen.core.StreamError` to be raised, and that
            attributes of the stream match the actual behaviour of ``sudo``.

    .. method:: ssh (hostname, username=None, ssh_path=None, port=None, check_host_keys=True, password=None, identity_file=None, compression=True, \**kwargs)

        Construct a remote context over a ``ssh`` invocation. The ``ssh``
        process is started in a newly allocated pseudo-terminal, and supports
        typing interactive passwords.

        Accepts all parameters accepted by :py:meth:`local`, in addition to:

        :param str username:
            The SSH username; default is unspecified, which causes SSH to pick
            the username to use.
        :param str ssh_path:
            Absolute or relative path to ``ssh``. Defaults to ``ssh``.
        :param int port:
            Port number to connect to; default is unspecified, which causes SSH
            to pick the port number.
        :param bool check_host_keys:
            If ``False``, arrange for SSH to perform no verification of host
            keys. If ``True``, cause SSH to pick the default behaviour, which
            is usually to verify host keys.
        :param str password:
            Password to type if/when ``ssh`` requests it. If not specified and
            a password is requested, :py:class:`mitogen.ssh.PasswordError` is
            raised.
        :param str identity_file:
            Path to an SSH private key file to use for authentication. Default
            is unspecified, which causes SSH to pick the identity file.

            When this option is specified, only `identity_file` will be used by
            the SSH client to perform authenticaion; agent authentication is
            automatically disabled, as is reading the default private key from
            ``~/.ssh/id_rsa``, or ``~/.ssh/id_dsa``.
        :param bool compression:
            If :py:data:`True`, enable ``ssh`` compression support. Compression
            has a minimal effect on the size of modules transmitted, as they
            are already compressed, however it has a large effect on every
            remaining message in the otherwise uncompressed stream protocol,
            such as function call arguments and return values.


Context Class
=============

.. currentmodule:: mitogen.core

.. class:: Context

    Represent a remote context regardless of connection method.

    **Note:** This is the somewhat limited core version of the Context class
    used by child contexts. The master subclass is documented below this one.

    .. method:: send (msg)

        Arrange for `msg` to be delivered to this context. Updates the
        message's `dst_id` prior to routing it via the associated router.

        :param mitogen.core.Message msg:
            The message.

    .. method:: send_async (msg, persist=False)

        Arrange for `msg` to be delivered to this context, with replies
        delivered to a newly constructed Receiver. Updates the message's
        `dst_id` prior to routing it via the associated router and registers a
        handle which is placed in the message's `reply_to`.

        :param bool persist:
            If ``False``, the handler will be unregistered after a single
            message has been received.

        :param mitogen.core.Message msg:
            The message.

        :returns:
            :py:class:`mitogen.core.Receiver` configured to receive any replies
            sent to the message's `reply_to` handle.

    .. method:: send_await (msg, deadline=None)

        As with :py:meth:`send_async`, but expect a single reply
        (`persist=False`) delivered within `deadline` seconds.

        :param mitogen.core.Message msg:
            The message.

        :param float deadline:
            If not ``None``, seconds before timing out waiting for a reply.

        :raises mitogen.core.TimeoutError:
            No message was received and `deadline` passed.


.. currentmodule:: mitogen.parent

.. class:: Context

    Extend :py:class:`mitogen.core.Router` with functionality useful to
    masters, and child contexts who later become parents. Currently when this
    class is required, the target context's router is upgraded at runtime.

    .. method:: shutdown (wait=False)

        Arrange for the context to receive a ``SHUTDOWN`` message, triggering
        graceful shutdown.

        Due to a lack of support for timers, no attempt is made yet to force
        terminate a hung context using this method. This will be fixed shortly.

        :param bool wait:
            If :py:data:`True`, block the calling thread until the context has
            completely terminated.

    .. method:: call_async (fn, \*args, \*\*kwargs)

        Arrange for the context's ``CALL_FUNCTION`` handle to receive a
        message that causes `fn(\*args, \**kwargs)` to be invoked on the
        context's main thread.

        :param fn:
            A free function in module scope, or a classmethod or staticmethod
            of a class directly reachable from module scope:

            .. code-block:: python

                # mymodule.py

                def my_func():
                    """A free function reachable as mymodule.my_func"""

                class MyClass:
                    @staticmethod
                    def my_staticmethod():
                        """Reachable as mymodule.MyClass.my_staticmethod"""

                    @classmethod
                    def my_classmethod(cls):
                        """Reachable as mymodule.MyClass.my_classmethod"""

                    def my_instancemethod(self):
                        """Unreachable: requires a class instance!"""

                    class MyEmbeddedClass:
                        @classmethod
                        def my_classmethod(cls):
                            """Not directly reachable from module scope!"""

        :param tuple args:
            Function arguments, if any. See :ref:`serialization-rules` for
            permitted types.
        :param dict kwargs:
            Function keyword arguments, if any. See :ref:`serialization-rules`
            for permitted types.
        :returns:
            :py:class:`mitogen.core.Receiver` configured to receive the result
            of the invocation:

            .. code-block:: python

                recv = context.call_async(os.check_output, 'ls /tmp/')
                try:
                    # Prints output once it is received.
                    msg = recv.get()
                    print msg.unpickle()
                except mitogen.core.CallError, e:
                    print 'Call failed:', str(e)

            Asynchronous calls may be dispatched in parallel to multiple
            contexts and consumed as they complete using
            :py:class:`mitogen.master.Select`.

    .. method:: call (fn, \*args, \*\*kwargs)

        Equivalent to :py:meth:`call_async(fn, \*args, \**kwargs).get_data()
        <call_async>`.

        :returns:
            The function's return value.

        :raises mitogen.core.CallError:
            An exception was raised in the remote context during execution.



Receiver Class
--------------

.. currentmodule:: mitogen.core

.. class:: Receiver (router, handle=None, persist=True, respondent=None)

    Receivers are used to wait for pickled responses from another context to be
    sent to a handle registered in this context. A receiver may be single-use
    (as in the case of :py:meth:`mitogen.parent.Context.call_async`) or
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
        ``None``, arranges for the receiver to receive :py:data:`_DEAD` if
        messages can no longer be routed to the context, due to disconnection
        or exit.

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
            # notification function was invoked at least once.

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

.. currentmodule:: mitogen.core

.. class:: Sender (context, dst_handle)

    Senders are used to send pickled messages to a handle in another context,
    it is the inverse of :py:class:`mitogen.core.Sender`.

    :param mitogen.core.Context context:
        Context to send messages to.
    :param int dst_handle:
        Destination handle to send messages to.

    .. py:method:: close ()

        Send :py:data:`_DEAD` to the remote end, causing
        :py:meth:`ChannelError` to be raised in any waiting thread.

    .. py:method:: put (data)

        Send `data` to the remote end.


Channel Class
-------------

.. currentmodule:: mitogen.core

.. class:: Channel (router, context, dst_handle, handle=None)

    A channel inherits from :py:class:`mitogen.core.Sender` and
    `mitogen.core.Receiver` to provide bidirectional functionality.

    Since all handles aren't known until after both ends are constructed, for
    both ends to communicate through a channel, it is necessary for one end to
    retrieve the handle allocated to the other and reconfigure its own channel
    to match. Currently this is a manual task.


Broker Class
============

.. currentmodule:: mitogen.core
.. class:: Broker

    Responsible for handling I/O multiplexing in a private thread.

    **Note:** This is the somewhat limited core version of the Broker class
    used by child contexts. The master subclass is documented below this one.

    .. attribute:: shutdown_timeout = 3.0

        Seconds grace to allow :py:class:`streams <Stream>` to shutdown
        gracefully before force-disconnecting them during :py:meth:`shutdown`.

    .. method:: defer (func, \*args, \*kwargs)

        Arrange for `func(\*args, \**kwargs)` to be executed on the broker
        thread, or immediately if the current thread is the broker thread. Safe
        to call from any thread.

    .. method:: start_receive (stream)

        Mark the :py:attr:`receive_side <Stream.receive_side>` on `stream` as
        ready for reading. Safe to call from any thread. When the associated
        file descriptor becomes ready for reading,
        :py:meth:`BasicStream.on_receive` will be called.

    .. method:: stop_receive (stream)

        Mark the :py:attr:`receive_side <Stream.receive_side>` on `stream` as
        not ready for reading. Safe to call from any thread.

    .. method:: _start_transmit (stream)

        Mark the :py:attr:`transmit_side <Stream.transmit_side>` on `stream` as
        ready for writing. Must only be called from the Broker thread. When the
        associated file descriptor becomes ready for writing,
        :py:meth:`BasicStream.on_transmit` will be called.

    .. method:: stop_receive (stream)

        Mark the :py:attr:`transmit_side <Stream.receive_side>` on `stream` as
        not ready for writing. Safe to call from any thread.

    .. method:: shutdown

        Request broker gracefully disconnect streams and stop.

    .. method:: join

        Wait for the broker to stop, expected to be called after
        :py:meth:`shutdown`.

    .. method:: keep_alive

        Return ``True`` if any reader's :py:attr:`Side.keep_alive` attribute is
        ``True``, or any :py:class:`Context` is still registered that is not
        the master. Used to delay shutdown while some important work is in
        progress (e.g. log draining).

    **Internal Methods**

    .. method:: _broker_main

        Handle events until :py:meth:`shutdown`. On shutdown, invoke
        :py:meth:`Stream.on_shutdown` for every active stream, then allow up to
        :py:attr:`shutdown_timeout` seconds for the streams to unregister
        themselves before forcefully calling
        :py:meth:`Stream.on_disconnect`.


.. currentmodule:: mitogen.master
.. class:: Broker (install_watcher=True)

    .. note::

        You may construct as many brokers as desired, and use the same broker
        for multiple routers, however usually only one broker need exist.
        Multiple brokers may be useful when dealing with sets of children with
        differing lifetimes. For example, a subscription service where
        non-payment results in termination for one customer.

    :param bool install_watcher:
        If ``True``, an additional thread is started to monitor the lifetime of
        the main thread, triggering :py:meth:`shutdown` automatically in case
        the user forgets to call it, or their code crashed.

        You should not rely on this functionality in your program, it is only
        intended as a fail-safe and to simplify the API for new users. In
        particular, alternative Python implementations may not be able to
        support watching the main thread.

    .. attribute:: shutdown_timeout = 5.0

        Seconds grace to allow :py:class:`streams <Stream>` to shutdown
        gracefully before force-disconnecting them during :py:meth:`shutdown`.


Utility Functions
=================

.. module:: mitogen.utils

A random assortment of utility functions useful on masters and children.

.. currentmodule:: mitogen.utils
.. function:: cast (obj)

    Many tools love to subclass built-in types in order to implement useful
    functionality, such as annotating the safety of a Unicode string, or adding
    additional methods to a dict. However, cPickle loves to preserve those
    subtypes during serialization, resulting in CallError during :py:meth:`call
    <mitogen.parent.Context.call>` in the target when it tries to deserialize
    the data.

    This function walks the object graph `obj`, producing a copy with any
    custom sub-types removed. The functionality is not default since the
    resulting walk may be computationally expensive given a large enough graph.

    See :ref:`serialization-rules` for a list of supported types.

    :param obj:
        Object to undecorate.
    :returns:
        Undecorated object.

.. currentmodule:: mitogen.utils
.. function:: disable_site_packages

    Remove all entries mentioning ``site-packages`` or ``Extras`` from the
    system path. Used primarily for testing on OS X within a virtualenv, where
    OS X bundles some ancient version of the :py:mod:`six` module.

.. currentmodule:: mitogen.utils
.. function:: log_to_file (path=None, io=False, usec=False, level='INFO')

    Install a new :py:class:`logging.Handler` writing applications logs to the
    filesystem. Useful when debugging slave IO problems.

    Parameters to this function may be overridden at runtime using environment
    variables. See :ref:`logging-env-vars`.

    :param str path:
        If not ``None``, a filesystem path to write logs to. Otherwise, logs
        are written to :py:data:`sys.stderr`.

    :param bool io:
        If ``True``, include extremely verbose IO logs in the output. Useful
        for debugging hangs, less useful for debugging application code.

    :parm bool usec:
        If ``True``, include microsecond timestamps. This greatly helps when
        debugging races and similar determinism issues.

    :param str level:
        Name of the :py:mod:`logging` package constant that is the minimum
        level to log at. Useful levels are ``DEBUG``, ``INFO``, ``WARNING``,
        and ``ERROR``.

.. currentmodule:: mitogen.utils
.. function:: run_with_router(func, \*args, \**kwargs)

    Arrange for `func(router, \*args, \**kwargs)` to run with a temporary
    :py:class:`mitogen.master.Router`, ensuring the Router and Broker are
    correctly shut down during normal or exceptional return.

    :returns:
        `func`'s return value.

.. currentmodule:: mitogen.utils
.. decorator:: with_router

    Decorator version of :py:func:`run_with_router`. Example:

    .. code-block:: python

        @with_router
        def do_stuff(router, arg):
            pass

        do_stuff(blah, 123)


Exceptions
==========

.. currentmodule:: mitogen.core

.. class:: Error (fmt, \*args)

    Base for all exceptions raised by Mitogen.

.. class:: CallError (e)

    Raised when :py:meth:`Context.call() <mitogen.parent.Context.call>` fails.
    A copy of the traceback from the external context is appended to the
    exception message.

.. class:: ChannelError (fmt, \*args)

    Raised when a channel dies or has been closed.

.. class:: LatchError (fmt, \*args)

    Raised when an attempt is made to use a :py:class:`mitogen.core.Latch` that
    has been marked closed.

.. class:: StreamError (fmt, \*args)

    Raised when a stream cannot be established.

.. class:: TimeoutError (fmt, \*args)

    Raised when a timeout occurs on a stream.
