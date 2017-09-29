
How Mitogen Works
=================

Some effort is required to accomplish the seemingly magical feat of
bootstrapping a remote Python process without any software installed on the
remote machine. The steps involved are unlikely to be immediately obvious to
the casual reader, and they required several iterations to discover, so we
document them thoroughly below.


The UNIX First Stage
--------------------

To allow delivery of the bootstrap compressed using :py:mod:`zlib`, it is
necessary for something on the remote to be prepared to decompress the payload
and feed it to a Python interpreter. Since we would like to avoid writing an
error-prone shell fragment to implement this, and since we must avoid writing
to the remote machine's disk in case it is read-only, the Python process
started on the remote machine by Mitogen immediately forks in order to
implement the decompression.


Python Command Line
###################

The Python command line sent to the host is a base64-encoded copy of the
:py:meth:`mitogen.master.Stream._first_stage` function, which has been
carefully optimized to reduce its size. Prior to base64 encoding,
``CONTEXT_NAME`` is replaced with the desired context name in the function's
source code.

.. code::

    python -c 'exec "xxx".decode("base64")'

The command-line arranges for the Python interpreter to decode the base64'd
component and execute it as Python code. Base64 is used since the first stage
implementation contains newlines, and many special characters that may be
interpreted by the system shell in use.


Forking The First Stage
#######################

The first stage creates a UNIX pipe and saves a copy of the process's real
``stdin`` file descriptor (used for communication with the master) so that it
can be recovered by the bootstrapped process later. It then forks into a new
process.

After fork, the parent half overwrites its ``stdin`` with the read end of the
pipe, and the child half writes the string ``EC0\n``, then begins reading the
:py:mod:`zlib`-compressed payload supplied on ``stdin`` by the master, and
writing the decompressed result to the write-end of the UNIX pipe.

To allow recovery of ``stdin`` for reuse by the bootstrapped process for
parent<->child communication, it is necessary for the first stage to avoid
closing ``stdin`` or reading from it until until EOF. Therefore, the master
sends the :py:mod:`zlib`-compressed payload prefixed with an integer size,
allowing reading by the first stage of exactly the required bytes.


Configuring argv[0]
###################

Forking provides us with an excellent opportunity for tidying up the eventual
Python interpreter, in particular, restarting it using a fresh command-line to
get rid of the large base64-encoded first stage parameter, and to replace
**argv[0]** with something descriptive.

After configuring its ``stdin`` to point to the read end of the pipe, the
parent half of the fork re-executes Python, with **argv[0]** taken from the
``CONTEXT_NAME`` variable earlier substituted into its source code. As no
arguments are provided to this new execution of Python, and since ``stdin`` is
connected to a pipe (whose write end is connected to the first stage), the
Python interpreter begins reading source code to execute from the pipe
connected to ``stdin``.


Bootstrap Preparation
#####################

Now we have the mechanism in place to send a :py:mod:`zlib`-compressed script
to the remote Python interpreter, it is time to choose what to send.

The script sent is simply the source code for :py:mod:`mitogen.core`, with a
single line suffixed to trigger execution of the
:py:meth:`mitogen.core.ExternalContext.main` function. The encoded arguments
to the main function include some additional details, such as the logging package
level that was active in the parent process, and whether debugging or profiling
are enabled.

After the script source code is prepared, it is passed through
:py:func:`mitogen.master.minimize_source` to strip it of docstrings and
comments, while preserving line numbers. This reduces the compressed payload
by around 20%.


Preserving The `mitogen.core` Source
####################################

One final trick is implemented in the first stage: after bootstrapping the new
child, it writes a duplicate copy of the :py:mod:`mitogen.core` source it just
used to bootstrap it back into another pipe connected to the child. The child's
module importer cache is initialized with a copy of the source, so that
subsequent bootstraps of children-of-children do not require the source to be
fetched from the master a second time.


Signalling Success
##################

Once the first stage has signalled ``EC0\n``, the master knows it is ready to
receive the compressed bootstrap. After decompressing and writing the bootstrap
source to its parent Python interpreter, the first stage writes the string
``EC1\n`` to ``stdout`` before exiting. The master process waits for this
string before considering bootstrap successful and the child's ``stdio`` ready
to receive messages.


ExternalContext.main()
----------------------

.. automethod:: mitogen.core.ExternalContext.main


Generating A Synthetic `mitogen` Package
########################################

Since the bootstrap consists of the :py:mod:`mitogen.core` source code, and
this code is loaded by Python by way of its main script (``__main__`` module),
initially the module layout in the child will be incorrect.

The first step taken after bootstrap is to rearrange :py:data:`sys.modules` slightly
so that :py:mod:`mitogen.core` appears in the correct location, and all
classes defined in that module have their ``__module__`` attribute fixed up
such that :py:mod:`cPickle` correctly serializes instance module names.

Once a synthetic :py:mod:`mitogen` package and :py:mod:`mitogen.core` module
have been generated, the bootstrap **deletes** `sys.modules['__main__']`, so
that any attempt to import it (by :py:mod:`cPickle`) will cause the import to
be satisfied by fetching the master's actual ``__main__`` module. This is
necessary to allow master programs to be written as a self-contained Python
script.


Reaping The First Stage
#######################

After the bootstrap has called :py:func:`os.dup` on the copy of the ``stdin``
file descriptor saved by the first stage, it is closed.

Additionally, since the first stage was forked prior to re-executing the Python
interpreter, it will exist as a zombie process until the parent process reaps
it. Therefore the bootstrap must call :py:func:`os.wait` soon after startup.


Setup Logging
#############

The child's :py:mod:`logging` package root logger is configured to have the
same log level as the root logger in the master, and
:py:class:`mitogen.core.LogHandler` is installed to forward logs to the master
context's :py:data:`FORWARD_LOG <mitogen.core.FORWARD_LOG>` handle.

The log level is copied into the child to avoid generating a potentially large
amount of network IO forwarding logs that will simply be filtered away once
they reach the master.


The Module Importer
###################

An instance of :py:class:`mitogen.core.Importer` is installed in
:py:data:`sys.meta_path`, where Python's ``import`` statement will execute it
before attempting to find a module locally.


Standard IO Redirection
#######################

Two instances of :py:class:`mitogen.core.IoLogger` are created, one for
``stdout`` and one for ``stderr``. This class creates a UNIX pipe whose read
end is added to the IO multiplexer, and whose write end is used to overwrite
the handles inherited during process creation.

Even without IO redirection, something must replace ``stdin`` and ``stdout``,
otherwise it is possible for the stream used for communication between parent
and child to be accidentally corrupted by subprocesses run by user code.

The inherited ``stdin`` is replaced by a file descriptor pointing to
``/dev/null``.

Finally Python's :py:data:`sys.stdout` is reopened to ensure line buffering is
active, so that ``print`` statements and suchlike promptly appear in the logs.


Function Call Dispatch
######################

After all initialization is complete, the child's main thread sits in a loop
reading from a :py:class:`Channel <mitogen.core.Channel>` connected to the
:py:data:`CALL_FUNCTION <mitogen.core.CALL_FUNCTION>` handle. This handle is
written to by
:py:meth:`call() <mitogen.master.Context.call>`
and :py:meth:`call_async() <mitogen.master.Context.call_async>`.


Shutdown
########

When the master signals the :py:data:`CALL_FUNCTION
<mitogen.core.CALL_FUNCTION>` :py:class:`Channel <mitogen.core.Channel>` is
closed, the child calls :py:meth:`shutdown() <mitogen.core.Broker.shutdown>`
followed by :py:meth:`wait() <mitogen.core.Broker.wait>` on its own broker,
triggering graceful shutdown.

During shutdown, the master will wait a few seconds for children to disconnect
gracefully before force disconnecting them, while the children will use that
time to call :py:meth:`socket.shutdown(SHUT_WR) <socket.socket.shutdown>` on
their :py:class:`IoLogger <mitogen.core.IoLogger>` socket's write ends before
draining any remaining data buffered on the read ends.

An alternative approach is to wait until the socket is completely closed, with
some hard timeout, but this necessitates greater discipline than is common in
infrastructure code (how often have you forgotten to redirect stderr to
``/dev/null``?), so needless irritating delays would often be experienced
during program termination.

If the main thread (responsible for function call dispatch) fails to trigger
shutdown (because some user function is hanging), then the eventual force
disconnection by the master will cause the IO multiplexer thread to enter
shutdown by itself.


.. _stream-protocol:

Stream Protocol
---------------

Once connected, a basic framing protocol is used to communicate between
parent and child:

+--------------------+------+------------------------------------------------------+
| Field              | Size | Description                                          |
+====================+======+======================================================+
| ``dst_id``         | 2    | Integer target context ID.                           |
+--------------------+------+------------------------------------------------------+
| ``src_id``         | 2    | Integer source context ID.                           |
+--------------------+------+------------------------------------------------------+
| ``handle``         | 4    | Integer target handle in recipient.                  |
+--------------------+------+------------------------------------------------------+
| ``reply_to``       | 4    | Integer response target ID.                          |
+--------------------+------+------------------------------------------------------+
| ``length``         | 4    | Message length                                       |
+--------------------+------+------------------------------------------------------+
| ``data``           | n/a  | Pickled message data.                                |
+--------------------+------+------------------------------------------------------+

Masters listen on the following handles:

.. data:: mitogen.core.FORWARD_LOG

    Receives `(logger_name, level, msg)` 3-tuples and writes them to the
    master's ``mitogen.ctx.<context_name>`` logger.

.. data:: mitogen.core.GET_MODULE

    Receives `(reply_to, fullname)` 2-tuples, looks up the source code for the
    module named ``fullname``, and writes the source along with some metadata
    back to the handle ``reply_to``. If lookup fails, ``None`` is sent instead.

.. data:: mitogen.core.ALLOCATE_ID

    Replies to any message sent to it with a newly allocated unique context ID,
    to allow children to safely start their own contexts. In future this is
    likely to be replaced by 32-bit context IDs and pseudorandom allocation,
    with an improved ``ADD_ROUTE`` message sent upstream rather than downstream
    that generates NACKs if any ancestor detects an ID collision.


Children listen on the following handles:

.. data:: mitogen.core.CALL_FUNCTION

    Receives `(mod_name, class_name, func_name, args, kwargs)`
    5-tuples from
    :py:meth:`call_async() <mitogen.master.Context.call_async>`,
    imports ``mod_name``, then attempts to execute
    `class_name.func_name(\*args, \**kwargs)`.

    When this channel is closed (by way of sending ``_DEAD`` to it), the
    child's main thread begins graceful shutdown of its own `Broker` and
    `Router`. Each child is responsible for sending ``_DEAD`` to each of its
    directly connected children in response to the master sending ``_DEAD`` to
    it, and arranging for the connection to its parent context to be closed
    shortly thereafter.

.. data:: mitogen.core.ADD_ROUTE

    Receives `(target_id, via_id)` integer tuples, describing how messages
    arriving at this context on any Stream should be forwarded on the stream
    associated with the Context `via_id` such that they are eventually
    delivered to the target Context.

    This message is necessary to inform intermediary contexts of the existence
    of a downstream Context, as they do not otherwise parse traffic they are
    fowarding to their downstream contexts that may cause new contexts to be
    established.

    Given a chain `master -> ssh1 -> sudo1`, no `ADD_ROUTE` message is
    necessary, since :py:class:`mitogen.core.Router` in the `ssh` context can
    arrange to update its routes while setting up the new child during
    `proxy_connect()`.

    However, given a chain like `master -> ssh1 -> sudo1 -> ssh2 -> sudo2`,
    `ssh1` requires an `ADD_ROUTE` for `ssh2`, and both `ssh1` and `sudo1`
    require an `ADD_ROUTE` for `sudo2`, as neither directly dealt with its
    establishment.


Children that have ever been used to create a descendent child also listen on
the following handles:

.. data:: mitogen.core.GET_MODULE

    As with master's ``GET_MODULE``, except this implementation
    (:py:class:`mitogen.master.ModuleForwarder`) serves responses using
    :py:class:`mitogen.core.Importer`'s cache before forwarding the request to
    its parent context. The response is cached by each context in turn before
    being forwarded on to the child context that originally made the request.
    In this way, the master need never re-send a module it has already sent to
    a direct descendant.


Additional handles are created to receive the result of every function call
triggered by :py:meth:`call_async() <mitogen.master.Context.call_async>`.


Sentinel Value
##############

.. autodata:: mitogen.core._DEAD

The special value :py:data:`mitogen.core._DEAD` is used to signal
disconnection or closure of the remote end. It is used internally by
:py:class:`Channel <mitogen.core.Channel>` and also passed to any function
still registered with :py:meth:`add_handler()
<mitogen.core.Router.add_handler>` during Broker shutdown.


Use of Pickle
#############

The current implementation uses the Python :py:mod:`cPickle` module, with a
restrictive class whitelist to prevent triggering undesirable code execution.
The primary reason for using :py:mod:`cPickle` is that it is computationally
efficient, and avoids including a potentially large body of serialization code
in the bootstrap.

The pickler will instantiate only built-in types and one of 3 constructor
functions, to support unpickling :py:class:`CallError
<mitogen.core.CallError>`, :py:data:`_DEAD <mitogen.core._DEAD>`, and
:py:class:`Context <mitogen.core.Context>`.

The choice of Pickle is one area to be revisited later. All accounts suggest it
cannot be used securely, however few of those accounts appear to be expert, and
none mention any additional attacks that would not be prevented by using a
restrictive class whitelist.


The IO Multiplexer
------------------

Since we must include our IO multiplexer as part of the bootstrap,
off-the-shelf implementations are for the most part entirely inappropriate. For
example, a minimal copy of Twisted weighs in at around 440KiB and is composed
of approximately 115 files. Even if we could arrange for an entire Python
package to be transferred during bootstrap, this minimal configuration is
massive in comparison to Mitogen's solution, multiplies quickly in the
presence of many machines, and would require manually splitting up the parts of
Twisted that we would like to use.


Message Routing
---------------

Routing assumes it is impossible to construct a tree such that one of a
context's parents will not know the ID of a target the context is attempting to
communicate with.

When :py:class:`mitogen.core.Router` receives a message, it checks the IDs
associated with its directly connected streams for a potential route. If any
stream matches, either because it directly connects to the target ID, or
because the master sent an ``ADD_ROUTE`` message associating it, then the
message will be forwarded down the tree using that stream.

If the message does not match any ``ADD_ROUTE`` message or stream, instead it
is forwarded upwards to the immediate parent, and recursively by each parent in
turn until one is reached that knows how to forward the message down the tree.

When the master establishes a new context via an existing child context, it
sends corresponding ``ADD_ROUTE`` messages to each indirect parent between the
context and the root.


Example
#######

.. image:: images/context-tree.png

In the diagram, when ``master`` is creating the ``sudo:node12b:webapp``
context, it must send ``ADD_ROUTE`` messages to ``rack12``, ``dc1``,
``bastion``, and itself; ``node12b`` does not require an ``ADD_ROUTE`` message
since it has a stream directly connected to the new context.

When ``sudo:node22a:webapp`` wants to send a message to
``sudo:node12b:webapp``, the message will be routed as follows:

``sudo:node22a:webapp -> node22a -> rack22 -> dc2 -> bastion -> dc1 -> rack12 -> node12b -> sudo:node12b:webapp``

.. image:: images/route.png


Future
######

The current routing approach is incomplete, since routes to downstream contexts
are not propagated upwards when a descendant of the master context establishes
a new child context, but that is okay for now, since child contexts cannot
currently allocate new context IDs anyway.


Differences Between Master And Child Brokers
############################################

The main difference between :py:class:`mitogen.core.Broker` and
:py:class:`mitogen.master.Broker` is that when the stream connection to the
parent is lost in a child, the broker will trigger its own shutdown.


The Module Importer
-------------------

:py:class:`mitogen.core.Importer` is still a work in progress, as there
are a variety of approaches to implementing it, and the present implementation
is not pefectly efficient in every case.

It operates by intercepting ``import`` statements via `sys.meta_path`, asking
Python if it can satisfy the import by itself, and if not, indicating to Python
that it is capable of loading the module.

In :py:meth:`load_module() <mitogen.core.Importer.load_module>` an RPC is
started to the parent context, requesting the module source code. Once the
source is fetched, the method builds a new module object using the best
practice documented in PEP-302.


Avoiding Negative Imports
#########################

In Python 2.x where relative imports are the default, a large number of import
requests will be made for modules that do not exist. For example:

.. code-block:: python

    # mypkg/__init__.py

    import sys
    import os

In Python 2.x, Python will first try to load ``mypkg.sys`` and ``mypkg.os``,
which do not exist, before falling back on :py:mod:`sys` and :py:mod:`os`.

These negative imports present a challenge, as they introduce a large number of
pointless network roundtrips. Therefore in addition to the
:py:mod:`zlib`-compressed source, for packages the master sends along a list of
child modules known to exist.

Before indicating it can satisfy an import request,
:py:class:`mitogen.core.Importer` first checks to see if the module belongs to
a package it has previously imported, and if so, ignores the request if the
module does not appear in the enumeration of child modules belonging to the
package that was provided by the master.


Child Module Enumeration
########################

Package children are enumerated using :py:func:`pkgutil.iter_modules`.


Use Of Threads
--------------

The package always runs the IO multiplexer in a thread. This is so the
multiplexer retains control flow in order to shut down gracefully, say, if the
user's code has hung and the master context has disconnected.

While it is possible for the IO multiplexer to recover control of a hung
function call on UNIX using for example :py:mod:`signal.SIGALRM <signal>`, this
mechanism is not portable to non-UNIX operating systems, and does not work in
every case, for example when Python blocks signals during a variety of
:py:mod:`threading` package operations.

At some point it is likely Mitogen will be extended to support children running
on Windows. When that happens, it would be nice if the process model on Windows
and UNIX did not differ, and in fact the code used on both were identical.
