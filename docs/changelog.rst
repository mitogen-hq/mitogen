
.. _changelog:

Release Notes
=============


.. raw:: html

    <style>
        div#release-notes h2 {
            border-bottom: 1px dotted #c0c0c0;
            margin-top: 50px !important;
        }
    </style>


v0.2.8 (unreleased)
-------------------

To avail of fixes in an unreleased version, please download a ZIP file
`directly from GitHub <https://github.com/dw/mitogen/>`_.


v0.2.7 (2019-05-19)
-------------------

This release primarily exists to add a descriptive error message when running
on Ansible 2.8, which is not yet supported.

Fixes
~~~~~

* `#557 <https://github.com/dw/mitogen/issues/557>`_: fix a crash when running
  on machines with high CPU counts.

* `#570 <https://github.com/dw/mitogen/issues/570>`_: the ``firewalld`` module
  internally caches a dbus name that changes across ``firewalld`` restarts,
  causing a failure if the service is restarted between ``firewalld`` module invocations.

* `#575 <https://github.com/dw/mitogen/issues/575>`_: fix a crash when
  rendering an error message to indicate no usable temporary directories could
  be found.

* `#576 <https://github.com/dw/mitogen/issues/576>`_: fix a crash during
  startup on SuSE Linux 11, due to an incorrect version compatibility check in
  the Mitogen code.

* `#581 <https://github.com/dw/mitogen/issues/58>`_: a
  ``mitogen_mask_remote_name`` Ansible variable is exposed, to allow masking
  the username, hostname and process ID of ``ansible-playbook`` running on the
  controller machine.

* `#587 <https://github.com/dw/mitogen/issues/587>`_: display a friendly
  message when running on an unsupported version of Ansible, to cope with
  potential influx of 2.8-related bug reports.


Thanks!
~~~~~~~

Mitogen would not be possible without the support of users. A huge thanks for
bug reports, testing, features and fixes in this release contributed by
`Orion Poplawski <https://github.com/opoplawski>`_,
`Thibaut Barrère <https://github.com/thbar>`_,
`@Moumoutaru <https://github.com/Moumoutaru>`_, and
`@polski-g <https://github.com/polski-g>`_.


v0.2.6 (2019-03-06)
-------------------

Fixes
~~~~~

* `#542 <https://github.com/dw/mitogen/issues/542>`_: some versions of OS X
  ship a default Python that does not support :func:`select.poll`. Restore the
  0.2.3 behaviour of defaulting to Kqueue in this case, but still prefer
  :func:`select.poll` if it is available.

* `#545 <https://github.com/dw/mitogen/issues/545>`_: an optimization
  introduced in `#493 <https://github.com/dw/mitogen/issues/493>`_ caused a
  64-bit integer to be assigned to a 32-bit field on ARM 32-bit targets,
  causing runs to fail.

* `#548 <https://github.com/dw/mitogen/issues/548>`_: `mitogen_via=` could fail
  when the selected transport was set to ``smart``.

* `#550 <https://github.com/dw/mitogen/issues/550>`_: avoid some broken
  TTY-related `ioctl()` calls on Windows Subsystem for Linux 2016 Anniversary
  Update.

* `#554 <https://github.com/dw/mitogen/issues/554>`_: third party Ansible
  action plug-ins that invoked :func:`_make_tmp_path` repeatedly could trigger
  an assertion failure.

* `#555 <https://github.com/dw/mitogen/issues/555>`_: work around an old idiom
  that reloaded :mod:`sys` in order to change the interpreter's default encoding.

* `ffae0355 <https://github.com/dw/mitogen/commit/ffae0355>`_: needless
  information was removed from the documentation and installation procedure.


Core Library
~~~~~~~~~~~~

* `#535 <https://github.com/dw/mitogen/issues/535>`_: to support function calls
  on a service pool from another thread, :class:`mitogen.select.Select`
  additionally permits waiting on :class:`mitogen.core.Latch`.

* `#535 <https://github.com/dw/mitogen/issues/535>`_:
  :class:`mitogen.service.Pool.defer` allows any function to be enqueued for
  the thread pool from another thread.

* `#535 <https://github.com/dw/mitogen/issues/535>`_: a new
  :mod:`mitogen.os_fork` module provides a :func:`os.fork` wrapper that pauses
  thread activity during fork. On Python<2.6, :class:`mitogen.core.Broker` and
  :class:`mitogen.service.Pool` automatically record their existence so that a
  :func:`os.fork` monkey-patch can automatically pause them for any attempt to
  start a subprocess.

* `ca63c26e <https://github.com/dw/mitogen/commit/ca63c26e>`_:
  :meth:`mitogen.core.Latch.put`'s `obj` argument was made optional.


Thanks!
~~~~~~~

Mitogen would not be possible without the support of users. A huge thanks for
bug reports, testing, features and fixes in this release contributed by
`Fabian Arrotin <https://github.com/arrfab>`_,
`Giles Westwood <https://github.com/gilesw>`_,
`Matt Layman <https://github.com/mblayman>`_,
`Percy Grunwald <https://github.com/percygrunwald>`_,
`Petr Enkov <https://github.com/enkov>`_,
`Tony Finch <https://github.com/fanf2>`_,
`@elbunda <https://github.com/elbunda>`_, and
`@zyphermonkey <https://github.com/zyphermonkey>`_.


v0.2.5 (2019-02-14)
-------------------

Fixes
~~~~~

* `#511 <https://github.com/dw/mitogen/issues/511>`_,
  `#536 <https://github.com/dw/mitogen/issues/536>`_: changes in 0.2.4 to
  repair ``delegate_to`` handling broke default ``ansible_python_interpreter``
  handling. Test coverage was added.

* `#532 <https://github.com/dw/mitogen/issues/532>`_: fix a race in the service
  used to propagate Ansible modules, that could easily manifest when starting
  asynchronous tasks in a loop.

* `#536 <https://github.com/dw/mitogen/issues/536>`_: changes in 0.2.4 to
  support Python 2.4 interacted poorly with modules that imported
  ``simplejson`` from a controller that also loaded an incompatible newer
  version of ``simplejson``.

* `#537 <https://github.com/dw/mitogen/issues/537>`_: a swapped operator in the
  CPU affinity logic meant 2 cores were reserved on 1<n<4 core machines, rather
  than 1 core as desired. Test coverage was added.

* `#538 <https://github.com/dw/mitogen/issues/538>`_: the source distribution
  includes a ``LICENSE`` file.

* `#539 <https://github.com/dw/mitogen/issues/539>`_: log output is no longer
  duplicated when the Ansible ``log_path`` setting is enabled.

* `#540 <https://github.com/dw/mitogen/issues/540>`_: the ``stderr`` stream of
  async module invocations was previously discarded.

* `#541 <https://github.com/dw/mitogen/issues/541>`_: Python error logs
  originating from the ``boto`` package are quiesced, and only appear in
  ``-vvv`` output. This is since EC2 modules may trigger errors during normal
  operation, when retrying transiently failing requests.

* `748f5f67 <https://github.com/dw/mitogen/commit/748f5f67>`_,
  `21ad299d <https://github.com/dw/mitogen/commit/21ad299d>`_,
  `8ae6ca1d <https://github.com/dw/mitogen/commit/8ae6ca1d>`_,
  `7fd0d349 <https://github.com/dw/mitogen/commit/7fd0d349>`_:
  the ``ansible_ssh_host``, ``ansible_ssh_user``, ``ansible_user``,
  ``ansible_become_method``, and ``ansible_ssh_port`` variables more correctly
  match typical behaviour when ``mitogen_via=`` is active.

* `2a8567b4 <https://github.com/dw/mitogen/commit/2a8567b4>`_: fix a race
  initializing a child's service thread pool on Python 3.4+, due to a change in
  locking scheme used by the Python import mechanism.


Thanks!
~~~~~~~

Mitogen would not be possible without the support of users. A huge thanks for
bug reports, testing, features and fixes in this release contributed by
`Carl George <https://github.com/carlwgeorge>`_,
`Guy Knights <https://github.com/knightsg>`_, and
`Josh Smift <https://github.com/jbscare>`_.


v0.2.4 (2019-02-10)
-------------------

Mitogen for Ansible
~~~~~~~~~~~~~~~~~~~

This release includes a huge variety of important fixes and new optimizations.
It is 35% faster than 0.2.3 on a synthetic 64 target run that places heavy load
on the connection multiplexer.

Enhancements
^^^^^^^^^^^^

* `#76 <https://github.com/dw/mitogen/issues/76>`_,
  `#351 <https://github.com/dw/mitogen/issues/351>`_,
  `#352 <https://github.com/dw/mitogen/issues/352>`_: disconnect propagation
  has improved, allowing Ansible to cancel waits for responses from abruptly
  disconnected targets. This ensures a task will reliably fail rather than
  hang, for example on network failure or EC2 instance maintenance.

* `#369 <https://github.com/dw/mitogen/issues/369>`_,
  `#407 <https://github.com/dw/mitogen/issues/407>`_: :meth:`Connection.reset`
  is implemented, allowing `meta: reset_connection
  <https://docs.ansible.com/ansible/latest/modules/meta_module.html>`_ to shut
  down the remote interpreter as documented, and improving support for the
  `reboot
  <https://docs.ansible.com/ansible/latest/modules/reboot_module.html>`_
  module.

* `09aa27a6 <https://github.com/dw/mitogen/commit/09aa27a6>`_: the
  ``mitogen_host_pinned`` strategy wraps the ``host_pinned`` strategy
  introduced in Ansible 2.7.

* `#477 <https://github.com/dw/mitogen/issues/477>`_: Python 2.4 is fully
  supported by the core library and tested automatically, in any parent/child
  combination of 2.4, 2.6, 2.7 and 3.6 interpreters.

* `#477 <https://github.com/dw/mitogen/issues/477>`_: Ansible 2.3 is fully
  supported and tested automatically. In combination with the core library
  Python 2.4 support, this allows Red Hat Enterprise Linux 5 targets to be
  managed with Mitogen. The ``simplejson`` package need not be installed on
  such targets, as is usually required by Ansible.

* `#412 <https://github.com/dw/mitogen/issues/412>`_: to simplify diagnosing
  connection configuration problems, Mitogen ships a ``mitogen_get_stack``
  action that is automatically added to the action plug-in path. See
  :ref:`mitogen-get-stack` for more information.

* `152effc2 <https://github.com/dw/mitogen/commit/152effc2>`_,
  `bd4b04ae <https://github.com/dw/mitogen/commit/bd4b04ae>`_: a CPU affinity
  policy was added for Linux controllers, reducing latency and SMP overhead on
  hot paths exercised for every task. This yielded a 19% speedup in a 64-target
  job composed of many short tasks, and should easily be visible as a runtime
  improvement in many-host runs.

* `2b44d598 <https://github.com/dw/mitogen/commit/2b44d598>`_: work around a
  defective caching mechanism by pre-heating it before spawning workers. This
  saves 40% runtime on a synthetic repetitive task.

* `0979422a <https://github.com/dw/mitogen/commit/0979422a>`_: an expensive
  dependency scanning step was redundantly invoked for every task,
  bottlenecking the connection multiplexer.

* `eaa990a97 <https://github.com/dw/mitogen/commit/eaa990a97>`_: a new
  ``mitogen_ssh_compression`` variable is supported, allowing Mitogen's default
  SSH compression to be disabled. SSH compression is a large contributor to CPU
  usage in many-target runs, and severely limits file transfer. On a `"shell:
  hostname"` task repeated 500 times, Mitogen requires around 800 bytes per
  task with compression, rising to 3 KiB without. File transfer throughput
  rises from ~25MiB/s when enabled to ~200MiB/s when disabled.

* `#260 <https://github.com/dw/mitogen/issues/260>`_,
  `a18a083c <https://github.com/dw/mitogen/commit/a18a083c>`_: brokers no
  longer wait for readiness indication to transmit, and instead assume
  transmission will succeed. As this is usually true, one loop iteration and
  two poller reconfigurations are avoided, yielding a significant reduction in
  interprocess round-trip latency.

* `#415 <https://github.com/dw/mitogen/issues/415>`_,
  `#491 <https://github.com/dw/mitogen/issues/491>`_,
  `#493 <https://github.com/dw/mitogen/issues/493>`_: the interface employed
  for in-process queues changed from `kqueue
  <https://www.freebsd.org/cgi/man.cgi?query=kqueue&sektion=2>`_ / `epoll
  <http://man7.org/linux/man-pages/man7/epoll.7.html>`_ to `poll()
  <http://man7.org/linux/man-pages/man2/poll.2.html>`_, which requires no setup
  or teardown, yielding a 38% latency reduction for inter-thread communication.


Fixes
^^^^^

* `#251 <https://github.com/dw/mitogen/issues/251>`_,
  `#359 <https://github.com/dw/mitogen/issues/359>`_,
  `#396 <https://github.com/dw/mitogen/issues/396>`_,
  `#401 <https://github.com/dw/mitogen/issues/401>`_,
  `#404 <https://github.com/dw/mitogen/issues/404>`_,
  `#412 <https://github.com/dw/mitogen/issues/412>`_,
  `#434 <https://github.com/dw/mitogen/issues/434>`_,
  `#436 <https://github.com/dw/mitogen/issues/436>`_,
  `#465 <https://github.com/dw/mitogen/issues/465>`_: connection delegation and
  ``delegate_to:`` handling suffered a major regression in 0.2.3. The 0.2.2
  behaviour has been restored, and further work has been made to improve the
  compatibility of connection delegation's configuration building methods.

* `#323 <https://github.com/dw/mitogen/issues/323>`_,
  `#333 <https://github.com/dw/mitogen/issues/333>`_: work around a Windows
  Subsystem for Linux bug that caused tracebacks to appear during shutdown.

* `#334 <https://github.com/dw/mitogen/issues/334>`_: the SSH method
  tilde-expands private key paths using Ansible's logic. Previously the path
  was passed unmodified to SSH, which expanded it using :func:`pwd.getpwnam`.
  This differs from :func:`os.path.expanduser`, which uses the ``HOME``
  environment variable if it is set, causing behaviour to diverge when Ansible
  was invoked across user accounts via ``sudo``.

* `#364 <https://github.com/dw/mitogen/issues/364>`_: file transfers from
  controllers running Python 2.7.2 or earlier could be interrupted due to a
  forking bug in the :mod:`tempfile` module.

* `#370 <https://github.com/dw/mitogen/issues/370>`_: the Ansible
  `reboot <https://docs.ansible.com/ansible/latest/modules/reboot_module.html>`_
  module is supported.

* `#373 <https://github.com/dw/mitogen/issues/373>`_: the LXC and LXD methods
  print a useful hint on failure, as no useful error is normally logged to the
  console by these tools.

* `#374 <https://github.com/dw/mitogen/issues/374>`_,
  `#391 <https://github.com/dw/mitogen/issues/391>`_: file transfer and module
  execution from 2.x controllers to 3.x targets was broken due to a regression
  caused by refactoring, and compounded by `#426
  <https://github.com/dw/mitogen/issues/426>`_.

* `#400 <https://github.com/dw/mitogen/issues/400>`_: work around a threading
  bug in the AWX display callback when running with high verbosity setting.

* `#409 <https://github.com/dw/mitogen/issues/409>`_: the setns method was
  silently broken due to missing tests. Basic coverage was added to prevent a
  recurrence.

* `#409 <https://github.com/dw/mitogen/issues/409>`_: the LXC and LXD methods
  support ``mitogen_lxc_path`` and ``mitogen_lxc_attach_path`` variables to
  control the location of third pary utilities.

* `#410 <https://github.com/dw/mitogen/issues/410>`_: the sudo method supports
  the SELinux ``--type`` and ``--role`` options.

* `#420 <https://github.com/dw/mitogen/issues/420>`_: if a :class:`Connection`
  was constructed in the Ansible top-level process, for example while executing
  ``meta: reset_connection``, resources could become undesirably shared in
  subsequent children.

* `#426 <https://github.com/dw/mitogen/issues/426>`_: an oversight while
  porting to Python 3 meant no automated 2->3 tests were running. A significant
  number of 2->3 bugs were fixed, mostly in the form of Unicode/bytes
  mismatches.

* `#429 <https://github.com/dw/mitogen/issues/429>`_: the ``sudo`` method can
  now recognize internationalized password prompts.

* `#362 <https://github.com/dw/mitogen/issues/362>`_,
  `#435 <https://github.com/dw/mitogen/issues/435>`_: the previous fix for slow
  Python 2.x subprocess creation on Red Hat caused newly spawned children to
  have a reduced open files limit. A more intrusive fix has been added to
  directly address the problem without modifying the subprocess environment.

* `#397 <https://github.com/dw/mitogen/issues/397>`_,
  `#454 <https://github.com/dw/mitogen/issues/454>`_: the previous approach to
  handling modern Ansible temporary file cleanup was too aggressive, and could
  trigger early finalization of Cython-based extension modules, leading to
  segmentation faults.

* `#499 <https://github.com/dw/mitogen/issues/499>`_: the ``allow_same_user``
  Ansible configuration setting is respected.

* `#527 <https://github.com/dw/mitogen/issues/527>`_: crashes in modules are
  trapped and reported in a manner that matches Ansible. In particular, a
  module crash no longer leads to an exception that may crash the corresponding
  action plug-in.

* `dc1d4251 <https://github.com/dw/mitogen/commit/dc1d4251>`_: the
  ``synchronize`` module could fail with the Docker transport due to a missing
  attribute.

* `599da068 <https://github.com/dw/mitogen/commit/599da068>`_: fix a race
  when starting async tasks, where it was possible for the controller to
  observe no status file on disk before the task had a chance to write one.

* `2c7af9f04 <https://github.com/dw/mitogen/commit/2c7af9f04>`_: Ansible
  modules were repeatedly re-transferred. The bug was hidden by the previously
  mandatorily enabled SSH compression.


Core Library
~~~~~~~~~~~~

* `#76 <https://github.com/dw/mitogen/issues/76>`_: routing records the
  destination context IDs ever received on each stream, and when disconnection
  occurs, propagates :data:`mitogen.core.DEL_ROUTE` messages towards every
  stream that ever communicated with the disappearing peer, rather than simply
  towards parents. Conversations between nodes anywhere in the tree receive
  :data:`mitogen.core.DEL_ROUTE` when either participant disconnects, allowing
  receivers to wake with :class:`mitogen.core.ChannelError`, even when one
  participant is not a parent of the other.

* `#109 <https://github.com/dw/mitogen/issues/109>`_,
  `57504ba6 <https://github.com/dw/mitogen/commit/57504ba6>`_: newer Python 3
  releases explicitly populate :data:`sys.meta_path` with importer internals,
  causing Mitogen to install itself at the end of the importer chain rather
  than the front.

* `#310 <https://github.com/dw/mitogen/issues/310>`_: support has returned for
  trying to figure out the real source of non-module objects installed in
  :data:`sys.modules`, so they can be imported. This is needed to handle syntax
  sugar used by packages like :mod:`plumbum`.

* `#349 <https://github.com/dw/mitogen/issues/349>`_: an incorrect format
  string could cause large stack traces when attempting to import built-in
  modules on Python 3.

* `#387 <https://github.com/dw/mitogen/issues/387>`_,
  `#413 <https://github.com/dw/mitogen/issues/413>`_: dead messages include an
  optional reason in their body. This is used to cause
  :class:`mitogen.core.ChannelError` to report far more useful diagnostics at
  the point the error occurs that previously would have been buried in debug
  log output from an unrelated context.

* `#408 <https://github.com/dw/mitogen/issues/408>`_: a variety of fixes were
  made to restore Python 2.4 compatibility.

* `#399 <https://github.com/dw/mitogen/issues/399>`_,
  `#437 <https://github.com/dw/mitogen/issues/437>`_: ignore a
  :class:`DeprecationWarning` to avoid failure of the ``su`` method on Python
  3.7.

* `#405 <https://github.com/dw/mitogen/issues/405>`_: if an oversized message
  is rejected, and it has a ``reply_to`` set, a dead message is returned to the
  sender. This ensures function calls exceeding the configured maximum size
  crash rather than hang.

* `#406 <https://github.com/dw/mitogen/issues/406>`_:
  :class:`mitogen.core.Broker` did not call :meth:`mitogen.core.Poller.close`
  during shutdown, leaking the underlying poller FD in masters and parents.

* `#406 <https://github.com/dw/mitogen/issues/406>`_: connections could leak
  FDs when a child process failed to start.

* `#288 <https://github.com/dw/mitogen/issues/288>`_,
  `#406 <https://github.com/dw/mitogen/issues/406>`_,
  `#417 <https://github.com/dw/mitogen/issues/417>`_: connections could leave
  FD wrapper objects that had not been closed lying around to be closed during
  garbage collection, causing reused FD numbers to be closed at random moments.

* `#411 <https://github.com/dw/mitogen/issues/411>`_: the SSH method typed
  "``y``" rather than the requisite "``yes``" when `check_host_keys="accept"`
  was configured. This would lead to connection timeouts due to the hung
  response.

* `#414 <https://github.com/dw/mitogen/issues/414>`_,
  `#425 <https://github.com/dw/mitogen/issues/425>`_: avoid deadlock of forked
  children by reinitializing the :mod:`mitogen.service` pool lock.

* `#416 <https://github.com/dw/mitogen/issues/416>`_: around 1.4KiB of memory
  was leaked on every RPC, due to a list of strong references keeping alive any
  handler ever registered for disconnect notification.

* `#418 <https://github.com/dw/mitogen/issues/418>`_: the
  :func:`mitogen.parent.iter_read` helper would leak poller FDs, because
  execution of its :keyword:`finally` block was delayed on Python 3. Now
  callers explicitly close the generator when finished.

* `#422 <https://github.com/dw/mitogen/issues/422>`_: the fork method could
  fail to start if :data:`sys.stdout` was opened in block buffered mode, and
  buffered data was pending in the parent prior to fork.

* `#438 <https://github.com/dw/mitogen/issues/438>`_: a descriptive error is
  logged when stream corruption is detected.

* `#439 <https://github.com/dw/mitogen/issues/439>`_: descriptive errors are
  raised when attempting to invoke unsupported function types.

* `#444 <https://github.com/dw/mitogen/issues/444>`_: messages regarding
  unforwardable extension module are no longer logged as errors.

* `#445 <https://github.com/dw/mitogen/issues/445>`_: service pools unregister
  the :data:`mitogen.core.CALL_SERVICE` handle at shutdown, ensuring any
  outstanding messages are either processed by the pool as it shuts down, or
  have dead messages sent in reply to them, preventing peer contexts from
  hanging due to a forgotten buffered message.

* `#446 <https://github.com/dw/mitogen/issues/446>`_: given thread A calling
  :meth:`mitogen.core.Receiver.close`, and thread B, C, and D sleeping in
  :meth:`mitogen.core.Receiver.get`, previously only one sleeping thread would
  be woken with :class:`mitogen.core.ChannelError` when the receiver was
  closed. Now all threads are woken per the docstring.

* `#447 <https://github.com/dw/mitogen/issues/447>`_: duplicate attempts to
  invoke :meth:`mitogen.core.Router.add_handler` cause an error to be raised,
  ensuring accidental re-registration of service pools are reported correctly.

* `#448 <https://github.com/dw/mitogen/issues/448>`_: the import hook
  implementation now raises :class:`ModuleNotFoundError` instead of
  :class:`ImportError` in Python 3.6 and above, to cope with an upcoming
  version of the :mod:`subprocess` module requiring this new subclass to be
  raised.

* `#453 <https://github.com/dw/mitogen/issues/453>`_: the loggers used in
  children for standard IO redirection have propagation disabled, preventing
  accidental reconfiguration of the :mod:`logging` package in a child from
  setting up a feedback loop.

* `#456 <https://github.com/dw/mitogen/issues/456>`_: a descriptive error is
  logged when :meth:`mitogen.core.Broker.defer` is called after the broker has
  shut down, preventing new messages being enqueued that will never be sent,
  and subsequently producing a program hang.

* `#459 <https://github.com/dw/mitogen/issues/459>`_: the beginnings of a
  :meth:`mitogen.master.Router.get_stats` call has been added. The initial
  statistics cover the module loader only.

* `#462 <https://github.com/dw/mitogen/issues/462>`_: Mitogen could fail to
  open a PTY on broken Linux systems due to a bad interaction between the glibc
  :func:`grantpt` function and an incorrectly mounted ``/dev/pts`` filesystem.
  Since correct group ownership is not required in most scenarios, when this
  problem is detected, the PTY is allocated and opened directly by the library.

* `#479 <https://github.com/dw/mitogen/issues/479>`_: Mitogen could fail to
  import :mod:`__main__` on Python 3.4 and newer due to a breaking change in
  the :mod:`pkgutil` API. The program's main script is now handled specially.

* `#481 <https://github.com/dw/mitogen/issues/481>`_: the version of `sudo`
  that shipped with CentOS 5 replaced itself with the program to be executed,
  and therefore did not hold any child PTY open on our behalf. The child
  context is updated to preserve any PTY FD in order to avoid the kernel
  sending `SIGHUP` early during startup.

* `#523 <https://github.com/dw/mitogen/issues/523>`_: the test suite didn't
  generate a code coverage report if any test failed.

* `#524 <https://github.com/dw/mitogen/issues/524>`_: Python 3.6+ emitted a
  :class:`DeprecationWarning` for :func:`mitogen.utils.run_with_router`.

* `#529 <https://github.com/dw/mitogen/issues/529>`_: Code coverage of the
  test suite was not measured across all Python versions.

* `16ca111e <https://github.com/dw/mitogen/commit/16ca111e>`_: handle OpenSSH
  7.5 permission denied prompts when ``~/.ssh/config`` rewrites are present.

* `9ec360c2 <https://github.com/dw/mitogen/commit/9ec360c2>`_: a new
  :meth:`mitogen.core.Broker.defer_sync` utility function is provided.

* `f20e0bba <https://github.com/dw/mitogen/commit/f20e0bba>`_:
  :meth:`mitogen.service.FileService.register_prefix` permits granting
  unprivileged access to whole filesystem subtrees, rather than single files at
  a time.

* `8f85ee03 <https://github.com/dw/mitogen/commit/8f85ee03>`_:
  :meth:`mitogen.core.Router.myself` returns a :class:`mitogen.core.Context`
  referring to the current process.

* `824c7931 <https://github.com/dw/mitogen/commit/824c7931>`_: exceptions
  raised by the import hook were updated to include probable reasons for
  a failure.

* `57b652ed <https://github.com/dw/mitogen/commit/57b652ed>`_: a stray import
  meant an extra roundtrip and ~4KiB of data was wasted for any context that
  imported :mod:`mitogen.parent`.


Thanks!
~~~~~~~

Mitogen would not be possible without the support of users. A huge thanks for
bug reports, testing, features and fixes in this release contributed by
`Alex Willmer <https://github.com/moreati>`_,
`Andreas Krüger <https://github.com/woopstar>`_,
`Anton Stroganov <https://github.com/Aeon>`_,
`Berend De Schouwer <https://github.com/berenddeschouwer>`_,
`Brian Candler <https://github.com/candlerb>`_,
`dsgnr <https://github.com/dsgnr>`_,
`Duane Zamrok <https://github.com/dewthefifth>`_,
`Eric Chang <https://github.com/changchichung>`_,
`Gerben Meijer <https://github.com/infernix>`_,
`Guy Knights <https://github.com/knightsg>`_,
`Jesse London <https://github.com/jesteria>`_,
`Jiří Vávra <https://github.com/Houbovo>`_,
`Johan Beisser <https://github.com/jbeisser>`_,
`Jonathan Rosser <https://github.com/jrosser>`_,
`Josh Smift <https://github.com/jbscare>`_,
`Kevin Carter <https://github.com/cloudnull>`_,
`Mehdi <https://github.com/mehdisat7>`_,
`Michael DeHaan <https://github.com/mpdehaan>`_,
`Michal Medvecky <https://github.com/michalmedvecky>`_,
`Mohammed Naser <https://github.com/mnaser/>`_,
`Peter V. Saveliev <https://github.com/svinota/>`_,
`Pieter Avonts <https://github.com/pieteravonts/>`_,
`Ross Williams <https://github.com/overhacked/>`_,
`Sergey <https://github.com/LuckySB/>`_,
`Stéphane <https://github.com/sboisson/>`_,
`Strahinja Kustudic <https://github.com/kustodian>`_,
`Tom Parker-Shemilt <https://github.com/palfrey/>`_,
`Younès HAFRI <https://github.com/yhafri>`_,
`@killua-eu <https://github.com/killua-eu>`_,
`@myssa91 <https://github.com/myssa91>`_,
`@ohmer1 <https://github.com/ohmer1>`_,
`@s3c70r <https://github.com/s3c70r/>`_,
`@syntonym <https://github.com/syntonym/>`_,
`@trim777 <https://github.com/trim777/>`_,
`@whky <https://github.com/whky/>`_, and
`@yodatak <https://github.com/yodatak/>`_.


v0.2.3 (2018-10-23)
-------------------

Mitogen for Ansible
~~~~~~~~~~~~~~~~~~~

Enhancements
^^^^^^^^^^^^

* `#315 <https://github.com/dw/mitogen/pull/315>`_,
  `#392 <https://github.com/dw/mitogen/issues/392>`_: Ansible 2.6 and 2.7 are
  supported.

* `#321 <https://github.com/dw/mitogen/issues/321>`_,
  `#336 <https://github.com/dw/mitogen/issues/336>`_: temporary file handling
  was simplified, undoing earlier damage caused by compatibility fixes,
  improving 2.6 compatibility, and avoiding two network roundtrips for every
  related action
  (`assemble <http://docs.ansible.com/ansible/latest/modules/assemble_module.html>`_,
  `aws_s3 <http://docs.ansible.com/ansible/latest/modules/aws_s3_module.html>`_,
  `copy <http://docs.ansible.com/ansible/latest/modules/copy_module.html>`_,
  `patch <http://docs.ansible.com/ansible/latest/modules/patch_module.html>`_,
  `script <http://docs.ansible.com/ansible/latest/modules/script_module.html>`_,
  `template <http://docs.ansible.com/ansible/latest/modules/template_module.html>`_,
  `unarchive <http://docs.ansible.com/ansible/latest/modules/unarchive_module.html>`_,
  `uri <http://docs.ansible.com/ansible/latest/modules/uri_module.html>`_). See
  :ref:`ansible_tempfiles` for a complete description.

* `#376 <https://github.com/dw/mitogen/pull/376>`_,
  `#377 <https://github.com/dw/mitogen/pull/377>`_: the ``kubectl`` connection
  type is now supported. Contributed by Yannig Perré.

* `084c0ac0 <https://github.com/dw/mitogen/commit/084c0ac0>`_: avoid a
  roundtrip in
  `copy <http://docs.ansible.com/ansible/latest/modules/copy_module.html>`_ and
  `template <http://docs.ansible.com/ansible/latest/modules/template_module.html>`_
  due to an unfortunate default.

* `7458dfae <https://github.com/dw/mitogen/commit/7458dfae>`_: avoid a
  roundtrip when transferring files smaller than 124KiB. Copy and template
  actions are now 2-RTT, reducing runtime for a 20-iteration template loop over
  a 250 ms link from 30 seconds to 10 seconds compared to v0.2.2, down from 120
  seconds compared to vanilla.

* `#337 <https://github.com/dw/mitogen/issues/337>`_: To avoid a scaling
  limitation, a PTY is no longer allocated for an SSH connection unless the
  configuration specifies a password.

* `d62e6e2a <https://github.com/dw/mitogen/commit/d62e6e2a>`_: many-target
  runs executed the dependency scanner redundantly due to missing
  synchronization, wasting significant runtime in the connection multiplexer.
  In one case work was reduced by 95%, which may manifest as faster runs.

* `5189408e <https://github.com/dw/mitogen/commit/5189408e>`_: threads are
  cooperatively scheduled, minimizing `GIL
  <https://en.wikipedia.org/wiki/Global_interpreter_lock>`_ contention, and
  reducing context switching by around 90%. This manifests as an overall
  improvement, but is easily noticeable on short many-target runs, where
  startup overhead dominates runtime.

* The `faulthandler <https://faulthandler.readthedocs.io/>`_ module is
  automatically activated if it is installed, simplifying debugging of hangs.
  See :ref:`diagnosing-hangs` for details.

* The ``MITOGEN_DUMP_THREAD_STACKS`` environment variable's value now indicates
  the number of seconds between stack dumps. See :ref:`diagnosing-hangs` for
  details.


Fixes
^^^^^

* `#251 <https://github.com/dw/mitogen/issues/251>`_,
  `#340 <https://github.com/dw/mitogen/issues/340>`_: Connection Delegation
  could establish connections to the wrong target when ``delegate_to:`` is
  present.

* `#291 <https://github.com/dw/mitogen/issues/291>`_: when Mitogen had
  previously been installed using ``pip`` or ``setuptools``, the globally
  installed version could conflict with a newer version bundled with an
  extension that had been installed using the documented steps. Now the bundled
  library always overrides over any system-installed copy.

* `#324 <https://github.com/dw/mitogen/issues/324>`_: plays with a
  `custom module_utils <https://docs.ansible.com/ansible/latest/reference_appendices/config.html#default-module-utils-path>`_
  would fail due to fallout from the Python 3 port and related tests being
  disabled.

* `#331 <https://github.com/dw/mitogen/issues/331>`_: the connection
  multiplexer subprocess always exits before the main Ansible process, ensuring
  logs generated by it do not overwrite the user's prompt when ``-vvv`` is
  enabled.

* `#332 <https://github.com/dw/mitogen/issues/332>`_: support a new
  :func:`sys.excepthook`-based module exit mechanism added in Ansible 2.6.

* `#338 <https://github.com/dw/mitogen/issues/338>`_: compatibility: changes to
  ``/etc/environment`` and ``~/.pam_environment`` made by a task are reflected
  in the runtime environment of subsequent tasks. See
  :ref:`ansible_process_env` for a complete description.

* `#343 <https://github.com/dw/mitogen/issues/343>`_: the sudo ``--login``
  option is supported.

* `#344 <https://github.com/dw/mitogen/issues/344>`_: connections no longer
  fail when the controller's login username contains slashes.

* `#345 <https://github.com/dw/mitogen/issues/345>`_: the ``IdentitiesOnly
  yes`` option is no longer supplied to OpenSSH by default, better matching
  Ansible's behaviour.

* `#355 <https://github.com/dw/mitogen/issues/355>`_: tasks configured to run
  in an isolated forked subprocess were forked from the wrong parent context.
  This meant built-in modules overridden via a custom ``module_utils`` search
  path may not have had any effect.

* `#362 <https://github.com/dw/mitogen/issues/362>`_: to work around a slow
  algorithm in the :mod:`subprocess` module, the maximum number of open files
  in processes running on the target is capped to 512, reducing the work
  required to start a subprocess by >2000x in default CentOS configurations.

* `#397 <https://github.com/dw/mitogen/issues/397>`_: recent Mitogen master
  versions could fail to clean up temporary directories in a number of
  circumstances, and newer Ansibles moved to using :mod:`atexit` to effect
  temporary directory cleanup in some circumstances.

* `b9112a9c <https://github.com/dw/mitogen/commit/b9112a9c>`_,
  `2c287801 <https://github.com/dw/mitogen/commit/2c287801>`_: OpenSSH 7.5
  permission denied prompts are now recognized. Contributed by Alex Willmer.

* A missing check caused an exception traceback to appear when using the
  ``ansible`` command-line tool with a missing or misspelled module name.

* Ansible since >=2.7 began importing :mod:`__main__` from
  :mod:`ansible.module_utils.basic`, causing an error during execution, due to
  the controller being configured to refuse network imports outside the
  ``ansible.*`` namespace. Update the target implementation to construct a stub
  :mod:`__main__` module to satisfy the otherwise seemingly vestigial import.


Core Library
~~~~~~~~~~~~

* A new :class:`mitogen.parent.CallChain` class abstracts safe pipelining of
  related function calls to a target context, cancelling the chain if an
  exception occurs.

* `#305 <https://github.com/dw/mitogen/issues/305>`_: fix a long-standing minor
  race relating to the logging framework, where *no route for Message..*
  would frequently appear during startup.

* `#313 <https://github.com/dw/mitogen/issues/313>`_:
  :meth:`mitogen.parent.Context.call` was documented as capable of accepting
  static methods. While possible on Python 2.x the result is ugly, and in every
  case it should be trivial to replace with a classmethod. The documentation
  was fixed.

* `#337 <https://github.com/dw/mitogen/issues/337>`_: to avoid a scaling
  limitation, a PTY is no longer allocated for each OpenSSH client if it can be
  avoided. PTYs are only allocated if a password is supplied, or when
  `host_key_checking=accept`. This is since Linux has a default of 4096 PTYs
  (``kernel.pty.max``), while OS X has a default of 127 and an absolute maximum
  of 999 (``kern.tty.ptmx_max``).

* `#339 <https://github.com/dw/mitogen/issues/339>`_: the LXD connection method
  was erroneously executing LXC Classic commands.

* `#345 <https://github.com/dw/mitogen/issues/345>`_: the SSH connection method
  allows optionally disabling ``IdentitiesOnly yes``.

* `#356 <https://github.com/dw/mitogen/issues/356>`_: if the master Python
  process does not have :data:`sys.executable` set, the default Python
  interpreter used for new children on the local machine defaults to
  ``"/usr/bin/python"``.

* `#366 <https://github.com/dw/mitogen/issues/366>`_,
  `#380 <https://github.com/dw/mitogen/issues/380>`_: attempts by children to
  import :mod:`__main__` where the main program module lacks an execution guard
  are refused, and an error is logged. This prevents a common and highly
  confusing error when prototyping new scripts.

* `#371 <https://github.com/dw/mitogen/pull/371>`_: the LXC connection method
  uses a more compatible method to establish an non-interactive session.
  Contributed by Brian Candler.

* `af2ded66 <https://github.com/dw/mitogen/commit/af2ded66>`_: add
  :func:`mitogen.fork.on_fork` to allow non-Mitogen managed process forks to
  clean up Mitogen resources in the child.

* `d6784242 <https://github.com/dw/mitogen/commit/d6784242>`_: the setns method
  always resets ``HOME``, ``SHELL``, ``LOGNAME`` and ``USER`` environment
  variables to an account in the target container, defaulting to ``root``.

* `830966bf <https://github.com/dw/mitogen/commit/830966bf>`_: the UNIX
  listener no longer crashes if the peer process disappears in the middle of
  connection setup.


Thanks!
~~~~~~~

Mitogen would not be possible without the support of users. A huge thanks for
bug reports, testing, features and fixes in this release contributed by
`Alex Russu <https://github.com/alexrussu>`_,
`Alex Willmer <https://github.com/moreati>`_,
`atoom <https://github.com/atoom>`_,
`Berend De Schouwer <https://github.com/berenddeschouwer>`_,
`Brian Candler <https://github.com/candlerb>`_,
`Dan Quackenbush <https://github.com/danquack>`_,
`dsgnr <https://github.com/dsgnr>`_,
`Jesse London <https://github.com/jesteria>`_,
`John McGrath <https://github.com/jmcgrath207>`_,
`Jonathan Rosser <https://github.com/jrosser>`_,
`Josh Smift <https://github.com/jbscare>`_,
`Luca Nunzi <https://github.com/0xlc>`_,
`Orion Poplawski <https://github.com/opoplawski>`_,
`Peter V. Saveliev <https://github.com/svinota>`_,
`Pierre-Henry Muller <https://github.com/pierrehenrymuller>`_,
`Pierre-Louis Bonicoli <https://github.com/jesteria>`_,
`Prateek Jain <https://github.com/prateekj201>`_,
`RedheatWei <https://github.com/RedheatWei>`_,
`Rick Box <https://github.com/boxrick>`_,
`nikitakazantsev12 <https://github.com/nikitakazantsev12>`_,
`Tawana Musewe <https://github.com/tbtmuse>`_,
`Timo Beckers <https://github.com/ti-mo>`_, and
`Yannig Perré <https://github.com/yannig>`_.


v0.2.2 (2018-07-26)
-------------------

Mitogen for Ansible
~~~~~~~~~~~~~~~~~~~

* `#291 <https://github.com/dw/mitogen/issues/291>`_: ``ansible_*_interpreter``
  variables are parsed using a restrictive shell-like syntax, supporting a
  common idiom where ``ansible_python_interpreter`` is set to ``/usr/bin/env
  python``.

* `#299 <https://github.com/dw/mitogen/issues/299>`_: fix the ``network_cli``
  connection type when the Mitogen strategy is active. Mitogen cannot help
  network device connections, however it should still be possible to use device
  connections while Mitogen is active.

* `#301 <https://github.com/dw/mitogen/pull/301>`_: variables like ``$HOME`` in
  the ``remote_tmp`` setting are evaluated correctly.

* `#303 <https://github.com/dw/mitogen/pull/303>`_: the :ref:`doas` become method
  is supported. Contributed by `Mike Walker
  <https://github.com/napkindrawing>`_.

* `#309 <https://github.com/dw/mitogen/issues/309>`_: fix a regression to
  process environment cleanup, caused by the change in v0.2.1 to run local
  tasks with the correct environment.

* `#317 <https://github.com/dw/mitogen/issues/317>`_: respect the verbosity
  setting when writing to Ansible's ``log_path``, if it is enabled. Child log
  filtering was also incorrect, causing the master to needlessly wake many
  times. This nets a 3.5% runtime improvement running against the local
  machine.

* The ``mitogen_ssh_debug_level`` variable is supported, permitting SSH debug
  output to be included in Mitogen's ``-vvv`` output when both are specified.


Core Library
~~~~~~~~~~~~

* `#291 <https://github.com/dw/mitogen/issues/291>`_: the ``python_path``
  parameter may specify an argument vector prefix rather than a string program
  path.

* `#300 <https://github.com/dw/mitogen/issues/300>`_: the broker could crash on
  OS X during shutdown due to scheduled `kqueue
  <https://www.freebsd.org/cgi/man.cgi?query=kevent>`_ filter changes for
  descriptors that were closed before the IO loop resumes. As a temporary
  workaround, kqueue's bulk change feature is not used.

* `#303 <https://github.com/dw/mitogen/pull/303>`_: the :ref:`doas` become method
  is now supported. Contributed by `Mike Walker
  <https://github.com/napkindrawing>`_.

* `#307 <https://github.com/dw/mitogen/issues/307>`_: SSH login banner output
  containing the word 'password' is no longer confused for a password prompt.

* `#319 <https://github.com/dw/mitogen/issues/319>`_: SSH connections would
  fail immediately on Windows Subsystem for Linux, due to use of `TCSAFLUSH`
  with :func:`termios.tcsetattr`. The flag is omitted if WSL is detected.

* `#320 <https://github.com/dw/mitogen/issues/320>`_: The OS X poller
  could spuriously wake up due to ignoring an error bit set on events returned
  by the kernel, manifesting as a failure to read from an unrelated descriptor.

* `#342 <https://github.com/dw/mitogen/issues/342>`_: The ``network_cli``
  connection type would fail due to a missing internal SSH plugin method.

* Standard IO forwarding accidentally configured the replacement ``stdout`` and
  ``stderr`` write descriptors as non-blocking, causing subprocesses that
  generate more output than kernel buffer space existed to throw errors. The
  write ends are now configured as blocking.

* When :func:`mitogen.core.enable_profiling` is active, :mod:`mitogen.service`
  threads are profiled just like other threads.

* The ``ssh_debug_level`` parameter is supported, permitting SSH debug output
  to be redirected to a Mitogen logger when specified.

* Debug logs containing command lines are printed with the minimal quoting and
  escaping required.


Thanks!
~~~~~~~

Mitogen would not be possible without the support of users. A huge thanks for
the bug reports and pull requests in this release contributed by
`Alex Russu <https://github.com/alexrussu>`_,
`Andy Freeland <https://github.com/rouge8>`_,
`Ayaz Ahmed Khan <https://github.com/ayaz>`_,
`Colin McCarthy <https://github.com/colin-mccarthy>`_,
`Dan Quackenbush <https://github.com/danquack>`_,
`Duane Zamrok <https://github.com/dewthefifth>`_,
`Gonzalo Servat <https://github.com/gservat>`_,
`Guy Knights <https://github.com/knightsg>`_,
`Josh Smift <https://github.com/jbscare>`_,
`Mark Janssen <https://github.com/sigio>`_,
`Mike Walker <https://github.com/napkindrawing>`_,
`Orion Poplawski <https://github.com/opoplawski>`_,
`falbanese <https://github.com/falbanese>`_,
`Tawana Musewe <https://github.com/tbtmuse>`_, and
`Zach Swanson <https://github.com/zswanson>`_.


v0.2.1 (2018-07-10)
-------------------

Mitogen for Ansible
~~~~~~~~~~~~~~~~~~~

* `#297 <https://github.com/dw/mitogen/issues/297>`_: compatibility: local
  actions set their working directory to that of their defining playbook, and
  inherit a process environment as if they were executed as a subprocess of the
  forked task worker.


v0.2.0 (2018-07-09)
-------------------

Mitogen 0.2.x is the inaugural feature-frozen branch eligible for fixes only,
except for problem areas listed as in-scope below. While stable from a
development perspective, it should still be considered "beta" at least for the
initial releases.

**In Scope**

* Python 3.x performance improvements
* Subprocess reaping improvements
* Major documentation improvements
* PyPI/packaging improvements
* Test suite improvements
* Replacement CI system to handle every supported OS
* Minor deviations from vanilla Ansible behaviour
* Ansible ``raw`` action support

The goal is a *tick/tock* model where even-numbered series are a maturation of
the previous unstable series, and unstable series are released on PyPI with
``--pre`` enabled. The API and user visible behaviour should remain unchanged
within a stable series.


Mitogen for Ansible
~~~~~~~~~~~~~~~~~~~

* Support for Ansible 2.3 - 2.7.x and any mixture of Python 2.6, 2.7 or 3.6 on
  controller and target nodes.

* Drop-in support for many Ansible connection types.

* Preview of Connection Delegation feature.

* Built-in file transfer compatible with connection delegation.


Core Library
~~~~~~~~~~~~

* Synchronous connection establishment via OpenSSH, sudo, su, Docker, LXC and
  FreeBSD Jails, local subprocesses and :func:`os.fork`. Parallel connection
  setup is possible using multiple threads. Connections may be used from one or
  many threads after establishment.

* UNIX masters and children, with Linux, MacOS, FreeBSD, NetBSD, OpenBSD and
  Windows Subsystem for Linux explicitly supported.

* Automatic tests covering Python 2.6, 2.7 and 3.6 on Linux only.
