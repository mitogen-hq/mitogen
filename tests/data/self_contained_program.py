"""
I am a self-contained program!
"""

import econtext.master


def repr_stuff():
    return repr([__name__, 50])


def main():
    broker = econtext.master.Broker()
    try:
        context = econtext.master.connect(broker)
        print context.call(repr_stuff)
    finally:
        broker.shutdown()
        broker.join()

if __name__ == '__main__' and not econtext.slave:
    main()
