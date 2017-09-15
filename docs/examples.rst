
Examples
========


Recursively Nested Bootstrap
----------------------------

This demonstrates the library's ability to use slave contexts to recursively
proxy connections to additional slave contexts, with a uniform API to any
slave, and all features (function calls, import forwarding, stdio forwarding,
log forwarding) functioning transparently.

This example uses a chain of local contexts for clarity, however SSH and sudo
contexts work identically.

nested.py:

.. code-block:: python

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


Output:

.. code-block:: shell

    $ python nested.py
    Connect local1 via None
    Connect local2 via Context(1, 'local1')
    Connect local3 via Context(2, 'local2')
    Connect local4 via Context(3, 'local3')
    Connect local5 via Context(4, 'local4')
    Connect local6 via Context(5, 'local5')
    Connect local7 via Context(6, 'local6')
    Connect local8 via Context(7, 'local7')
    Connect local9 via Context(8, 'local8')
    Connect local10 via Context(9, 'local9')
    18:14:07 I ctx.local10: stdout: -+= 00001 root /sbin/launchd
    18:14:07 I ctx.local10: stdout:  \-+= 08126 dmw /Applications/iTerm.app/Contents/MacOS/iTerm2
    18:14:07 I ctx.local10: stdout:    \-+= 10638 dmw /Applications/iTerm.app/Contents/MacOS/iTerm2 --server bash --login
    18:14:07 I ctx.local10: stdout:      \-+= 10639 dmw bash --login
    18:14:07 I ctx.local10: stdout:        \-+= 13632 dmw python nested.py
    18:14:07 I ctx.local10: stdout:          \-+- 13633 dmw mitogen:dmw@Eldil.local:13632
    18:14:07 I ctx.local10: stdout:            \-+- 13635 dmw mitogen:dmw@Eldil.local:13633
    18:14:07 I ctx.local10: stdout:              \-+- 13637 dmw mitogen:dmw@Eldil.local:13635
    18:14:07 I ctx.local10: stdout:                \-+- 13639 dmw mitogen:dmw@Eldil.local:13637
    18:14:07 I ctx.local10: stdout:                  \-+- 13641 dmw mitogen:dmw@Eldil.local:13639
    18:14:07 I ctx.local10: stdout:                    \-+- 13643 dmw mitogen:dmw@Eldil.local:13641
    18:14:07 I ctx.local10: stdout:                      \-+- 13645 dmw mitogen:dmw@Eldil.local:13643
    18:14:07 I ctx.local10: stdout:                        \-+- 13647 dmw mitogen:dmw@Eldil.local:13645
    18:14:07 I ctx.local10: stdout:                          \-+- 13649 dmw mitogen:dmw@Eldil.local:13647
    18:14:07 I ctx.local10: stdout:                            \-+- 13651 dmw mitogen:dmw@Eldil.local:13649
    18:14:07 I ctx.local10: stdout:                              \-+- 13653 dmw pstree -s python -s mitogen
    18:14:07 I ctx.local10: stdout:                                \--- 13654 root ps -axwwo user,pid,ppid,pgid,command
