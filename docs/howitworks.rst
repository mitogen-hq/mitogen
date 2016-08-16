
How econtext Works
==================

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
started on the remote machine by ``econtext`` immediately forks in order to
implement the decompression.


Python Command Line
###################

The Python command line sent to the host is a base64-encoded copy of the
:py:meth:`econtext.master.LocalStream._first_stage` function, which has been
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
pipe, and the child half begins reading the :py:mod:`zlib`-compressed payload
supplied on ``stdin`` by the econtext master, and writing the decompressed
result to the write-end of the UNIX pipe.

To allow recovery of ``stdin`` for reuse by the bootstrapped process for
master<->slave communication, it is necessary for the first stage to avoid
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

The script sent is simply the source code for :py:mod:`econtext.core`, with a
single line suffixed to trigger execution of the
:py:meth:`econtext.core.ExternalContext.main` function. The encoded arguments
to the main function include some additional details, such as the logging package
level that was active in the parent process, and a random secret key used to
generate HMAC signatures over the data frames that will be exchanged after
bootstrap.

After the script source code is prepared, it is passed through
:py:func:`econtext.master.minimize_source` to strip it of docstrings and
comments, while preserving line numbers. This reduces the compressed payload
by around 20%.



Signalling Success
##################

Once the first stage has decompressed and written the bootstrap source code to
its parent Python interpreter, it writes the string ``OK\n`` to ``stdout``
before exitting. The master process waits for this string before considering
bootstrap successful and the child's ``stdio`` ready to receive messages.


ExternalContext.main()
----------------------

.. automethod:: econtext.core.ExternalContext.main


Generating A Synthetic `econtext` Package
#########################################

Since the bootstrap consists of the :py:mod:`econtext.core` source code, and
this code is loaded by Python by way of its main script (``__main__`` module),
initially the module layout in the slave will be incorrect.

The first step taken after bootstrap is to rearrange :py:data:`sys.modules` slightly
so that :py:mod:`econtext.core` appears in the correct location, and all
classes defined in that module have their ``__module__`` attribute fixed up
such that :py:mod:`cPickle` correctly serializes instance module names.

Once a synthetic :py:mod:`econtext` package and :py:mod:`econtext.core` module
have been generated, the bootstrap **deletes** `sys.modules['__main__']`, so
that any attempt to import it (by :py:mod:`cPickle`) will cause the import to
be satisfied by fetching the econtext master's actual ``__main__`` module. This
is necessary to allow master programs to be written as a self-contained Python
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

The slave's :py:mod:`logging` package root logger is configured to have the
same log level as the root logger in the master, and
:py:class:`econtext.core.LogHandler` is installed to forward logs to the master
context's :py:data:`FORWARD_LOG <econtext.core.FORWARD_LOG>` handle.

The log level is copied into the slave to avoid generating a potentially large
amount of network IO forwarding logs that will simply be filtered away once
they reach the master.


The Module Importer
###################

An instance of :py:class:`econtext.core.Importer` is installed in
:py:data:`sys.meta_path`, where Python's ``import`` statement will execute it
before attempting to find a module locally.


Standard IO Redirection
#######################

Two instances of :py:class:`econtext.core.IoLogger` are created, one for
``stdout`` and one for ``stderr``. This class creates a UNIX pipe whose read
end is added to the IO multiplexer, and whose write end is used to overwrite
the handles inherited during process creation.

Even without IO redirection, something must replace ``stdin`` and ``stdout``,
otherwise it is possible for the stream used for communication between the
master and slave to be accidentally corrupted by subprocesses run by user code.

The inherited ``stdin`` is replaced by a file descriptor pointing to
``/dev/null``.

Finally Python's :py:data:`sys.stdout` is reopened to ensure line buffering is
active, so that ``print`` statements and suchlike promptly appear in the logs.


Function Call Dispatch
######################

After all initialization is complete, the slave's main thread sits in a loop
reading from a :py:class:`Channel <econtext.core.Channel>` connected to the
:py:data:`CALL_FUNCTION <econtext.core.CALL_FUNCTION>` handle. This handle is
written to by
:py:meth:`call_with_deadline() <econtext.master.Context.call_with_deadline>`
and :py:meth:`call() <econtext.master.Context.call>`.


Shutdown
########

When the master signals the :py:data:`CALL_FUNCTION
<econtext.core.CALL_FUNCTION>` :py:class:`Channel <econtext.core.Channel>` is
closed, the slave calls :py:meth:`shutdown() <econtext.core.Broker.shutdown>`
followed by :py:meth:`wait() <econtext.core.Broker.wait>` on its own broker,
triggering graceful shutdown.

During shutdown, the master will wait a few seconds for slaves to disconnect
gracefully before force disconnecting them, while the slaves will use that time
to call :py:meth:`socket.shutdown(SHUT_WR) <socket.socket.shutdown>` on their
:py:class:`IoLogger <econtext.core.IoLogger>` socket's write ends before
draining any remaining data buffered on the read ends.

If the main thread (responsible for function call dispatch) fails to trigger
shutdown (because some user function is hanging), then the eventual force
disconnection by the master will cause the IO multiplexer thread to enter
shutdown by itself.


.. _stream-protocol:

Stream Protocol
---------------

Once connected, a basic framing protocol is used to communicate between
master and slave:

+------------+-------+-----------------------------------------------------+
| Field      | Size  | Description                                         |
+============+=======+=====================================================+
| ``hmac``   | 20    | SHA-1 MAC over (``length || data``)                 |
+------------+-------+-----------------------------------------------------+
| ``length`` | 4     | Message length                                      |
+------------+-------+-----------------------------------------------------+
| ``data``   | n/a   | Pickled message data.                               |
+------------+-------+-----------------------------------------------------+

The ``data`` component always consists of a 2-tuple, `(handle, data)`, where
``handle`` is an integer describing the message target and ``data`` is the
value to be delivered to the target.

Masters listen on the following handles:

.. data:: econtext.core.FORWARD_LOG

    Receives `(logger_name, level, msg)` 3-tuples and writes them to the
    master's ``econtext.ctx.<context_name>`` logger.

.. data:: econtext.core.GET_MODULE

    Receives `(reply_to, fullname)` 2-tuples, looks up the source code for the
    module named ``fullname``, and writes the source along with some metadata
    back to the handle ``reply_to``. If lookup fails, ``None`` is sent instead.

Slaves listen on the following handles:

.. data:: econtext.core.CALL_FUNCTION

    Receives `(with_context, mod_name, class_name, func_name, args, kwargs)`
    5-tuples from
    :py:meth:`call_with_deadline() <econtext.master.Context.call_with_deadline>`,
    imports ``mod_name``, then attempts to execute
    `class_name.func_name(\*args, \**kwargs)`.

Additional handles are created to receive the result of every function call
triggered by :py:meth:`call_with_deadline() <econtext.master.Context.call_with_deadline>`.


Sentinel Value
##############

.. autodata:: econtext.core._DEAD

The special value :py:data:`econtext.core._DEAD` is used to signal
disconnection or closure of the remote end. It is used internally by
:py:class:`Channel <econtext.core.Channel>` and also passed to any function
still registered with :py:meth:`add_handle_cb()
<econtext.core.Context.add_handle_cb>` during Broker shutdown.


Use of Pickle
#############

The current implementation uses the Python :py:mod:`cPickle` module, with
mitigations to prevent untrusted slaves from triggering code excution in the
master. The primary reason for using :py:mod:`cPickle` is that it is
computationally efficient, and avoids including a potentially large body of
serialization code in the bootstrap.

The pickler active in slave contexts will instantiate any class, however in the
master it is initially restricted to only permitting
:py:class:`CallError <econtext.core.CallError>` and :py:data:`_DEAD
<econtext.core._DEAD>`. While not recommended, it is possible to register more
using :py:meth:`econtext.master.LocalStream.allow_class`.

The choice of Pickle is one area to be revisited later. All accounts suggest it
cannot be used securely, however few of those accounts appear to be expert, and
none mention any additional attacks that would not be prevented by using a
restrictive class whitelist.


Use of HMAC
###########

In the current implementation the use of HMAC signatures over data frames is
mostly redundant since all communication occurs over SSH, however in order to
reduce resource usage, it is planned to support connecting back to the master
via plain TCP, at which point the signatures become important.


The IO Multiplexer
------------------

Since we must include our IO multiplexer as part of the bootstrap,
off-the-shelf implementations are for the most part entirely inappropriate. For
example, a minimal copy of Twisted weighs in at around 440KiB and is composed
of approximately 115 files. Even if we could arrange for an entire Python
package to be transferred during bootstrap, this minimal configuration is
massive in comparison to econtext's solution, multiplies quickly in the
presence of many machines, and would require manually splitting up the parts of
Twisted that we would like to use.


Differences Between Master And Slave Brokers
############################################

The main difference between :py:class:`econtext.core.Broker` and
:py:class:`econtext.master.Broker` is that when the stream connection to the
parent is lost in a slave, the broker will trigger its own shutdown.


The Module Importer
-------------------

:py:class:`econtext.core.Importer` is still a work in progress, as there
are a variety of approaches to implementing it, and the present implementation
is not pefectly efficient in every case.

It operates by intercepting ``import`` statements via `sys.meta_path`, asking
Python if it can satisfy the import by itself, and if not, indicating to Python
that it is capable of loading the module.

In :py:meth:`load_module() <econtext.core.Importer.load_module>` an RPC is
started to the master, requesting the module source code. Once the source is
fetched, the method builds a new module object using the best practice
documented in PEP-302.


Minimizing Roundtrips
#####################

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
:py:class:`econtext.core.Importer` first checks to see if the module belongs to
a package it has previously imported, and if so, ignores the request if the
module does not appear in the enumeration of child modules belonging to the
package.


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

At some point it is likely econtext will be extended to support starting slaves
running on Windows. When that happens, it would be nice if the process model on
Windows and UNIX did not differ, and in fact the code used on both were
identical.
