
Mitogen Compared To
-------------------

This provides a little free-text summary of conceptual differences between
Mitogen and other tools, along with some basic perceptual metrics (project
maturity/age, quality of tests, function matrix)


Ansible
#######

Ansible is a complete provisioning system, Mitogen is a small component of such a system.

You should use Ansible if ...

You should not use Ansible if ...


Baker
#####

http://bitbucket.org/mchaput/baker


Chopsticks
##########

also supports recursion! but the recursively executed instance has no special knowledge of its identity in a tree structure, and little support for functions running in the master to directly invoke functions in a recursive context.. effectively each recursion produces a new master, from which function calls must be made.

executing functions from __main__ entails picking just that function and deps
out of the main module, not transferring the module intact. that approach works
but it's much messier than just arranging for __main__ to be imported and
executed through the import mechanism.

supports sudo but no support for require_tty or typing a sudo password. also supports SSH and Docker.

good set of tests

real PEP-302 module loader, but doesn't try to cope with master also relying on
a PEP-302 module loader (e.g. py2exe).

unclear which versions of Python are supported, requires at least Python2.6
(from __future__ import print_function). Unspecified versions of 3 are
supported.

I/O multiplexer in the master, but not in children.

as with Execnet it includes its own serialization.

design is reminiscent of Mitogen in places (Tunnel is practically identical to
Mitogen's Stream), and closer to Execnet elsewhere (lack of uniformity,
tendency to prefer logic expressed in if/else special case soup rather than the
type system, though some of that is due to supporting Python 3, so not judging
too harshly!)

You should use Chopsticks if you need Python 3 support.


Execnet
#######

- Parent and children may use threads, gevent, or eventlet, Mitogen only supports threads.
- No recursion
- Similar Channel abstraction but better developed.. includes waiting for remote to close its end
- Heavier emphasis on passing chunks of Python source code around, modules are loaded one-at-a-time with no dependency resolution mechanism
- Built-in unidirectional rsync-alike, compared to Mitogen's SSH emulation which allows use of real rsync in any supported mode
- no support for sudo, but supports connecting to vagrant
- works with read-only filesystem
- includes its own serialization independent of the standard library, Mitogen uses cPickle.

You should use Execnet if you value code maturity more than featureset.


Fabric
######

allows execution of shell snippets on remote machines, Python functions run
locally, any remote interaction is fundamentally done via shell, with all the
limitations that entails. prefers to depend on SSH features (e.g. tunnelling)
than reinvent them

You should use Fabric if you enjoy being woken at 4am to pages about broken
shell snippets.


Invoke
######

http://www.pyinvoke.org/

Python 2.6+, 3.3+

Basically a Fabric-alike



Paver
#####

https://github.com/paver/paver/

More or less another task execution framework / make-alike, doesn't really deal
with remote execution at all.


Plumbum
#######

https://pypi.python.org/pypi/plumbum

Shell-only

Basically syntax sugar for running shell commands. Nicer than raw shell
(depending on your opinions of operating overloading), but it's still shell.


Pyro4
#####

...


RPyC
####

- supports transparent object proxies similar to Pyro (with all the pain and suffering hidden network IO entails)
- significantly more 'frameworkey' feel
- runs multiplexer in a thread too?
- bootstrap over SSH only, no recursion and no sudo
- requires a writable filesystem



To Salt
#######

- no crappy deps

You should use Salt if you enjoy firefighting endless implementation bugs,
otherwise you should prefer Ansible.

