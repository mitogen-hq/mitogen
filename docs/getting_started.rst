
Getting Started
===============

xxx


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
* :py:class:`mitogen.core._Dead`
