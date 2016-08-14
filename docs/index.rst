
Python Execution Contexts
=========================

**5KiB of sugar and no fat!**

.. toctree::
   :maxdepth: 1

   self
   howitworks
   getting_started
   api
   history


Introduction
------------

The Python ``econtext`` package implements external *execution contexts*: an
execution context is somewhere you can run Python functions external to your
main process, even on a remote machine.

There is **no requirement for installing packages, copying files around,
writing shell scripts, upfront configuration, or providing any secondary link
to the remote machine**. Due to its origins for use in managing potentially
damaged infrastructure, the **remote machine need not even have a writeable
filesystem**.

It is not intended as a generic RPC framework; the goal is to provide a robust
and efficient low-level API on which tools like `Salt`_ or `Ansible`_ can be
built, and while the API is quite friendly and similar in scope to `Fabric`_,
ultimately it should not be used directly by consumer software.

.. _Salt: https://docs.saltstack.com/en/latest/
.. _Ansible: http://docs.ansible.com/
.. _Fabric: http://docs.fabfile.org/en/

The focus is to centralize and perfect the intricate dance required to run
Python code safely and efficiently on a remote machine, while avoiding
temporary files or large chunks of error-prone shell scripts.


Automatic Bootstrap
###################

The package's main feature is enabling your Python program to bootstrap and
communicate with new Python programs under its control running on remote
machines, **using only an existing installed Python interpreter and SSH
client**, something that by default can be found on almost all contemporary
machines in the wild. To accomplish bootstrap, econtext uses a single 500 byte
SSH command line and 5KB of its own source code sent to stdin of the remote SSH
connection.

.. code::

    $ python preamble_size.py
    SSH command size: 411
    Preamble size: 4845 (4.73KiB)
    econtext.master size: 2640 (2.58KiB)

Once bootstrapped, the remote process is configured with a customizable
**argv[0]**, readily visible to system administrators of the remote machine
using the UNIX **ps** command:

.. code::

    20051 ?        Ss     0:00  \_ sshd: dmw [priv]
    20053 ?        S      0:00  |   \_ sshd: dmw@notty
    20054 ?        Ssl    0:00  |       \_ econtext:dmw@Eldil.home:22476
    20103 ?        S      0:00  |           \_ tar zxvf myapp.tar.gz

The example context was started by UID ``dmw`` on host ``Eldil.home``, process
ID ``22476``.


IO Multiplexer
##############

The bootstrap includes a compact IO multiplexer (like Twisted or asyncio) that
allows it to perform work in the background while executing your program's
code. For example, the remote context can be used to **connect to a new user on
the remote machine using sudo**, or as an intermediary for extending the
program's domain of control outward to other machines, enabling your program to
**manipulate machines behind a firewall**, or enable its **data plane to cohere
to your network topology**.

The multiplexer also ensures the remote process is terminated if your Python
program crashes, communication is lost, or the application code running in the
context has hung.


Module Forwarder
################

In addition to an IO multiplexer, the external context is configured with a
custom `PEP-302 importer`_ that forwards requests for unknown Python modules
back to the host machine. When your program asks an external context to execute
code from an unknown module, all requisite modules are transferred
automatically and imported entirely in RAM without need for further
configuration.

.. _PEP-302 importer: https://www.python.org/dev/peps/pep-0302/

.. code-block:: python

    import myapp.mypkg.mymodule

    # myapp/__init__.py, myapp/mypkg/__init__.py, and myapp/mypkg/mymodule.py
    # are transferred automatically.
    print context.call(myapp.mymodule.my_function)


Logging Forwarder
#################

The bootstrap configures the remote process's Python logging package to forward
all logs back to the local process, enabling management of program logs in one
location.

.. code::

    18:15:29 D econtext.ctx.k3: econtext: Importer.find_module('econtext.zlib')
    18:15:29 D econtext.ctx.k3: econtext: _dispatch_calls((1002L, False, 'posix', None, 'system', ('ls -l /proc/self/fd',), {}))


Stdio Forwarder
###############

To ease porting of crusty old infrastructure scripts to Python, the bootstrap
redirects stdio for itself and any child processes back into the logging
framework. This allows use of functions as basic as **os.system('hostname;
uptime')** without further need to capture or manage output.

.. code::

   18:17:28 D econtext.ctx.k3: econtext: _dispatch_calls((1002L, False, 'posix', None, 'system', ('hostname; uptime',), {}))
   18:17:56 I econtext.ctx.k3: stdout: k3
   18:17:56 I econtext.ctx.k3: stdout: 17:37:10 up 562 days,  2:25,  5 users,  load average: 1.24, 1.13, 1.14


Blocking Code Friendly
######################

Within each process, a private thread runs the I/O multiplexer, leaving the
main thread and any additional application threads free to perform useful work.

While econtext is internally asynchronous it hides this asynchrony from
consumer code. This is since writing asynchronous code is mostly a foreign
concept to the target application of managing infrastructure. It should be
possible to rewrite a shell script in Python without significant restructuring,
or mind-bending feats of comprehension to understand control flow.

Before:

.. code-block:: sh

    #!/bin/bash
    # Install our application.

    tar zxvf app.tar.gz

After:

.. code-block:: python

    def install_app():
        """
        Install our application.
        """
        os.system('tar zxvf app.tar.gz')

    context.call(install_app)

Or even:

.. code-block:: python

    context.call(os.system, 'tar zxvf app.tar.gz')

Exceptions raised by function calls are propagated back to the parent program,
and timeouts can be configured to ensure failed calls do not block progress of
the parent.


Support For Single File Programs
################################

Programs that are self-contained within a single Python script are supported.
External contexts are configured such that any attempt to execute a function
from the main Python script will correctly cause that script to be imported as
usual into the slave process.

.. code-block:: python

    #!/usr/bin/env python
    """
    Install our application on a remote machine.

    Usage:
        install_app.py <hostname>

    Where:
        <hostname>  Hostname to install to.
    """
    import os
    import sys

    import econtext


    def install_app():
        os.system('tar zxvf my_app.tar.gz')


    def main(broker):
        if len(sys.argv) != 2:
            print __doc__
            sys.exit(1)

        context = broker.get_remote(sys.argv[1])
        context.call(install_app)

    if __name__ == '__main__' and not econtext.slave:
        import econtext.utils
        econtext.utils.run_with_broker(main)


Event-driven IO
###############

Code running in a remote context can be connected to a *Channel*. Channels are
used to send data asynchronously back to the parent, without further need for
the parent to poll for changes. This is useful for monitoring systems managing
a large fleet of machines, or to alert the parent of unexpected state changes.

.. code-block:: python

    def tail_log_file(channel, path='/var/log/messages'):
        """
        Forward new lines in a log file to the parent.
        """
        size = os.path.getsize(path)

        while channel.open():
            new_size = os.path.getsize(path)
            if new_size == size:
                time.sleep(1)
                continue
            elif new_size < size:
                size = 0

            fp = file(path, 'r')
            fp.seek(size)
            channel.send(fp.read(new_size - size))
            fp.close()
            size = new_size


Compatibility
#############

The package is written using syntax compatible all the way back to **Python
2.4** released November 2004, making it suitable for managing a fleet of
potentially ancient corporate hardware. For example econtext can be used out of
the box against Red Hat Enterprise Linux 5, released in 2007.

There is currently no support for Python 3, and no solid plan for supporting it
any time soon. Due to constraints on implementation size and desire for
compatibility with ancient Python versions, conventional porting methods such
as ``six.py`` are likely to be unsuitable.
