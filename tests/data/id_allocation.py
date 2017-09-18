
import mitogen.core
import mitogen.master


@mitogen.core.takes_econtext
def allocate_an_id(econtext):
    mitogen.master.upgrade_router(econtext)
    return econtext.router.allocate_id()

