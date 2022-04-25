"""
Measure latency of local service RPC.
"""
import mitogen
import mitogen.core
import mitogen.service


class MyService(mitogen.service.Service):
    @mitogen.service.expose(policy=mitogen.service.AllowParents())
    def ping(self):
        return 'pong'


@mitogen.main()
def main(router):
    f = router.fork()
    t0 = mitogen.core.now()
    for x in range(1000):
        f.call_service(service_name=MyService, method_name='ping')
    print('++', int(1e6 * ((mitogen.core.now() - t0) / (1.0+x))), 'usec')
