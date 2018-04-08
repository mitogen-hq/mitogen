
.. currentmodule:: mitogen.service


Service Framework
=================

Mitogen includes a simple framework for implementing services exposed to other
contexts, with built-in subclasses that capture some common service models.
This is a work in progress, and new functionality will be added as common usage
patterns emerge.


Overview
--------


Example
-------

.. code-block:: python

    import mitogen
    import mitogen.service


    class FileService(mitogen.service.Service):
        """
        Simple file server, for demonstration purposes only! Use of this in
        real code would be a security vulnerability as it would permit children
        to read arbitrary files from the master's disk.
        """
        handle = 500
        required_args = {
            'path': str
        }

        def dispatch(self, args, msg):
            with open(args['path'], 'r') as fp:
                return fp.read()


    def download_file(context, path):
        s = mitogen.service.call(context, FileService.handle, {
            'path': path
        })

        with open(path, 'w') as fp:
            fp.write(s)


    @mitogen.core.takes_econtext
    def download_some_files(paths, econtext):
        for path in paths:
            download_file(econtext.master, path)


    @mitogen.main()
    def main(router):
        pool = mitogen.service.Pool(router, size=1, services=[
            FileService(router),
        ])

        remote = router.ssh(hostname='k3')
        remote.call(download_some_files, [
            '/etc/passwd',
            '/etc/hosts',
        ])
        pool.stop()


Reference
---------

.. autoclass:: mitogen.service.Policy
.. autoclass:: mitogen.service.AllowParents
.. autoclass:: mitogen.service.AllowAny

.. autofunction:: mitogen.service.arg_spec
.. autofunction:: mitogen.service.expose

.. autofunction:: mitogen.service.Service

.. autoclass:: mitogen.service.Service
    :members:

.. autoclass:: mitogen.service.DeduplicatingService
    :members:

.. autoclass:: mitogen.service.Pool
    :members:

