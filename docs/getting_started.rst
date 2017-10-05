
Getting Started
===============

.. warning::

    This section is incomplete.


Liability Waiver
----------------

.. image:: images/radiation.png
    :align: right

Before proceeding, it is crucial you understand what you're involving yourself
and possibly your team with:

* Constructing the most fundamental class, :py:class:`Broker
  <mitogen.master.Broker>`, causes a new thread to be spawned, exposing a huge
  class of difficult to analyse behaviours that Python software generally does
  not suffer from.

  While every effort is made to hide this complexity, you should expect
  threading-related encounters during development. See :ref:`troubleshooting`
  for more information.

* While high-level abstractions are provided, you must understand how Mitogen
  works before depending on it. Mitogen interacts with many aspects of the
  operating system, network, SSH, sudo, sockets, TTYs, Python runtime, and
  timing and ordering uncertainty introduced through interaction with the
  network and OS scheduling.

  Knowledge of this domain is typically gained through painful years of ugly
  attempts hacking system-level programs, and learning through continual
  suffering how to debug the messes left behind. If you feel you lack resources
  to diagnose problems independently, Mitogen is not appropriate, prefer a
  higher level solution instead. Bug reports failing this expectation risk
  unfavourable treatment.


Broker And Router
-----------------

.. image:: images/layout.png
.. currentmodule:: mitogen.master

Execution starts when your program constructs a :py:class:`Broker` and
associated :py:class:`Router`. The broker is responsible for multiplexing IO to
children from a private thread, while in children, it is additionally
responsible for ensuring robust destruction if communication with the master
is lost.

:py:class:`Router` is responsible for receiving messages and either dispatching
them to a callback from the broker thread (registered by
:py:meth:`add_handler() <mitogen.core.Router.add_handler>`), or forwarding them
to a :py:class:`Stream <mitogen.core.Stream>`. See :ref:`routing` for an
in-depth description. :py:class:`Router` also doubles as the entry point to
Mitogen's public API.

.. code-block:: python

    broker = mitogen.master.Broker()
    router = mitogen.master.Router(broker)

    try:
        # Your code here.
    finally:
        broker.shutdown()

As your program will not exit if threads are still running when the main thread
exits, it is crucial :py:meth:`Broker.shutdown` is called reliably at exit.
Helpers are provided by :py:mod:`mitogen.utils` to ensure :py:class:`Broker` is
reliably destroyed:

.. code-block:: python

    def do_mitogen_stuff(router):
        # Your code here.

    mitogen.utils.run_with_router(do_mitogen_stuff)

If your program cannot live beneath :py:func:`mitogen.utils.run_with_router` on
the stack, you must must arrange for :py:meth:`Broker.shutdown` to be called
anywhere exit of the main thread may be triggered.


Creating A Context
------------------

Contexts simply refer to external Python programs over which your program has
control. They can be created as subprocesses on the local machine, in another
user account via ``sudo``, on a remote machine via ``ssh``, and in any
recursive combination of the above.

Now a :py:class:`Router` exists, our first :py:class:`Context` can be created.


.. _serialization-rules:

RPC Serialization Rules
-----------------------

The following built-in types may be used as parameters or return values in
remote procedure calls:

* bool
* bytearray
* bytes
* dict
* int
* list
* long
* str
* tuple
* unicode

User-defined types may not be used, except for:

* :py:class:`mitogen.core.CallError`
* :py:class:`mitogen.core.Context`
* :py:class:`mitogen.core._DEAD`


.. _troubleshooting:

Troubleshooting
---------------

.. warning::

    This section is incomplete.

A typical example is a hang due to your application's main thread exitting
perhaps due to an unhandled exception, without first arranging for any
:py:class:`Broker <mitogen.master.Broker>` to be shut down gracefully.

Another example would be your main thread hanging indefinitely because a bug
in Mitogen fails to notice an event (such as RPC completion) your thread is
waiting for will never complete. Solving this kind of hang is a work in
progress.

router.enable_debug()
