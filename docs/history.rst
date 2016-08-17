
History And Future
==================


History
#######

The first version of econtext was written in late 2006 for use in an
infrastructure management program, however at the time I lacked the pragmatism
necessary for pushing my little design from concept to finished implementation.
I tired of it when no way could be found to unify every communication style
(*blocking execute function, asynchronous execute function, proxy
slave-of-slave context*) into one neat abstraction. That unification never
happened, but I'm no longer worried by it.

Every few years I would pick through the source code, especially after periods
of commercial work involving some contemporary infrastructure management
systems, none of which had nearly as neat an approach to running Python code
remotely, and suffered from shockingly beginner-level bugs such as failing to
report SSH diagnostic messages.

And every few years I'd put that code down again, especially since moving to an
OS X laptop where :py:func:`select.poll` was not available, the struggle to get
back on top seemed more hassle than it was worth.

That changed in 2016 during a quiet evening at home with a clear head and
nothing better to do, after a full day of exposure to Ansible's intensely
unbearable tendency to make running a 50 line Python script across a 1Gbit/sec
LAN feel like I were configuring a host on Mars. Poking through Ansible, I was
shocked to discover it writing temporary files everywhere, and uploading a
56KiB zip file apparently for every playbook step.

.. figure:: _static/wtf.gif

    All contemporary Devops tooling

Searching around for something to play with, I came across my forgotten
``src/econtext`` directory and somehow in a few hours managed to squash most of
the race conditions and logic bugs that were preventing reliable operation,
write the IO and log forwarders, rewrite the module importer, move from
:py:func:`select.poll` to :py:func:`select.select`, and even refactor the
special cases out of the main loop.

So there you have it. As of writing :py:mod:`econtext.core` consists of 528
source lines, and those 528 lines have taken me almost a decade to write. I
have long had a preference for avoiding infrastructure work commercially, not
least for the inescapable depression induced by considering the wasted effort
across the world caused by universally horrific tooling. This is my small
contribution to a solution, I hope you find it useful.


Future
######

* Connect back using TCP and SSL.
* Python 3 support.
* Windows support via psexec or similar.
* Investigate cPickle safety and potentially replace it, or implement a strict
  format validator for messages received by master.
* Predictive import: reduce roundtrips by pipelining modules observed to
  probably be requested in future.
* Provide a means for waiting on multiple
  :py:class:`Channels <econtext.core.Channel>`.
* Comprehensive integration tests.
* Make pickler deliver a CallError to the intended recipient when a type is
  rejected during unpickling.
