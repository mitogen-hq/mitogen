import logging
import os

import mitogen.ssh
import mitogen.sudo
import mitogen.utils

@mitogen.utils.run_with_router
def main(router):
    mitogen.utils.log_to_file(io=False)
    child1 = router.ssh(name='u', hostname='u')
    child2 = router.sudo(
        username='sudo_pw_test',
        password='x',
        name='sudo_pw_test',
        via=child1,
    )
    child2.call(os.system, 'id')
