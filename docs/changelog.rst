
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

To avail of fixes in an unreleased version, please download a ZIP file
`directly from GitHub <https://github.com/mitogen-hq/mitogen/>`_.


Unreleased
----------


v0.3.6 (2024-04-04)
-------------------

* :gh:issue:`974` Support Ansible 7
* :gh:issue:`1046` Raise :py:exc:`TypeError` in :func:`<mitogen.util.cast()>`
  when casting a string subtype to `bytes()` or `str()` fails. This is
  potentially an API breaking change. Failures previously passed silently.
* :gh:issue:`1046` Add :func:`<ansible_mitogen.util.cast()>`, to cast
  :class:`ansible.utils.unsafe_proxy.AnsibleUnsafe` objects in Ansible 7+.


v0.3.5 (2024-03-17)
-------------------

* :gh:issue:`987` Support Python 3.11
* :gh:issue:`885` Fix :py:exc:`PermissionError` in :py:mod:`importlib` when
  becoming an unprivileged user with Python 3.x
* :gh:issue:`1033` Support `PEP 451 <https://peps.python.org/pep-0451/>`_,
  required by Python 3.12
* :gh:issue:`1033` Support Python 3.12


v0.3.4 (2023-07-02)
-------------------

* :gh:issue:`929` Support Ansible 6 and ansible-core 2.13
* :gh:issue:`832` Fix runtime error when using the ansible.builtin.dnf module multiple times
* :gh:issue:`925` :class:`ansible_mitogen.connection.Connection` no longer tries to close the 
  connection on destruction. This is expected to reduce cases of `mitogen.core.Error: An attempt
  was made to enqueue a message with a Broker that has already exitted`. However it may result in
  resource leaks.
* :gh:issue:`659` Removed :mod:`mitogen.compat.simplejson`, not needed with Python 2.7+, contained Python 3.x syntax errors
* :gh:issue:`983` CI: Removed PyPI faulthandler requirement from tests
* :gh:issue:`1001` CI: Fixed Debian 9 & 11 tests

v0.3.3 (2022-06-03)
-------------------

* :gh:issue:`906` Support packages dynamically inserted into sys.modules, e.g. `distro` >= 1.7.0 as `ansible.module_utils.distro`.
* :gh:issue:`918` Support Python 3.10
* :gh:issue:`920` Support Ansible :ans:conn:`~podman` connection plugin
* :gh:issue:`836` :func:`mitogen.utils.with_router` decorator preserves the docstring in addition to the name.
* :gh:issue:`936` :ans:mod:`fetch` no longer emits `[DEPRECATION WARNING]: The '_remote_checksum()' method is deprecated.`


v0.3.2 (2022-01-12)
-------------------

* :gh:issue:`891` Correct `Framework :: Ansible` Trove classifier


v0.3.1 (unreleased)
-------------------

* :gh:issue:`874` Support for Ansible 5 (ansible-core 2.12)
* :gh:issue:`774` Fix bootstrap failures on macOS 11.x and 12.x, involving Python 2.7 wrapper
* :gh:issue:`834` Support for Ansible 3 and 4 (ansible-core 2.11)
* :gh:issue:`869` Continuous Integration tests are now run with Tox
* :gh:issue:`869` Continuous Integration tests now cover CentOS 6 & 8, Debian 9 & 11, Ubuntu 16.04 & 20.04
* :gh:issue:`860` Add initial support for podman connection (w/o Ansible support yet)
* :gh:issue:`873` `python -c ...` first stage no longer uses :py:mod:`platform`` to detect the macOS release
* :gh:issue:`876` `python -c ...` first stage no longer contains tab characters, to reduce size
* :gh:issue:`878` Continuous Integration tests now correctly perform comparisons of 2 digit versions
* :gh:issue:`878` Kubectl connector fixed with Ansible 2.10 and above


v0.3.0 (2021-11-24)
-------------------

This release separates itself from the v0.2.X releases. Ansible's API changed too much to support backwards compatibility so from now on, v0.2.X releases will be for Ansible < 2.10 and v0.3.X will be for Ansible 2.10+.
`See here for details <https://github.com/mitogen-hq/mitogen/pull/715#issuecomment-750697248>`_.

* :gh:issue:`827` NewStylePlanner: detect `ansible_collections` imports
* :gh:issue:`770` better check for supported Ansible version
* :gh:issue:`731` ansible 2.10 support
* :gh:issue:`652` support for ansible collections import hook
* :gh:issue:`847` Removed historic Continuous Integration reverse shell


v0.2.10 (2021-11-24)
--------------------

* :gh:issue:`597` mitogen does not support Ansible 2.8 Python interpreter detection
* :gh:issue:`655` wait_for_connection gives errors
* :gh:issue:`672` cannot perform relative import error
* :gh:issue:`673` mitogen fails on RHEL8 server with bash /usr/bin/python: No such file or directory
* :gh:issue:`676` mitogen fail to run playbook without “/usr/bin/python” on target host
* :gh:issue:`716` fetch fails with "AttributeError: 'ShellModule' object has no attribute 'tmpdir'"
* :gh:issue:`756` ssh connections with `check_host_keys='accept'` would
  timeout, when using recent OpenSSH client versions.
* :gh:issue:`758` fix initilialisation of callback plugins in test suite, to address a `KeyError` in
  :py:meth:`ansible.plugins.callback.CallbackBase.v2_runner_on_start`
* :gh:issue:`775` Test with Python 3.9
* :gh:issue:`775` Add msvcrt to the default module deny list


v0.2.9 (2019-11-02)
-------------------

This release contains minimal fixes beyond those required for Ansible 2.9.

* :gh:issue:`633`: :ans:mod:`meta: reset_connection <meta>` could fail to reset
  a connection when ``become: true`` was set on the playbook.


Thanks!
~~~~~~~

Mitogen would not be possible without the support of users. A huge thanks for
bug reports, testing, features and fixes in this release contributed by
`Can Ozokur <https://github.com/canozokur/>`_.


v0.2.8 (2019-08-18)
-------------------

This release includes Ansible 2.8 and SELinux support, fixes for two deadlocks,
and major internal design overhauls in preparation for future functionality.


Enhancements
~~~~~~~~~~~~

* :gh:issue:`556`,
  :gh:issue:`587`: Ansible 2.8 is supported.
  `Become plugins <https://docs.ansible.com/ansible/latest/plugins/become.html>`_ (:gh:issue:`631`) and
  `interpreter discovery <https://docs.ansible.com/ansible/latest/reference_appendices/interpreter_discovery.html>`_ (:gh:issue:`630`)
  are not yet handled.

* :gh:issue:`419`, :gh:issue:`470`: file descriptor usage is approximately
  halved, as it is no longer necessary to separately manage read and write
  sides to work around a design problem.

* :gh:issue:`419`: setup for all connections happens almost entirely on one
  thread, reducing contention and context switching early in a run.

* :gh:issue:`419`: Connection setup is better pipelined, eliminating some
  network round-trips. Most infrastructure is in place to support future
  removal of the final round-trips between a target booting and receiving
  function calls.

* :gh:pull:`595`: the :meth:`~mitogen.parent.Router.buildah` connection method
  is available to manipulate `Buildah <https://buildah.io/>`_ containers, and
  is exposed to Ansible as the :ans:conn:`buildah`.

* :gh:issue:`615`: a modified :ans:mod:`fetch` implements streaming transfer
  even when ``become`` is active, avoiding excess CPU and memory spikes, and
  improving performance. A representative copy of two 512 MiB files drops from
  55.7 seconds to 6.3 seconds, with peak memory usage dropping from 10.7 GiB to
  64.8 MiB. [#i615]_

* `Operon <https://networkgenomics.com/operon/>`_ no longer requires a custom
  library installation, both Ansible and Operon are supported by a single
  Mitogen release.

* The ``MITOGEN_CPU_COUNT`` variable shards the connection multiplexer into
  per-CPU workers. This may improve throughput for large runs involving file
  transfer, and is required for future functionality. One multiplexer starts by
  default, to match existing behaviour.

* :gh:commit:`d6faff06`, :gh:commit:`807cbef9`, :gh:commit:`e93762b3`,
  :gh:commit:`50bfe4c7`: locking is avoided on hot paths, and some locks are
  released before waking a thread that must immediately acquire the same lock.


Mitogen for Ansible
~~~~~~~~~~~~~~~~~~~

* :gh:issue:`363`: fix an obscure race matching *Permission denied* errors from
  some versions of :linux:man1:`su` running on heavily loaded machines.

* :gh:issue:`410`: Uses of :linux:man7:`unix` sockets are replaced with
  traditional :linux:man7:`pipe` pairs when SELinux is detected, to work around
  a broken heuristic in common SELinux policies that prevents inheriting
  :linux:man7:`unix` sockets across privilege domains.

* :gh:issue:`467`: an incompatibility running Mitogen under `Molecule
  <https://ansible.readthedocs.io/projects/molecule/>`_ was resolved.

* :gh:issue:`547`, :gh:issue:`598`: fix a deadlock during initialization of
  connections, ``async`` tasks, tasks using custom :mod:`module_utils`,
  ``mitogen_task_isolation: fork`` modules, and modules present on an internal
  blacklist. This would manifest as a timeout or hang, was easily hit, had been
  present since 0.2.0, and likely impacted many users.

* :gh:issue:`549`: the open file limit is increased to the permitted hard
  limit. It is common for distributions to ship with a higher hard limit than
  the default soft limit, allowing *"too many open files"* errors to be avoided
  more often in large runs without user intervention.

* :gh:issue:`558`, :gh:issue:`582`: on Ansible 2.3 a directory was
  unconditionally deleted after the first module belonging to an action plug-in
  had executed, causing the :ans:mod:`unarchive` to fail.

* :gh:issue:`578`: the extension could crash while rendering an error due to an
  incorrect format string.

* :gh:issue:`590`: the importer can handle modules that replace themselves in
  :data:`sys.modules` with completely unrelated modules during import, as in
  the case of Ansible 2.8 :mod:`ansible.module_utils.distro`.

* :gh:issue:`591`: the working directory is reset between tasks to ensure
  :func:`os.getcwd` cannot fail, in the same way :class:`AnsibleModule`
  resets it during initialization. However this restore happens before the
  module executes, ensuring code that calls :func:`os.getcwd` prior to
  :class:`AnsibleModule` initialization, such as the Ansible 2.7
  :ans:mod:`pip`, cannot fail due to the actions of a prior task.

* :gh:issue:`593`: the SSH connection method exposes
  ``mitogen_ssh_keepalive_interval`` and ``mitogen_ssh_keepalive_count``
  variables, and the default timeout for an SSH server has been increased from
  `15*3` seconds to `30*10` seconds.

* :gh:issue:`600`: functionality to reflect changes to ``/etc/environment`` did
  not account for Unicode file contents. The file may now use any single byte
  encoding.

* :gh:issue:`602`: connection configuration is more accurately inferred for
  :ans:mod:`meta: reset_connection <meta>`, the :ans:mod:`synchronize`, and for
  any action plug-ins that establish additional connections.

* :gh:issue:`598`, :gh:issue:`605`: fix a deadlock managing a shared counter
  used for load balancing, present since 0.2.4.

* :gh:issue:`615`: streaming is implemented for the :ans:mod:`fetch` and other
  actions that transfer files from targets to the controller. Previously files
  were sent in one message, requiring them to fit in RAM and be smaller than an
  internal message size sanity check. Transfers from controller to targets have
  been streaming since 0.2.0.

* :gh:commit:`7ae926b3`: the :ans:mod:`lineinfile` leaked writable temporary
  file descriptors between Ansible 2.7.0 and 2.8.2. When :ans:mod:`~lineinfile`
  created or modified a script, and that script was later executed, the
  execution could fail with "*text file busy*". Temporary descriptors are now
  tracked and cleaned up on exit for all modules.


Core Library
~~~~~~~~~~~~

* Log readability is improving and many :func:`repr` strings are more
  descriptive. The old pseudo-function-call format is migrating to
  readable output where possible. For example, *"Stream(ssh:123).connect()"*
  might be written *"connecting to ssh:123"*.

* In preparation for reducing default log output, many messages are delivered
  to per-component loggers, including messages originating from children,
  enabling :mod:`logging` aggregation to function as designed. An importer
  message like::

      12:00:00 D mitogen.ctx.remotehost mitogen: loading module "foo"

  Might instead be logged to the ``mitogen.importer.[remotehost]`` logger::

      12:00:00 D mitogen.importer.[remotehost] loading module "foo"

  Allowing a filter or handler for ``mitogen.importer`` to select that logger
  in every process. This introduces a small risk of leaking memory in
  long-lived programs, as logger objects are internally persistent.

* :func:`bytearray` was removed from the list of supported serialization types.
  It was never portable between Python versions, unused, and never made much
  sense to support.

* :gh:issue:`170`: to improve subprocess
  management and asynchronous connect, a :class:`~mitogen.parent.TimerList`
  interface is available, accessible as :attr:`Broker.timers` in an
  asynchronous context.

* :gh:issue:`419`: the internal
  :class:`~mitogen.core.Stream` has been refactored into many new classes,
  modularizing protocol behaviour, output buffering, line-oriented input
  parsing, option handling and connection management. Connection setup is
  internally asynchronous, laying most groundwork for fully asynchronous
  connect, proxied Ansible become plug-ins, and in-process SSH.

* :gh:issue:`169`,
  :gh:issue:`419`: zombie subprocess reaping
  has vastly improved, by using timers to efficiently poll for a child to exit,
  and delaying shutdown while any subprocess remains. Polling avoids
  process-global configuration such as a `SIGCHLD` handler, or
  :func:`signal.set_wakeup_fd` available in modern Python.

* :gh:issue:`256`, :gh:issue:`419`: most :func:`os.dup` use was eliminated,
  along with most manual file descriptor management. Descriptors are trapped in
  :func:`os.fdopen` objects at creation, ensuring a leaked object will close
  itself, and ensuring every descriptor is fused to a `closed` flag, preventing
  historical bugs where a double close could destroy unrelated descriptors.

* :gh:issue:`533`: routing accounts for
  a race between a parent (or cousin) sending a message to a child via an
  intermediary, where the child had recently disconnected, and
  :data:`~mitogen.core.DEL_ROUTE` propagating from the intermediary
  to the sender, informing it that the child no longer exists. This condition
  is detected at the intermediary and a :ref:`dead message <IS_DEAD>` is
  returned to the sender.

  Previously since the intermediary had already removed its route for the
  child, the *route messages upwards* rule would be triggered, causing the
  message (with a privileged :ref:`src_id/auth_id <stream-protocol>`) to be
  sent upstream, resulting in a ``bad auth_id`` error logged at the first
  upstream parent, and a possible hang due to a request message being dropped.

* :gh:issue:`586`: fix import of
  :mod:`__main__` on later versions of Python 3 when running from the
  interactive console.

* :gh:issue:`606`: fix example code on the
  documentation front page.

* :gh:issue:`612`: fix various errors
  introduced by stream refactoring.

* :gh:issue:`615`: when routing fails to
  deliver a message for some reason other than the sender cannot or should not
  reach the recipient, and no reply-to address is present on the message,
  instead send a :ref:`dead message <IS_DEAD>` to the original recipient. This
  ensures a descriptive message is delivered to a thread sleeping on the reply
  to a function call, where the reply might be dropped due to exceeding the
  maximum configured message size.

* :gh:issue:`624`: the number of threads used for a child's automatically
  initialized service thread pool has been reduced from 16 to 2. This may drop
  to 1 in future, and become configurable via a :class:`Router` option.

* :gh:commit:`a5536c35`: avoid quadratic
  buffer management when logging lines received from a child's redirected
  standard IO.

* :gh:commit:`49a6446a`: the
  :meth:`empty` methods of :class:`~mitogen.core.Latch`,
  :class:`~mitogen.core.Receiver` and :class:`~mitogen.select.Select` are
  obsoleted by a more general :meth:`size` method. :meth:`empty` will be
  removed in 0.3

* :gh:commit:`ecc570cb`: previously
  :meth:`mitogen.select.Select.add` would enqueue one wake event when adding an
  existing receiver, latch or subselect that contained multiple buffered items,
  causing :meth:`get` calls to block or fail even though data existed to return.

* :gh:commit:`5924af15`: *[security]*
  unidirectional routing, where contexts may optionally only communicate with
  parents and never siblings (so that air-gapped networks cannot be
  unintentionally bridged) was not inherited when a child was initiated
  directly from another child. This did not effect Ansible, since the
  controller initiates any new child used for routing, only forked tasks are
  initiated by children.


Thanks!
~~~~~~~

Mitogen would not be possible without the support of users. A huge thanks for
bug reports, testing, features and fixes in this release contributed by
`Andreas Hubert <https://github.com/peshay>`_,
`Anton Markelov <https://github.com/strangeman>`_,
`Dan <https://github.com/dsgnr>`_,
`Dave Cottlehuber <https://github.com/dch>`_,
`Denis Krienbühl <https://github.com/href>`_,
`El Mehdi CHAOUKI <https://github.com/elmchaouki>`_,
`Florent Dutheil <https://github.com/fdutheil>`_,
`James Hogarth <https://github.com/hogarthj>`_,
`Jordan Webb <https://github.com/jordemort>`_,
`Julian Andres Klode <https://github.com/julian-klode>`_,
`Marc Hartmayer <https://github.com/marc1006>`_,
`Nigel Metheringham <https://github.com/nigelm>`_,
`Orion Poplawski <https://github.com/opoplawski>`_,
`Pieter Voet <https://github.com/pietervoet/>`_,
`Stefane Fermigier <https://github.com/sfermigier>`_,
`Szabó Dániel Ernő <https://github.com/r3ap3rpy>`_,
`Ulrich Schreiner <https://github.com/ulrichSchreiner>`_,
`Vincent S. Cojot <https://github.com/ElCoyote27>`_,
`yen <https://github.com/antigenius0910>`_,
`Yuki Nishida <https://github.com/yuki-nishida-exa>`_,
`@alexhexabeam <https://github.com/alexhexabeam>`_,
`@DavidVentura <https://github.com/DavidVentura>`_,
`@dbiegunski <https://github.com/dbiegunski>`_,
`@ghp-rr <https://github.com/ghp-rr>`_,
`@migalsp <https://github.com/migalsp>`_,
`@rizzly <https://github.com/rizzly>`_,
`@SQGE <https://github.com/SQGE>`_, and
`@tho86 <https://github.com/tho86>`_.


.. rubric:: Footnotes

.. [#i615] Peak RSS of controller and target as measured with ``/usr/bin/time
   -v ansible-playbook -c local`` using the reproduction supplied in
   :gh:issue:`615`.


v0.2.7 (2019-05-19)
-------------------

This release primarily exists to add a descriptive error message when running
on Ansible 2.8, which is not yet supported.

Fixes
~~~~~

* :gh:issue:`557`: fix a crash when running
  on machines with high CPU counts.

* :gh:issue:`570`: the :ans:mod:`firewalld` internally caches a dbus name that
  changes across :ans:mod:`~firewalld` restarts, causing a failure if the
  service is restarted between :ans:mod:`~firewalld` module invocations.

* :gh:issue:`575`: fix a crash when
  rendering an error message to indicate no usable temporary directories could
  be found.

* :gh:issue:`576`: fix a crash during
  startup on SuSE Linux 11, due to an incorrect version compatibility check in
  the Mitogen code.

* :gh:issue:`581`: a
  ``mitogen_mask_remote_name`` Ansible variable is exposed, to allow masking
  the username, hostname and process ID of ``ansible-playbook`` running on the
  controller machine.

* :gh:issue:`587`: display a friendly
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

* :gh:issue:`542`: some versions of OS X
  ship a default Python that does not support :func:`select.poll`. Restore the
  0.2.3 behaviour of defaulting to Kqueue in this case, but still prefer
  :func:`select.poll` if it is available.

* :gh:issue:`545`: an optimization
  introduced in :gh:issue:`493` caused a
  64-bit integer to be assigned to a 32-bit field on ARM 32-bit targets,
  causing runs to fail.

* :gh:issue:`548`: `mitogen_via=` could fail
  when the selected transport was set to ``smart``.

* :gh:issue:`550`: avoid some broken
  TTY-related `ioctl()` calls on Windows Subsystem for Linux 2016 Anniversary
  Update.

* :gh:issue:`554`: third party Ansible
  action plug-ins that invoked :func:`_make_tmp_path` repeatedly could trigger
  an assertion failure.

* :gh:issue:`555`: work around an old idiom
  that reloaded :mod:`sys` in order to change the interpreter's default encoding.

* :gh:commit:`ffae0355`: needless
  information was removed from the documentation and installation procedure.


Core Library
~~~~~~~~~~~~

* :gh:issue:`535`: to support function calls
  on a service pool from another thread, :class:`mitogen.select.Select`
  additionally permits waiting on :class:`mitogen.core.Latch`.

* :gh:issue:`535`:
  :class:`mitogen.service.Pool.defer` allows any function to be enqueued for
  the thread pool from another thread.

* :gh:issue:`535`: a new
  :mod:`mitogen.os_fork` module provides a :func:`os.fork` wrapper that pauses
  thread activity during fork. On Python<2.6, :class:`mitogen.core.Broker` and
  :class:`mitogen.service.Pool` automatically record their existence so that a
  :func:`os.fork` monkey-patch can automatically pause them for any attempt to
  start a subprocess.

* :gh:commit:`ca63c26e`:
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

* :gh:issue:`511`,
  :gh:issue:`536`: changes in 0.2.4 to
  repair ``delegate_to`` handling broke default ``ansible_python_interpreter``
  handling. Test coverage was added.

* :gh:issue:`532`: fix a race in the service
  used to propagate Ansible modules, that could easily manifest when starting
  asynchronous tasks in a loop.

* :gh:issue:`536`: changes in 0.2.4 to
  support Python 2.4 interacted poorly with modules that imported
  ``simplejson`` from a controller that also loaded an incompatible newer
  version of ``simplejson``.

* :gh:issue:`537`: a swapped operator in the
  CPU affinity logic meant 2 cores were reserved on 1<n<4 core machines, rather
  than 1 core as desired. Test coverage was added.

* :gh:issue:`538`: the source distribution
  includes a ``LICENSE`` file.

* :gh:issue:`539`: log output is no longer
  duplicated when the Ansible ``log_path`` setting is enabled.

* :gh:issue:`540`: the ``stderr`` stream of
  async module invocations was previously discarded.

* :gh:issue:`541`: Python error logs
  originating from the ``boto`` package are quiesced, and only appear in
  ``-vvv`` output. This is since EC2 modules may trigger errors during normal
  operation, when retrying transiently failing requests.

* :gh:commit:`748f5f67`,
  :gh:commit:`21ad299d`,
  :gh:commit:`8ae6ca1d`,
  :gh:commit:`7fd0d349`:
  the ``ansible_ssh_host``, ``ansible_ssh_user``, ``ansible_user``,
  ``ansible_become_method``, and ``ansible_ssh_port`` variables more correctly
  match typical behaviour when ``mitogen_via=`` is active.

* :gh:commit:`2a8567b4`: fix a race
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

* :gh:issue:`76`,
  :gh:issue:`351`,
  :gh:issue:`352`: disconnect propagation
  has improved, allowing Ansible to cancel waits for responses from abruptly
  disconnected targets. This ensures a task will reliably fail rather than
  hang, for example on network failure or EC2 instance maintenance.

* :gh:issue:`369`,
  :gh:issue:`407`: :meth:`Connection.reset`
  is implemented, allowing :ans:mod:`meta: reset_connection <meta>` to shut
  down the remote interpreter as documented, and improving support for the
  :ans:mod:`reboot`.

* :gh:commit:`09aa27a6`: the
  ``mitogen_host_pinned`` strategy wraps the ``host_pinned`` strategy
  introduced in Ansible 2.7.

* :gh:issue:`477`: Python 2.4 is fully
  supported by the core library and tested automatically, in any parent/child
  combination of 2.4, 2.6, 2.7 and 3.6 interpreters.

* :gh:issue:`477`: Ansible 2.3 is fully
  supported and tested automatically. In combination with the core library
  Python 2.4 support, this allows Red Hat Enterprise Linux 5 targets to be
  managed with Mitogen. The ``simplejson`` package need not be installed on
  such targets, as is usually required by Ansible.

* :gh:issue:`412`: to simplify diagnosing
  connection configuration problems, Mitogen ships a ``mitogen_get_stack``
  action that is automatically added to the action plug-in path. See
  :ref:`mitogen-get-stack` for more information.

* :gh:commit:`152effc2`,
  :gh:commit:`bd4b04ae`: a CPU affinity
  policy was added for Linux controllers, reducing latency and SMP overhead on
  hot paths exercised for every task. This yielded a 19% speedup in a 64-target
  job composed of many short tasks, and should easily be visible as a runtime
  improvement in many-host runs.

* :gh:commit:`2b44d598`: work around a
  defective caching mechanism by pre-heating it before spawning workers. This
  saves 40% runtime on a synthetic repetitive task.

* :gh:commit:`0979422a`: an expensive
  dependency scanning step was redundantly invoked for every task,
  bottlenecking the connection multiplexer.

* :gh:commit:`eaa990a97`: a new
  ``mitogen_ssh_compression`` variable is supported, allowing Mitogen's default
  SSH compression to be disabled. SSH compression is a large contributor to CPU
  usage in many-target runs, and severely limits file transfer. On a `"shell:
  hostname"` task repeated 500 times, Mitogen requires around 800 bytes per
  task with compression, rising to 3 KiB without. File transfer throughput
  rises from ~25MiB/s when enabled to ~200MiB/s when disabled.

* :gh:issue:`260`,
  :gh:commit:`a18a083c`: brokers no
  longer wait for readiness indication to transmit, and instead assume
  transmission will succeed. As this is usually true, one loop iteration and
  two poller reconfigurations are avoided, yielding a significant reduction in
  interprocess round-trip latency.

* :gh:issue:`415`, :gh:issue:`491`, :gh:issue:`493`: the interface employed
  for in-process queues changed from :freebsd:man2:`kqueue` /
  :linux:man7:`epoll` to :linux:man2:`poll`, which requires no setup or
  teardown, yielding a 38% latency reduction for inter-thread communication.


Fixes
^^^^^

* :gh:issue:`251`,
  :gh:issue:`359`,
  :gh:issue:`396`,
  :gh:issue:`401`,
  :gh:issue:`404`,
  :gh:issue:`412`,
  :gh:issue:`434`,
  :gh:issue:`436`,
  :gh:issue:`465`: connection delegation and
  ``delegate_to:`` handling suffered a major regression in 0.2.3. The 0.2.2
  behaviour has been restored, and further work has been made to improve the
  compatibility of connection delegation's configuration building methods.

* :gh:issue:`323`,
  :gh:issue:`333`: work around a Windows
  Subsystem for Linux bug that caused tracebacks to appear during shutdown.

* :gh:issue:`334`: the SSH method
  tilde-expands private key paths using Ansible's logic. Previously the path
  was passed unmodified to SSH, which expanded it using :func:`pwd.getpwnam`.
  This differs from :func:`os.path.expanduser`, which uses the ``HOME``
  environment variable if it is set, causing behaviour to diverge when Ansible
  was invoked across user accounts via ``sudo``.

* :gh:issue:`364`: file transfers from
  controllers running Python 2.7.2 or earlier could be interrupted due to a
  forking bug in the :mod:`tempfile` module.

* :gh:issue:`370`: the Ansible :ans:mod:`reboot` is supported.

* :gh:issue:`373`: the LXC and LXD methods print a useful hint on failure, as
  no useful error is normally logged to the console by these tools.

* :gh:issue:`374`,
  :gh:issue:`391`: file transfer and module
  execution from 2.x controllers to 3.x targets was broken due to a regression
  caused by refactoring, and compounded by :gh:issue:`426`.

* :gh:issue:`400`: work around a threading
  bug in the AWX display callback when running with high verbosity setting.

* :gh:issue:`409`: the setns method was
  silently broken due to missing tests. Basic coverage was added to prevent a
  recurrence.

* :gh:issue:`409`: the LXC and LXD methods
  support ``mitogen_lxc_path`` and ``mitogen_lxc_attach_path`` variables to
  control the location of third pary utilities.

* :gh:issue:`410`: the sudo method supports
  the SELinux ``--type`` and ``--role`` options.

* :gh:issue:`420`: if a :class:`Connection`
  was constructed in the Ansible top-level process, for example while executing
  ``meta: reset_connection``, resources could become undesirably shared in
  subsequent children.

* :gh:issue:`426`: an oversight while
  porting to Python 3 meant no automated 2->3 tests were running. A significant
  number of 2->3 bugs were fixed, mostly in the form of Unicode/bytes
  mismatches.

* :gh:issue:`429`: the ``sudo`` method can
  now recognize internationalized password prompts.

* :gh:issue:`362`,
  :gh:issue:`435`: the previous fix for slow
  Python 2.x subprocess creation on Red Hat caused newly spawned children to
  have a reduced open files limit. A more intrusive fix has been added to
  directly address the problem without modifying the subprocess environment.

* :gh:issue:`397`,
  :gh:issue:`454`: the previous approach to
  handling modern Ansible temporary file cleanup was too aggressive, and could
  trigger early finalization of Cython-based extension modules, leading to
  segmentation faults.

* :gh:issue:`499`: the ``allow_same_user``
  Ansible configuration setting is respected.

* :gh:issue:`527`: crashes in modules are
  trapped and reported in a manner that matches Ansible. In particular, a
  module crash no longer leads to an exception that may crash the corresponding
  action plug-in.

* :gh:commit:`dc1d4251`: the :ans:mod:`synchronize` could fail with the Docker
  transport due to a missing attribute.

* :gh:commit:`599da068`: fix a race
  when starting async tasks, where it was possible for the controller to
  observe no status file on disk before the task had a chance to write one.

* :gh:commit:`2c7af9f04`: Ansible
  modules were repeatedly re-transferred. The bug was hidden by the previously
  mandatorily enabled SSH compression.


Core Library
~~~~~~~~~~~~

* :gh:issue:`76`: routing records the
  destination context IDs ever received on each stream, and when disconnection
  occurs, propagates :data:`mitogen.core.DEL_ROUTE` messages towards every
  stream that ever communicated with the disappearing peer, rather than simply
  towards parents. Conversations between nodes anywhere in the tree receive
  :data:`mitogen.core.DEL_ROUTE` when either participant disconnects, allowing
  receivers to wake with :class:`mitogen.core.ChannelError`, even when one
  participant is not a parent of the other.

* :gh:issue:`109`,
  :gh:commit:`57504ba6`: newer Python 3
  releases explicitly populate :data:`sys.meta_path` with importer internals,
  causing Mitogen to install itself at the end of the importer chain rather
  than the front.

* :gh:issue:`310`: support has returned for
  trying to figure out the real source of non-module objects installed in
  :data:`sys.modules`, so they can be imported. This is needed to handle syntax
  sugar used by packages like :mod:`plumbum`.

* :gh:issue:`349`: an incorrect format
  string could cause large stack traces when attempting to import built-in
  modules on Python 3.

* :gh:issue:`387`,
  :gh:issue:`413`: dead messages include an
  optional reason in their body. This is used to cause
  :class:`mitogen.core.ChannelError` to report far more useful diagnostics at
  the point the error occurs that previously would have been buried in debug
  log output from an unrelated context.

* :gh:issue:`408`: a variety of fixes were
  made to restore Python 2.4 compatibility.

* :gh:issue:`399`,
  :gh:issue:`437`: ignore a
  :class:`DeprecationWarning` to avoid failure of the ``su`` method on Python
  3.7.

* :gh:issue:`405`: if an oversized message
  is rejected, and it has a ``reply_to`` set, a dead message is returned to the
  sender. This ensures function calls exceeding the configured maximum size
  crash rather than hang.

* :gh:issue:`406`:
  :class:`mitogen.core.Broker` did not call :meth:`mitogen.core.Poller.close`
  during shutdown, leaking the underlying poller FD in masters and parents.

* :gh:issue:`406`: connections could leak
  FDs when a child process failed to start.

* :gh:issue:`288`,
  :gh:issue:`406`,
  :gh:issue:`417`: connections could leave
  FD wrapper objects that had not been closed lying around to be closed during
  garbage collection, causing reused FD numbers to be closed at random moments.

* :gh:issue:`411`: the SSH method typed
  "``y``" rather than the requisite "``yes``" when `check_host_keys="accept"`
  was configured. This would lead to connection timeouts due to the hung
  response.

* :gh:issue:`414`,
  :gh:issue:`425`: avoid deadlock of forked
  children by reinitializing the :mod:`mitogen.service` pool lock.

* :gh:issue:`416`: around 1.4KiB of memory
  was leaked on every RPC, due to a list of strong references keeping alive any
  handler ever registered for disconnect notification.

* :gh:issue:`418`: the
  :func:`mitogen.parent.iter_read` helper would leak poller FDs, because
  execution of its :keyword:`finally` block was delayed on Python 3. Now
  callers explicitly close the generator when finished.

* :gh:issue:`422`: the fork method could
  fail to start if :data:`sys.stdout` was opened in block buffered mode, and
  buffered data was pending in the parent prior to fork.

* :gh:issue:`438`: a descriptive error is
  logged when stream corruption is detected.

* :gh:issue:`439`: descriptive errors are
  raised when attempting to invoke unsupported function types.

* :gh:issue:`444`: messages regarding
  unforwardable extension module are no longer logged as errors.

* :gh:issue:`445`: service pools unregister
  the :data:`mitogen.core.CALL_SERVICE` handle at shutdown, ensuring any
  outstanding messages are either processed by the pool as it shuts down, or
  have dead messages sent in reply to them, preventing peer contexts from
  hanging due to a forgotten buffered message.

* :gh:issue:`446`: given thread A calling
  :meth:`mitogen.core.Receiver.close`, and thread B, C, and D sleeping in
  :meth:`mitogen.core.Receiver.get`, previously only one sleeping thread would
  be woken with :class:`mitogen.core.ChannelError` when the receiver was
  closed. Now all threads are woken per the docstring.

* :gh:issue:`447`: duplicate attempts to
  invoke :meth:`mitogen.core.Router.add_handler` cause an error to be raised,
  ensuring accidental re-registration of service pools are reported correctly.

* :gh:issue:`448`: the import hook
  implementation now raises :class:`ModuleNotFoundError` instead of
  :class:`ImportError` in Python 3.6 and above, to cope with an upcoming
  version of the :mod:`subprocess` module requiring this new subclass to be
  raised.

* :gh:issue:`453`: the loggers used in
  children for standard IO redirection have propagation disabled, preventing
  accidental reconfiguration of the :mod:`logging` package in a child from
  setting up a feedback loop.

* :gh:issue:`456`: a descriptive error is
  logged when :meth:`mitogen.core.Broker.defer` is called after the broker has
  shut down, preventing new messages being enqueued that will never be sent,
  and subsequently producing a program hang.

* :gh:issue:`459`: the beginnings of a
  :meth:`mitogen.master.Router.get_stats` call has been added. The initial
  statistics cover the module loader only.

* :gh:issue:`462`: Mitogen could fail to
  open a PTY on broken Linux systems due to a bad interaction between the glibc
  :func:`grantpt` function and an incorrectly mounted ``/dev/pts`` filesystem.
  Since correct group ownership is not required in most scenarios, when this
  problem is detected, the PTY is allocated and opened directly by the library.

* :gh:issue:`479`: Mitogen could fail to
  import :mod:`__main__` on Python 3.4 and newer due to a breaking change in
  the :mod:`pkgutil` API. The program's main script is now handled specially.

* :gh:issue:`481`: the version of `sudo`
  that shipped with CentOS 5 replaced itself with the program to be executed,
  and therefore did not hold any child PTY open on our behalf. The child
  context is updated to preserve any PTY FD in order to avoid the kernel
  sending `SIGHUP` early during startup.

* :gh:issue:`523`: the test suite didn't
  generate a code coverage report if any test failed.

* :gh:issue:`524`: Python 3.6+ emitted a
  :class:`DeprecationWarning` for :func:`mitogen.utils.run_with_router`.

* :gh:issue:`529`: Code coverage of the
  test suite was not measured across all Python versions.

* :gh:commit:`16ca111e`: handle OpenSSH
  7.5 permission denied prompts when ``~/.ssh/config`` rewrites are present.

* :gh:commit:`9ec360c2`: a new
  :meth:`mitogen.core.Broker.defer_sync` utility function is provided.

* :gh:commit:`f20e0bba`:
  :meth:`mitogen.service.FileService.register_prefix` permits granting
  unprivileged access to whole filesystem subtrees, rather than single files at
  a time.

* :gh:commit:`8f85ee03`:
  :meth:`mitogen.core.Router.myself` returns a :class:`mitogen.core.Context`
  referring to the current process.

* :gh:commit:`824c7931`: exceptions
  raised by the import hook were updated to include probable reasons for
  a failure.

* :gh:commit:`57b652ed`: a stray import
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

* :gh:pull:`315`,
  :gh:issue:`392`: Ansible 2.6 and 2.7 are
  supported.

* :gh:issue:`321`, :gh:issue:`336`: temporary file handling was simplified,
  undoing earlier damage caused by compatibility fixes, improving 2.6
  compatibility, and avoiding two network roundtrips for every related action
  (:ans:mod:`~assemble`, :ans:mod:`~aws_s3`, :ans:mod:`~copy`,
  :ans:mod:`~patch`, :ans:mod:`~script`, :ans:mod:`~template`,
  :ans:mod:`~unarchive`, :ans:mod:`~uri`). See :ref:`ansible_tempfiles` for a
  complete description.

* :gh:pull:`376`, :gh:pull:`377`: the ``kubectl`` connection type is now
  supported. Contributed by Yannig Perré.

* :gh:commit:`084c0ac0`: avoid a roundtrip in :ans:mod:`~copy` and
  :ans:mod:`~template` due to an unfortunate default.

* :gh:commit:`7458dfae`: avoid a
  roundtrip when transferring files smaller than 124KiB. Copy and template
  actions are now 2-RTT, reducing runtime for a 20-iteration template loop over
  a 250 ms link from 30 seconds to 10 seconds compared to v0.2.2, down from 120
  seconds compared to vanilla.

* :gh:issue:`337`: To avoid a scaling
  limitation, a PTY is no longer allocated for an SSH connection unless the
  configuration specifies a password.

* :gh:commit:`d62e6e2a`: many-target
  runs executed the dependency scanner redundantly due to missing
  synchronization, wasting significant runtime in the connection multiplexer.
  In one case work was reduced by 95%, which may manifest as faster runs.

* :gh:commit:`5189408e`: threads are
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

* :gh:issue:`251`,
  :gh:issue:`340`: Connection Delegation
  could establish connections to the wrong target when ``delegate_to:`` is
  present.

* :gh:issue:`291`: when Mitogen had
  previously been installed using ``pip`` or ``setuptools``, the globally
  installed version could conflict with a newer version bundled with an
  extension that had been installed using the documented steps. Now the bundled
  library always overrides over any system-installed copy.

* :gh:issue:`324`: plays with a
  `custom module_utils <https://docs.ansible.com/ansible/latest/reference_appendices/config.html#default-module-utils-path>`_
  would fail due to fallout from the Python 3 port and related tests being
  disabled.

* :gh:issue:`331`: the connection
  multiplexer subprocess always exits before the main Ansible process, ensuring
  logs generated by it do not overwrite the user's prompt when ``-vvv`` is
  enabled.

* :gh:issue:`332`: support a new
  :func:`sys.excepthook`-based module exit mechanism added in Ansible 2.6.

* :gh:issue:`338`: compatibility: changes to
  ``/etc/environment`` and ``~/.pam_environment`` made by a task are reflected
  in the runtime environment of subsequent tasks. See
  :ref:`ansible_process_env` for a complete description.

* :gh:issue:`343`: the sudo ``--login``
  option is supported.

* :gh:issue:`344`: connections no longer
  fail when the controller's login username contains slashes.

* :gh:issue:`345`: the ``IdentitiesOnly
  yes`` option is no longer supplied to OpenSSH by default, better matching
  Ansible's behaviour.

* :gh:issue:`355`: tasks configured to run
  in an isolated forked subprocess were forked from the wrong parent context.
  This meant built-in modules overridden via a custom ``module_utils`` search
  path may not have had any effect.

* :gh:issue:`362`: to work around a slow
  algorithm in the :mod:`subprocess` module, the maximum number of open files
  in processes running on the target is capped to 512, reducing the work
  required to start a subprocess by >2000x in default CentOS configurations.

* :gh:issue:`397`: recent Mitogen master
  versions could fail to clean up temporary directories in a number of
  circumstances, and newer Ansibles moved to using :mod:`atexit` to effect
  temporary directory cleanup in some circumstances.

* :gh:commit:`b9112a9c`,
  :gh:commit:`2c287801`: OpenSSH 7.5
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

* :gh:issue:`305`: fix a long-standing minor
  race relating to the logging framework, where *no route for Message..*
  would frequently appear during startup.

* :gh:issue:`313`:
  :meth:`mitogen.parent.Context.call` was documented as capable of accepting
  static methods. While possible on Python 2.x the result is ugly, and in every
  case it should be trivial to replace with a classmethod. The documentation
  was fixed.

* :gh:issue:`337`: to avoid a scaling
  limitation, a PTY is no longer allocated for each OpenSSH client if it can be
  avoided. PTYs are only allocated if a password is supplied, or when
  `host_key_checking=accept`. This is since Linux has a default of 4096 PTYs
  (``kernel.pty.max``), while OS X has a default of 127 and an absolute maximum
  of 999 (``kern.tty.ptmx_max``).

* :gh:issue:`339`: the LXD connection method
  was erroneously executing LXC Classic commands.

* :gh:issue:`345`: the SSH connection method
  allows optionally disabling ``IdentitiesOnly yes``.

* :gh:issue:`356`: if the master Python
  process does not have :data:`sys.executable` set, the default Python
  interpreter used for new children on the local machine defaults to
  ``"/usr/bin/python"``.

* :gh:issue:`366`,
  :gh:issue:`380`: attempts by children to
  import :mod:`__main__` where the main program module lacks an execution guard
  are refused, and an error is logged. This prevents a common and highly
  confusing error when prototyping new scripts.

* :gh:pull:`371`: the LXC connection method
  uses a more compatible method to establish an non-interactive session.
  Contributed by Brian Candler.

* :gh:commit:`af2ded66`: add
  :func:`mitogen.fork.on_fork` to allow non-Mitogen managed process forks to
  clean up Mitogen resources in the child.

* :gh:commit:`d6784242`: the setns method
  always resets ``HOME``, ``SHELL``, ``LOGNAME`` and ``USER`` environment
  variables to an account in the target container, defaulting to ``root``.

* :gh:commit:`830966bf`: the UNIX
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
`Peter V. Saveliev <https://github.com/svinota/>`_,
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

* :gh:issue:`291`: ``ansible_*_interpreter``
  variables are parsed using a restrictive shell-like syntax, supporting a
  common idiom where ``ansible_python_interpreter`` is set to ``/usr/bin/env
  python``.

* :gh:issue:`299`: fix the ``network_cli``
  connection type when the Mitogen strategy is active. Mitogen cannot help
  network device connections, however it should still be possible to use device
  connections while Mitogen is active.

* :gh:pull:`301`: variables like ``$HOME`` in
  the ``remote_tmp`` setting are evaluated correctly.

* :gh:pull:`303`: the :ref:`doas` become method
  is supported. Contributed by `Mike Walker
  <https://github.com/napkindrawing>`_.

* :gh:issue:`309`: fix a regression to
  process environment cleanup, caused by the change in v0.2.1 to run local
  tasks with the correct environment.

* :gh:issue:`317`: respect the verbosity
  setting when writing to Ansible's ``log_path``, if it is enabled. Child log
  filtering was also incorrect, causing the master to needlessly wake many
  times. This nets a 3.5% runtime improvement running against the local
  machine.

* The ``mitogen_ssh_debug_level`` variable is supported, permitting SSH debug
  output to be included in Mitogen's ``-vvv`` output when both are specified.


Core Library
~~~~~~~~~~~~

* :gh:issue:`291`: the ``python_path``
  parameter may specify an argument vector prefix rather than a string program
  path.

* :gh:issue:`300`: the broker could crash on OS X during shutdown due to
  scheduled :freebsd:man2:`kqueue` filter changes for
  descriptors that were closed before the IO loop resumes. As a temporary
  workaround, kqueue's bulk change feature is not used.

* :gh:pull:`303`: the :ref:`doas` become method
  is now supported. Contributed by `Mike Walker
  <https://github.com/napkindrawing>`_.

* :gh:issue:`307`: SSH login banner output
  containing the word 'password' is no longer confused for a password prompt.

* :gh:issue:`319`: SSH connections would
  fail immediately on Windows Subsystem for Linux, due to use of `TCSAFLUSH`
  with :func:`termios.tcsetattr`. The flag is omitted if WSL is detected.

* :gh:issue:`320`: The OS X poller
  could spuriously wake up due to ignoring an error bit set on events returned
  by the kernel, manifesting as a failure to read from an unrelated descriptor.

* :gh:issue:`342`: The ``network_cli``
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

* :gh:issue:`297`: compatibility: local
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
