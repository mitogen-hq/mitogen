
import mitogen.core


@mitogen.core.takes_router
def allocate_an_id(router):
    return router.allocate_id()

