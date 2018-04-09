
Ansible Extension
=================

.. image:: images/ansible/cell_division.png
    :align: right

An experimental extension to `Ansible`_ is included that implements host
connections over Mitogen, replacing embedded shell invocations with pure-Python
equivalents invoked via highly efficient remote procedure calls tunnelled over
SSH. No changes are required to the target hosts.

The extension isn't nearly in a generally dependable state yet, however it
already works well enough for testing against real-world playbooks. `Bug
reports`_ in this area are very welcome – Ansible is a huge beast, and only
significant testing will prove the extension's soundness.

Divergence from Ansible's normal behaviour is considered a bug, so please
report anything you notice, regardless of how inconsequential it may seem.

.. _Ansible: https://www.ansible.com/

.. _Bug reports: https://goo.gl/yLKZiJ


Overview
--------

You should **expect a 1.25x - 7x speedup** and a **CPU usage reduction of at
least 2x**, depending on network conditions, the specific modules executed, and
time spent by the target host already doing useful work. Mitogen cannot speed
up a module once it is executing, it can only ensure the module executes as
quickly as possible.

* **A single SSH connection is used for each target host**, in addition to one
  sudo invocation per distinct user account. Subsequent playbook steps always
  reuse the same connection. This is much better than SSH multiplexing combined
  with pipelining, as significant state can be maintained in RAM between steps,
  and the system logs aren't filled with spam from repeat SSH and sudo
  invocations.

* **A single Python interpreter is used** per host and sudo account combination
  for the duration of the run, avoiding the repeat cost of invoking multiple
  interpreters and recompiling imports, saving 300-800 ms for every playbook
  step.

* Remote interpreters reuse Mitogen's module import mechanism, caching uploaded
  dependencies between steps at the host and user account level. As a
  consequence, **bandwidth usage is consistently an order of magnitude lower**
  compared to SSH pipelining, and around 5x fewer frames are required to
  traverse the wire for a run to complete successfully.

* **No writes to the target host's filesystem occur**, unless explicitly
  triggered by a playbook step. In all typical configurations, Ansible
  repeatedly rewrites and extracts ZIP files to multiple temporary directories
  on the target host. Since no temporary files are used, security issues
  relating to those files in cross-account scenarios are entirely avoided.


Demo
----

This demonstrates Ansible running a subset of the Mitogen integration tests
concurrent to an equivalent run using the extension.

.. raw:: html

    <video width="720" height="439" controls>
        <source src="http://k3.botanicus.net/tmp/ansible_mitogen.mp4" type="video/mp4">
    </video>


Testimonials
------------

* "With mitogen **my playbook runtime went from 45 minutes to just under 3
  minutes**. Awesome work!"

* "The runtime was reduced from **1.5 hours on 4 servers to just under 3
  minutes**. Thanks!"

* "Oh, performance improvement using Mitogen is *huge*. As mentioned before,
  running with Mitogen enables takes 7m36 (give or take a few seconds). Without
  Mitogen, the same run takes 19m49! **I'm not even deploying without Mitogen
  anymore** :)"

* "**Works like a charm**, thank you for your quick response"

* "I tried it out. **He is not kidding about the speed increase**."

* "I don't know what kind of dark magic @dmw_83 has done, but his Mitogen
  strategy took Clojars' Ansible runs from **14 minutes to 2 minutes**. I still
  can't quite believe it."


Installation
------------

.. caution::

    Thoroughly review the list of limitations before use, and **do not test the
    prototype in a live environment until this notice is removed**.

1. Verify Ansible 2.4 and Python 2.7 are listed in the output of ``ansible
   --version``
2. Download and extract https://github.com/dw/mitogen/archive/master.zip
3. Modify ``ansible.cfg``:

   .. code-block:: dosini

        [defaults]
        strategy_plugins = /path/to/mitogen-master/ansible_mitogen/plugins/strategy
        strategy = mitogen_linear

   The ``strategy`` key is optional. If omitted, you can set the
   ``ANSIBLE_STRATEGY=mitogen_linear`` environment variable on a per-run basis.
   Like ``mitogen_linear``, the ``mitogen_free`` strategy also exists to mimic
   the built-in ``free`` strategy.

4. Cross your fingers and try it.


Limitations
-----------

This is a proof of concept: issues below are exclusively due to code immaturity.

High Risk
~~~~~~~~~

* Transfer of large files using certain Ansible-internal APIs, such as
  triggered via the ``copy`` module, will cause corresponding memory and CPU
  spikes on both host and target machine, due to delivering the file as a
  single message. If many machines are targetted, the controller could easily
  exhaust available RAM. This will be fixed soon as it's likely to be tickled
  by common playbooks.

* No mechanism exists to bound the number of interpreters created during a run.
  For some playbooks that parameterize ``become_user`` over many accounts,
  resource exhaustion may be triggered on the target machine.


Low Risk
~~~~~~~~

* Only Ansible 2.4 is being used for development, with occasional tests under
  2.5, 2.3 and 2.2. It should be more than possible to fully support at least
  2.3, if not also 2.2.

* Only the ``sudo`` become method is available, however adding new methods is
  straightforward, and eventually at least ``su`` will be included.

* The extension's performance benefits do not scale perfectly linearly with the
  number of targets. This is a subject of ongoing investigation and
  improvements will appear in time.

* "Module Replacer" style modules are not yet supported. These rarely appear in
  practice, and light Github code searches failed to reveal many examples of
  them.


Behavioural Differences
-----------------------

* Ansible permits up to ``forks`` SSH connections to be setup simultaneously,
  whereas in Mitogen this is handled by a thread pool. Eventually this pool
  will become per-CPU, but meanwhile, a maximum of 16 SSH connections may be
  established simultaneously by default. This can be increased or decreased
  setting the ``MITOGEN_POOL_SIZE`` environment variable.

* Mitogen treats connection timeouts for the SSH and become steps of a task
  invocation separately, meaning that in some circumstances the configured
  timeout may appear to be doubled. This is since Mitogen internally treats the
  creation of an SSH account context separately to the creation of a sudo
  account context proxied via that SSH account.

  A future revision may detect a sudo account context created immediately
  following its parent SSH account, and try to emulate Ansible's existing
  timeout semantics.

* Local commands are executed in a reuseable Python interpreter created
  identically to interpreters used on remote hosts. At present only one such
  interpreter per ``become_user`` exists, and so only one local action may be
  executed simultaneously per local user account.

  Ansible usually permits up to ``ansible.cfg:forks`` simultaneous local
  actions. Any long-running local actions that execute for every target will
  experience artificial serialization, causing slowdown equivalent to
  `task_duration * num_targets`. This will be fixed soon.

* Asynchronous jobs exist only for the duration of a run, and cannot be
  queried by subsequent ansible-playbook invocations. Since the ability to
  query job IDs across runs relied on an implementation detail, it is not
  expected this will break any real-world playbooks.


How Modules Execute
-------------------

Ansible usually modifies, recompresses and reuploads modules every time they
run on a target, work that must be repeated by the controller for every
playbook step.

With the extension any modifications are done on the target, allowing pristine
copies of modules to be cached, reducing the necessity to re-transfer modules
for each invocation. Unmodified modules are uploaded once on first use and
cached in RAM for the remainder of the run.

**Binary**
    Native executables detected using a complex heuristic. Arguments are
    supplied as a JSON file whose path is the sole script parameter.

**Module Replacer**
    Python scripts detected by the presence of
    ``#<<INCLUDE_ANSIBLE_MODULE_COMMON>>`` appearing in their source. This type
    is not yet supported.

**New-Style**
    Python scripts detected by the presence of ``from ansible.module_utils.``
    appearing in their source. Arguments are supplied as JSON written to
    ``sys.stdin`` of the target interpreter.

**JSON_ARGS**
    Detected by the presence of ``INCLUDE_ANSIBLE_MODULE_JSON_ARGS`` appearing
    in the script source. The interpreter directive (``#!interpreter``) is
    adjusted to match the corresponding value of ``{{ansible_*_interpreter}}``
    if one is set. Arguments are supplied as JSON mixed into the script as a
    replacement for ``INCLUDE_ANSIBLE_MODULE_JSON_ARGS``.

**WANT_JSON**
    Detected by the presence of ``WANT_JSON`` appearing in the script source.
    The interpreter directive is adjusted as above. Arguments are supplied as a
    JSON file whose path is the sole script parameter.

**Old Style**
    Files not matching any of the above tests. The interpreter directive is
    adjusted as above. Arguments are supplied as a file whose path is the sole
    script parameter. The format of the file is ``"key=repr(value)[
    key2=repr(value2)[ ..]] "``.


Sample Profiles
---------------

Local VM connection
~~~~~~~~~~~~~~~~~~~

This demonstrates Mitogen vs. connection pipelining to a local VM, executing
the 100 simple repeated steps of ``run_hostname_100_times.yml`` from the
examples directory. Mitogen requires **43x less bandwidth and 4.25x less
time**.

.. image:: images/ansible/run_hostname_100_times.png


Kathmandu to Paris
~~~~~~~~~~~~~~~~~~

This is a full Django application playbook over a ~180ms link between Kathmandu
and Paris. Aside from large pauses where the host performs useful work, the
high latency of this link means Mitogen only manages a 1.7x speedup.

Many early roundtrips are due to inefficiencies in Mitogen's importer that will
be fixed over time, however the majority, comprising at least 10 seconds, are
due to idling while the host's previous result and next command are in-flight
on the network.

The initial extension lays groundwork for exciting structural changes to the
execution model: a future version will tackle latency head-on by delegating
some control flow to the target host, melding the performance and scalability
benefits of pull-based operation with the management simplicity of push-based
operation.

.. image:: images/ansible/costapp.png


SSH Variables
-------------

Matching Ansible's existing model, these variables are treated on a per-task
basis, causing establishment of additional reuseable interpreters as necessary
to match the configuration of each task.

This list will grow as more missing pieces are discovered.

* ``ansible_ssh_timeout``
* ``ansible_host``, ``ansible_ssh_host``
* ``ansible_user``, ``ansible_ssh_user``
* ``ansible_port``, ``ssh_port``
* ``ansible_ssh_executable``, ``ssh_executable``
* ``ansible_ssh_private_key_file``
* ``ansible_ssh_pass``, ``ansible_password`` (default: assume passwordless)
* ``ssh_args``, ``ssh_common_args``, ``ssh_extra_args``
* ``mitogen_ssh_discriminator``: if present, a string mixed into the key used
  to deduplicate connections. This permits intentional duplicate Mitogen
  connections to a single host, which is probably only useful for testing.


Sudo Variables
--------------

* ``ansible_python_interpreter``
* ``ansible_sudo_exe``, ``ansible_become_exe``
* ``ansible_sudo_user``, ``ansible_become_user`` (default: ``root``)
* ``ansible_sudo_pass``, ``ansible_become_pass`` (default: assume passwordless)
* ``sudo_flags``, ``become_flags``
* ansible.cfg: ``timeout``


Docker Variables
----------------

Note: Docker support is only intended for developer testing, it might disappear
entirely prior to a stable release.

* ansible_host


Chat on IRC
-----------

Some users and developers hang out on the
`#mitogen <https://webchat.freenode.net/?channels=mitogen>`_ channel on the
FreeNode IRC network.


Debugging
---------

Normally with Ansible, diagnostics and use of the :py:mod:`logging` package
output on the target machine are discarded. With Mitogen, all of this is
captured and returned to the host machine, where it can be viewed as desired
with ``-vvv``. Basic high level logs are produced with ``-vvv``, with logging
of all IO on the controller with ``-vvvv`` or higher.

Although use of standard IO and the logging package on the target is forwarded
to the controller, it is not possible to receive IO activity logs, as the
processs of receiving those logs would would itself generate IO activity. To
receive a complete trace of every process on every machine, file-based logging
is necessary. File-based logging can be enabled by setting
``MITOGEN_ROUTER_DEBUG=1`` in your environment.

When file-based logging is enabled, one file per context will be created on the
local machine and every target machine, as ``/tmp/mitogen.<pid>.log``.


Implementation Notes
--------------------

Interpreter Reuse
~~~~~~~~~~~~~~~~~

The extension aggressively reuses the single target Python interpreter to
execute every module. While this generally works well, it violates an unwritten
assumption regarding Ansible modules, and so it is possible a buggy module
could cause a run to fail, or for unrelated modules to interact with each other
due to bad hygiene.

Before reporting a bug relating to a module behaving incorrectly, please re-run
your playbook with ``-e mitogen_task_isolation=fork`` to see if the problem
abates. This may also be set on a per-task basis:

::

    - name: My task.
      broken_module:
        some_option: true
      vars:
        mitogen_task_isolation: fork

If forking fixes your problem, **please report a bug regardless**, as an
internal list can be updated to prevent users bumping into the same problem in
future.


Runtime Patches
~~~~~~~~~~~~~~~

Three small runtime patches are employed in ``strategy.py`` to hook into
desirable locations, in order to override uses of shell, the module executor,
and the mechanism for selecting a connection plug-in. While it is hoped the
patches can be avoided in future, for interesting versions of Ansible deployed
today this simply is not possible, and so they continue to be required.

The patches are concise and behave conservatively, including by disabling
themselves when non-Mitogen connections are in use. Additional third party
plug-ins are unlikely to attempt similar patches, so the risk to an established
configuration should be minimal.


Standard IO
~~~~~~~~~~~

Ansible uses pseudo TTYs for most invocations, to allow it to handle typing
passwords interactively, however it disables pseudo TTYs for certain commands
where standard input is required or ``sudo`` is not in use. Additionally when
SSH multiplexing is enabled, a string like ``Shared connection to localhost
closed\r\n`` appears in ``stderr`` of every invocation.

Mitogen does not naturally require either of these, as command output is
embedded within the SSH stream, and it can simply call :py:func:`pty.openpty`
in every location an interactive password must be typed.

A major downside to Ansible's behaviour is that ``stdout`` and ``stderr`` are
merged together into a single ``stdout`` variable, with carriage returns
inserted in the output by the TTY layer. However ugly, the extension emulates
all of this behaviour precisely, to avoid breaking playbooks that expect
certain text to appear in certain variables with certain linefeed characters.

See `Ansible#14377`_ for related discussion.

.. _Ansible#14377: https://github.com/ansible/ansible/issues/14377


Flag Emulation
~~~~~~~~~~~~~~

Mitogen re-parses ``sudo_flags``, ``become_flags``, and ``ssh_flags`` using
option parsers extracted from `sudo(1)` and `ssh(1)` in order to emulate their
equivalent semantics. This allows:

* robust support for common ``ansible.cfg`` tricks without reconfiguration,
  such as forwarding SSH agents across ``sudo`` invocations,
* reporting on conflicting flag combinations,
* reporting on unsupported flag combinations,
* internally special-casing certain behaviour (like recursive agent forwarding)
  without boring the user with the details,
* avoiding opening the extension up to untestable scenarios where users can
  insert arbitrary garbage between Mitogen and the components it integrates
  with,
* precise emulation by an alternative implementation, for example if Mitogen
  grew support for Paramiko.

