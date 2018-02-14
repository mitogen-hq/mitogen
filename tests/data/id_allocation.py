
import mitogen.core
import mitogen.parent


@mitogen.core.takes_econtext
def allocate_an_id(econtext):
    mitogen.parent.upgrade_router(econtext)
    return econtext.router.allocate_id()

