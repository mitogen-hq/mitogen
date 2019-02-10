
#
# This program is a stand-in for good intro docs. It just documents various
# basics of using Mitogen.
#

from __future__ import absolute_import
from __future__ import print_function

import hashlib
import io
import os
import spwd

import mitogen.core
import mitogen.master
import mitogen.service
import mitogen.utils



def get_file_contents(path):
    """
    Get the contents of a file.
    """
    with open(path, 'rb') as fp:
        # mitogen.core.Blob() is a bytes subclass with a repr() that returns a
        # summary of the blob, rather than the raw blob data. This makes
        # logging output *much* nicer. Unlike most custom types, blobs can be
        # serialized.
        return mitogen.core.Blob(fp.read())


def put_file_contents(path, s):
    """
    Write the contents of a file.
    """
    with open(path, 'wb') as fp:
        fp.write(s)


def streamy_download_file(context, path):
    """
    Fetch a file from the FileService hosted by `context`.
    """
    bio = io.BytesIO()

    # FileService.get() is not actually an exposed service method, it's just a
    # classmethod that wraps up the complicated dance of implementing the
    # transfer.
    ok, metadata = mitogen.service.FileService.get(context, path, bio)

    return {
        'success': ok,
        'metadata': metadata,
        'size': len(bio.getvalue()),
    }


def get_password_hash(username):
    """
    Fetch a user's password hash.
    """
    try:
        h = spwd.getspnam(username)
    except KeyError:
        return None

    # mitogen.core.Secret() is a Unicode subclass with a repr() that hides the
    # secret data. This keeps secret stuff out of logs. Like blobs, secrets can
    # also be serialized.
    return mitogen.core.Secret(h)


def md5sum(path):
    """
    Return the MD5 checksum for a file.
    """
    return hashlib.md5(get_file_contents(path)).hexdigest()



def work_on_machine(context):
    """
    Do stuff to a remote context.
    """
    print("Created context. Context ID is", context.context_id)

    # You don't need to understand any/all of this, but it's helpful to grok
    # the whole chain:

    # - Context.call() is a light wrapper around .call_async(), the wrapper
    #   simply blocks the caller until a reply arrives.
    # - .call_async() serializes the call signature into a message and passes
    #   it to .send_async()
    # - .send_async() creates a mitogen.core.Receiver() on the local router.
    #   The receiver constructor uses Router.add_handle() to allocate a
    #   'reply_to' handle and install a callback function that wakes the
    #   receiver when a reply message arrives.
    # - .send_async() puts the reply handle in Message.reply_to field and
    #   passes it to .send()
    # - Context.send() stamps the destination context ID into the
    #   Message.dst_id field and passes it to Router.route()
    # - Router.route() uses Broker.defer() to schedule _async_route(msg)
    #   on the Broker thread.
    # [broker thread]
    # - The broker thread wakes and calls _async_route(msg)
    # - Router._async_route() notices 'dst_id' is for a remote context and
    #   looks up the stream on which messages for dst_id should be sent (may be
    #   direct connection or not), and calls Stream.send()
    # - Stream.send() packs the message into a bytestring, appends it to
    #   Stream._output_buf, and calls Broker.start_transmit()
    # - Broker finishes work, reenters IO loop. IO loop wakes due to writeable
    #   stream.
    # - Stream.on_transmit() writes the full/partial buffer to SSH, calls
    #   stop_transmit() to mark the stream unwriteable once _output_buf is
    #   empty.
    # - Broker IO loop sleeps, no readers/writers.
    # - Broker wakes due to SSH stream readable.
    # - Stream.on_receive() called, reads the reply message, converts it to a
    #   Message and passes it to Router._async_route().
    # - Router._async_route() notices message is for local context, looks up
    #   target handle in the .add_handle() registry.
    # - Receiver._on_receive() called, appends message to receiver queue.
    # [main thread]
    # - Receiver.get() used to block the original Context.call() wakes and pops
    #   the message from the queue.
    # - Message data (pickled return value) is deserialized and returned to the
    #   caller.
    print("It's running on the local machine. Its PID is",
          context.call(os.getpid))

    # Now let's call a function defined in this module. On receiving the
    # function call request, the child attempts to import __main__, which is
    # initially missing, causing the importer in the child to request it from
    # its parent. That causes _this script_ to be sent as the module source
    # over the wire.
    print("Calling md5sum(/etc/passwd) in the child:",
          context.call(md5sum, '/etc/passwd'))

    # Now let's "transfer" a file. The simplest way to do this is calling a
    # function that returns the file data, which is totally fine for small
    # files.
    print("Download /etc/passwd via function call: %d bytes" % (
        len(context.call(get_file_contents, '/etc/passwd'))
    ))

    # And using function calls, in the other direction:
    print("Upload /tmp/blah via function call: %s" % (
        context.call(put_file_contents, '/tmp/blah', b'blah!'),
    ))

    # Now lets transfer what might be a big files. The problem with big files
    # is that they may not fit in RAM. This uses mitogen.services.FileService
    # to implement streamy file transfer instead. The sender must have a
    # 'service pool' running that will host FileService. First let's do the
    # 'upload' direction, where the master hosts FileService.

    # Steals the 'Router' reference from the context object. In a real app the
    # pool would be constructed once at startup, this is just demo code.
    file_service = mitogen.service.FileService(context.router)

    # Start the pool.
    pool = mitogen.service.Pool(context.router, services=[file_service])

    # Grant access to a file on the local disk from unprivileged contexts.
    # .register() is also exposed as a service method -- you can call it on a
    # child context from any more privileged context.
    file_service.register('/etc/passwd')

    # Now call our wrapper function that knows how to handle the transfer. In a
    # real app, this wrapper might also set ownership/modes or do any other
    # app-specific stuff relating to the file that was transferred.
    print("Streamy upload /etc/passwd: remote result: %s" % (
        context.call(
            streamy_download_file,
            # To avoid hard-wiring streamy_download_file(), we want to pass it
            # a Context object that hosts the file service it should request
            # files from. Router.myself() returns a Context referring to this
            # process.
            context=router.myself(),
            path='/etc/passwd',
        ),
    ))

    # Shut down the pool now we're done with it, else app will hang at exit.
    # Once again, this should only happen once at app startup/exit, not for
    # every file transfer!
    pool.stop(join=True)

    # Now let's do the same thing but in reverse: we use FileService on the
    # remote download a file. This uses context.call_service(), which invokes a
    # special code path that causes auto-initialization of a thread pool in the
    # target, and auto-construction of the target service, but only if the
    # service call was made by a more privileged context. We could write a
    # helper function that runs in the remote to do all that by hand, but the
    # library handles it for us.

    # Make the file accessible. A future FileService could avoid the need for
    # this for privileged contexts.
    context.call_service(
        service_name=mitogen.service.FileService,
        method_name='register',
        path='/etc/passwd'
    )

    # Now we can use our streamy_download_file() function in reverse -- running
    # it from this process and having it fetch from the remote process:
    print("Streamy download /etc/passwd: result: %s" % (
        streamy_download_file(context, '/etc/passwd'),
    ))


def main():
    # Setup logging. Mitogen produces a LOT of logging. Over the course of the
    # stable series, Mitogen's loggers will be carved up so more selective /
    # user-friendly logging is possible. mitogen.log_to_file() just sets up
    # something basic, defaulting to INFO level, but you can override from the
    # command-line by passing MITOGEN_LOG_LEVEL=debug or MITOGEN_LOG_LEVEL=io.
    # IO logging is sometimes useful for hangs, but it is often creates more
    # confusion than it solves.
    mitogen.utils.log_to_file()

    # Construct the Broker thread. It manages an async IO loop listening for
    # reads from any active connection, or wakes from any non-Broker thread.
    # Because Mitogen uses a background worker thread, it is extremely
    # important to pay attention to the use of UNIX fork in your code --
    # forking entails making a snapshot of the state of all locks in the
    # program, including those in the logging module, and thus can create code
    # that appears to work for a long time, before deadlocking randomly.
    # Forking in a Mitogen app requires significant upfront planning!
    broker = mitogen.master.Broker()

    # Construct a Router. This accepts messages (mitogen.core.Message) and
    # either dispatches locally addressed messages to local handlers (added via
    # Router.add_handle()) on the broker thread, or forwards the message
    # towards the target context.

    # The router also acts as an uglyish God object for creating new
    # connections. This was a design mistake, really those methods should be
    # directly imported from e.g. 'mitogen.ssh'.
    router = mitogen.master.Router(broker)

    # Router can act like a context manager. It simply ensures
    # Broker.shutdown() is called on exception / exit. That prevents the app
    # hanging due to a forgotten background thread. For throwaway scripts,
    # there are also decorator versions "@mitogen.main()" and
    # "@mitogen.utils.with_router" that do the same thing with less typing.
    with router:
        # Now let's construct a context. The '.local()' constructor just creates
        # the context as a subprocess, the simplest possible case.
        child = router.local()
        print("Created a context:", child)
        print()

        # This demonstrates the standard IO redirection. We call the print
        # function in the remote context, that should cause a log message to be
        # emitted. Any subprocesses started by the remote also get the same
        # treatment, so it's very easy to spot otherwise discarded errors/etc.
        # from remote tools.
        child.call(print, "Hello from child.")

        # Context objects make it semi-convenient to treat the local machine the
        # same as a remote machine.
        work_on_machine(child)

        # Now let's construct a proxied context. We'll simply use the .local()
        # constructor again, but construct it via 'child'. In effect we are
        # constructing a sub-sub-process. Instead of .local() here, we could
        # have used .sudo() or .ssh() or anything else.
        subchild = router.local(via=child)
        print()
        print()
        print()
        print("Created a context as a child of another context:", subchild)

        # Do everything again with the new child.
        work_on_machine(subchild)

        # We can selectively shut down individual children if we want:
        subchild.shutdown(wait=True)

        # Or we can simply fall off the end of the scope, effectively calling
        # Broker.shutdown(), which causes all children to die as part of
        # shutdown.


# The child module importer detects the execution guard below and removes any
# code appearing after it, and refuses to execute "__main__" if it is absent.
# This is necessary to prevent a common problem where people try to call
# functions defined in __main__ without first wrapping it up to be importable
# as a module, which previously hung the target, or caused bizarre recursive
# script runs.
if __name__ == '__main__':
    main()
