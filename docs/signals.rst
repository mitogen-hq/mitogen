
Signals
=======

Mitogen exposes a simplistic signal mechanism to help decouple its internal
components. When a signal is fired by a particular instance of a class, any
functions registered to receive it will be called back.


Functions
---------

.. function:: mitogen.core.listen (obj, name, func)

    Arrange for `func(\*args, \*\*kwargs)` to be invoked when the named signal
    is fired by `obj`.

.. function:: mitogen.core.fire (obj, name, \*args, \*\*kwargs)

    Arrange for `func(\*args, \*\*kwargs)` to be invoked for every function
    registered for the named signal on `obj`.



List
----

These signals are used internally by Mitogen.

.. list-table::
    :header-rows: 1
    :widths: auto

    * - Class
      - Name
      - Description

    * - :py:class:`mitogen.core.Stream`
      - ``disconnect``
      - Fired on the Broker thread when disconnection is detected.

    * - :py:class:`mitogen.core.Context`
      - ``disconnect``
      - Fired on the Broker thread during shutdown (???)

    * - :py:class:`mitogen.core.Router`
      - ``shutdown``
      - Fired on the Broker thread after Broker.shutdown() is called.

    * - :py:class:`mitogen.core.Broker`
      - ``shutdown``
      - Fired after Broker.shutdown() is called.

    * - :py:class:`mitogen.core.Broker`
      - ``exit``
      - Fired immediately prior to the broker thread exit.

