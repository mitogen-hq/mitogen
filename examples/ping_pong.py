# Wire up a ping/pong counting loop between 2 subprocesses.

from __future__ import print_function
import mitogen.core
import mitogen.select


@mitogen.core.takes_router
def ping_pong(control_sender, router):
    with mitogen.core.Receiver(router) as recv:
        # Tell caller how to communicate with us.
        control_sender.send(recv.to_sender())

        # Wait for caller to tell us how to talk back:
        data_sender = recv.get().unpickle()

        n = 0
        while (n + 1) < 30:
            n = recv.get().unpickle()
            print('the number is currently', n)
            data_sender.send(n + 1)


@mitogen.main()
def main(router):
    # Create a receiver for control messages.
    with mitogen.core.Receiver(router) as recv:
        # Start ping_pong() in child 1 and fetch its sender.
        c1 = router.local()
        c1_call = c1.call_async(ping_pong, recv.to_sender())
        c1_sender = recv.get().unpickle()

        # Start ping_pong() in child 2 and fetch its sender.
        c2 = router.local()
        c2_call = c2.call_async(ping_pong, recv.to_sender())
        c2_sender = recv.get().unpickle()

        # Tell the children about each others' senders.
        c1_sender.send(c2_sender)
        c2_sender.send(c1_sender)

    # Start the loop.
    c1_sender.send(0)

    # Wait for both functions to return.
    mitogen.select.Select.all([c1_call, c2_call])
