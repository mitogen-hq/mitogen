import mitogen
import mitogen.service


class FileService(mitogen.service.Service):
    """
    Simple file server, for demonstration purposes only! Use of this in
    real code would be a security vulnerability as it would permit children
    to read any file from the master's disk.
    """

    @mitogen.service.expose(policy=mitogen.service.AllowAny())
    @mitogen.service.arg_spec(spec={
        'path': str
    })
    def read_file(self, path):
        with open(path, 'rb') as fp:
            return fp.read()


def download_file(source_context, path):
    s = source_context.call_service(
        service_name=FileService,  # may also be string 'pkg.mod.FileService'
        method_name='read_file',
        path=path,
    )

    with open(path, 'w') as fp:
        fp.write(s)


def download_some_files(source_context, paths):
    for path in paths:
        download_file(source_context, path)


@mitogen.main()
def main(router):
    pool = mitogen.service.Pool(router, services=[
        FileService(router),
    ])

    remote = router.ssh(hostname='k3')
    remote.call(download_some_files,
        source_context=router.myself(),
        paths=[
            '/etc/passwd',
            '/etc/hosts',
        ]
    )
    pool.stop()

