"""
I am a self-contained program!
"""

import mitogen.master


def repr_stuff():
    return repr([__name__, 50])


def main(router):
    context = router.local()
    print context.call(repr_stuff)

if __name__ == '__main__' and mitogen.is_master:
    import mitogen.utils
    mitogen.utils.run_with_router(main)
