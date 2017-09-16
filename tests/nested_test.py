import os
import mitogen.utils

@mitogen.utils.run_with_router
def main(router):
    mitogen.utils.log_to_file()

    context = None
    for x in range(1, 11):
        print 'Connect local%d via %s' % (x, context)
        context = router.local(via=context, name='local%d' % x)

    context.call(os.system, 'pstree -s python -s mitogen')

