
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

* :py:class:`econtext.core.CallError`
* :py:class:`econtext.core.Context`
* :py:class:`econtext.core._Dead`
