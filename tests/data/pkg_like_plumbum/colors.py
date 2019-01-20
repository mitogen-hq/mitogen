
import sys


class EvilObject(object):
    """
    Wild cackles! I have come to confuse perplex your importer with rainbows!
    """

sys.modules[__name__] = EvilObject()

