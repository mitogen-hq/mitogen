
Signals
=======


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
      - ``crash``
      - Fired when a crash occurs on the broker thread. Used by client apps to
        hasten shutdown (e.g. by disconnect

    * - :py:class:`mitogen.core.Broker`
      - ``shutdown``
      - Fired after Broker.shutdown() is called.

    * - :py:class:`mitogen.core.Broker`
      - ``exit``
      - Fired immediately prior to the broker thread exit.

