
import econtext


def with_broker(func):
    def wrapper(*args, **kwargs):
        broker = econtext.Broker()
        try:
            return func(broker, *args, **kwargs)
        finally:
            broker.Finalize()

    wrapper.func_name = func.func_name
    return wrapper
