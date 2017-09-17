
Importer Wall Of Shame
----------------------

The following modules and packages run magic during ``__init.py__`` that makes
life hard for Mitogen. Executing code during module import is always bad, and
Mitogen is a concrete benchmark for why it's bad.

Bugs will probably be filed for these in time, but it does not address the huge
installed base of existing old software versions, so hacks are needed anyway.


``pkg_resources``
=================

Anything that imports ``pkg_resources`` will eventually cause ``pkg_resources``
to try and import and scan ``__main__`` for its ``__requires__`` attribute
(``pkg_resources/__init__.py::_build_master()``). This breaks any app that is
not expecting its ``__main__`` to suddenly be sucked over a network and
injected into a remote process, like py.test.

A future version of Mitogen might have a more general hack that doesn't import
the master's ``__main__`` as ``__main__`` in the slave, avoiding all kinds of
issues like these.

**What could it do instead?**

* Explicit is better than implicit: wait until the magical behaviour is
  explicitly requested (i.e. an API call).

* Use ``get("__main__")`` on :py:data:`sys.modules` rather than ``import``, but
  this method isn't general enough, it only really helps tools like Mitogen.


``pbr``
=======

It claims to use ``pkg_resources`` to read version information
(``_get_version_from_pkg_metadata()``), which would result in PEP-302 being
reused and everything just working wonderfully, but instead it actually does
direct filesystem access. So we smodge the environment with a ``PBR_VERSION``
environment variable to override any version that was defined. This will
probably break code I haven't seen yet.

**What could it do instead?**

* ``pkg_resources.get_resource_stream()``
