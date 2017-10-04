
Getting Started
===============

xxx


.. _serialization-rules:

RPC Serialization Rules
-----------------------

The following built-in types may be used as parameters or return values in
remote procedure calls:

* :class:`bool`
* :class:`bytearray`
* :func:`bytes`
* :class:`dict`
* :class:`int`
* :func:`list`
* :class:`long`
* :class:`str`
* :func:`tuple`
* :func:`unicode`

User-defined types may not be used, except for:

* :py:class:`mitogen.core.CallError`
* :py:class:`mitogen.core.Context`
* :py:class:`mitogen.core._DEAD`
