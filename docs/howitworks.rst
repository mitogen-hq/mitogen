
How econtext Works
==================

Some effort is required to accomplish the seemingly magical feat of
bootstrapping a remote Python process without any software installed on the
remote machine. The steps involved are unlikely to be immediately obvious to
the casual reader, and they required several iterations to discover, so we
document them thoroughly below.


The UNIX First Stage
--------------------

To allow delivery of the bootstrap compressed using ``zlib``, it is necessary
for something on the remote to be prepared to decompress the payload and feed
it to a Python interpreter. Since we would like to avoid writing an error-prone
shell fragment to implement this, and since we must avoid writing to the remote
machine's disk in case it is read-only, the Python process started on the
remote machine by ``econtext`` immediately forks in order to implement the
decompression.


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
pipe, and the child half begins reading the ``zlib``-compressed payload
supplied on ``stdin`` by the econtext master, and writing the decompressed
result to the write-end of the UNIX pipe.

To allow recovery of ``stdin`` for reuse by the bootstrapped process for
master<->slave communication, it is necessary for the first stage to avoid
closing ``stdin`` or reading from it until until EOF. Therefore, the master
sends the zlib-compressed payload prefixed with an integer size, allowing
reading by the first stage of exactly the required bytes.


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

Now we have the mechanism in place to send a zlib-compressed script to the
remote Python interpreter, it is time to choose what to send.

The script sent is simply the source code for :py:mod:`econtext.core`, with a
single line suffixed to trigger execution of the
:py:meth:`econtext.core.ExternalContext.main` function. The encoded arguments
to the main function include some additional details, such as the logging package
level that was active in the parent process, and a random secret key used to
generate HMAC signatures over the data frames that will be exchanged after
bootstrap.

After the script source code is prepared, it is passed through
:py:func:`econtext.master.minimize_source` to strip it of docstrings and
comments, while preserving original line numbers. This reduces the compressed
payload size by around 20%.



Signalling Success
##################


ExternalContext main()
----------------------


Reaping The First Stage
#######################


Generating A Synthetic `econtext` Package
#########################################


Setup The Broker And Master Context
###################################


Setup Logging
#############


The Module Importer
###################


Standard IO Redirection
#######################


Function Call Dispatch
######################



Stream Protocol
---------------


Use of HMAC
###########

In the current version of econtext, the use of HMAC signatures over data frames
is mostly redundant, since all communication occurs over SSH, however in order
to reduce resource usage, it is planned to support connecting back to the
master via plain TCP, at which point the signatures become important.


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

* Self destruct.


The Module Importer
-------------------

Minimizing Roundtrips
#####################


Child Package Enumeration
#########################


Negative Cache Hits
###################



Use Of Threads
--------------

The package mandatorily runs the IO multiplexer in a thread. This is so the
multiplexer always retains control flow in order to shut down gracefully, say,
if the user's code has hung and the master context has disconnected.

While it is possible for the IO multiplexer to recover control of a hung
function call on UNIX using for example ``signal.SIGALRM``, this mechanism is
not portable to non-UNIX operating systems, and does not work in every case,
for example when Python blocks signals during a variety of :py:mod:`threading`
package operations.

At some point it is likely econtext will be extended to support starting slaves
running on Windows. When that happens, it would be nice if the process model on
Windows and UNIX did not differ, and in fact the code used on both were
identical.
