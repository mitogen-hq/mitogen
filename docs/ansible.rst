
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

.. _Ansible: https://www.ansible.com/

.. _Bug reports: https://goo.gl/yLKZiJ


Overview
--------

You should **expect a 1.25x - 7x speedup** and a **CPU usage reduction of at
least 2x**, depending on network conditions, the specific modules executed, and
time spent by the target host already doing useful work. Mitogen cannot speed
up a module once it is executing, it can only ensure the module executes as
quickly as possible.

.. raw:: html

    <div style="float:right; border:1px solid silver;margin-left: 16px;">
    <iframe src="https://www.kickstarter.com/projects/548438714/mitogen-extension-for-ansible/widget/card.html?v=2" width="220" height="420" frameborder="0" scrolling="no" target="_blank"></iframe>
    </div>

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
        strategy = mitogen

   The ``strategy`` key is optional. If omitted, you can set the
   ``ANSIBLE_STRATEGY=mitogen`` environment variable on a per-run basis.

4. Cross your fingers and try it.


Limitations
-----------

This is a proof of concept: issues below are exclusively due to code immaturity.

High Risk
~~~~~~~~~

* Connection establishment is single-threaded until more pressing issues are
  solved. To evaluate performance, target only one host. Many hosts still work,
  the first playbook step will simply run unnecessarily slowly.

* `Asynchronous Actions And Polling
  <https://docs.ansible.com/ansible/latest/playbooks_async.html>`_ has received
  minimal testing.

* For now only **built-in Python command modules work**, however almost all
  modules shipped with Ansible are Python-based.

* Transfer of large (i.e. GB-sized) files using certain Ansible-internal APIs,
  such as triggered via the ``copy`` module, will cause corresponding temporary
  memory and CPU spikes on both host and target machine, due to delivering the
  file as a single large message, and quadratic buffer management in both
  sender and receiver. If many machines are targetted with a large file, the
  host machine could easily exhaust available RAM. This will be fixed soon as
  it's likely to be tickled by common playbook use cases.

* Situations may exist where the playbook's execution conditions are not
  respected, however ``delegate_to``, ``connection: local``, ``become``,
  ``become_user``, and ``local_action`` have all been tested.

* Only Ansible 2.4 is being used for development, with occasional tests under
  2.3 and 2.2. It should be more than possible to fully support at least 2.3,
  if not also 2.2.


Low Risk
~~~~~~~~

* Only UNIX machines running Python 2.x are supported, Windows will come later.

* Only the ``sudo`` become method is available, however adding new methods is
  straightforward, and eventually at least ``su`` will be included.

* The only supported strategy is ``linear``, which is Ansible's default.

* In some cases ``remote_tmp`` may not be respected.

* Ansible defaults to requiring pseudo TTYs for most SSH invocations, in order
  to allow it to handle ``sudo`` with ``requiretty`` enabled, however it
  disables pseudo TTYs for certain commands where standard input is required or
  ``sudo`` is not in use. Mitogen does not require this, as it can simply call
  :py:func:`pty.openpty` from the SSH user account during ``sudo`` setup.

  A major downside to Ansible's default is that stdout and stderr of any
  resulting executed command are merged, with additional carriage return
  characters synthesized in the output by the TTY layer. Neither of these
  problems are apparent using the Mitogen extension, which may break some
  playbooks.

  A future version will emulate Ansible's behaviour, once it is clear precisely
  what that behaviour is supposed to be. See `Ansible#14377`_ for related
  discussion.

.. _Ansible#14377: https://github.com/ansible/ansible/issues/14377


Behavioural Differences
-----------------------

* Mitogen treats connection timeouts for the SSH and become steps of a task
  invocation separately, meaning that in some circumstances the configured
  timeout may appear to be doubled. This is since Mitogen internally treats the
  creation of an SSH account context separately to the creation of a sudo
  account context proxied via that SSH account.

  A future revision may detect a sudo account context created immediately
  following its parent SSH account, and try to emulate Ansible's existing
  timeout semantics.

* Normally with Ansible, diagnostics and use of the :py:mod:`logging` package
  output on the target machine are discarded. With Mitogen, all of this is
  captured and returned to the host machine, where it can be viewed as desired
  with ``-vvv``.

* Ansible with SSH multiplexing enabled causes a string like ``Shared
  connection to host closed`` to appear in ``stderr`` output of every executed
  command. This never manifests with the Mitogen extension.

* Asynchronous support is very primitive, and jobs execute in a thread of the
  target Python interpreter. This will fixed shortly.


Demo
----

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

This list will grow as more missing pieces are discovered.

* ansible_python_interpreter
* ansible_ssh_timeout
* ansible_host, ansible_ssh_host
* ansible_user, ansible_ssh_user
* ansible_port, ssh_port
* ansible_ssh_executable, ssh_executable
* ansible_ssh_private_key_file
* ansible_ssh_pass, ansible_password (default: assume passwordless)
* ssh_args, ssh_common_args, ssh_extra_args


Sudo Variables
--------------

* ansible_python_interpreter
* ansible_sudo_exe, ansible_become_exe
* ansible_sudo_user, ansible_become_user (default: root)
* ansible_sudo_pass, ansible_become_pass (default: assume passwordless)
* sudo_flags, become_flags
* ansible.cfg: timeout


Chat on IRC
-----------

Some users and developers hang out on the
`#mitogen <https://webchat.freenode.net/?channels=mitogen>`_ channel on the
FreeNode IRC network.


Debugging
---------

Mitogen's logs are integrated into Ansible's display framework. Basic high
level debug logs are produced with ``-vvv``, with logging of all IO activity on
the controller machine when ``-vvvv`` or higher is specified.

Although any use of standard IO and the logging package on remote machines is
forwarded to the controller machine, it is not possible to receive logs of all
IO activity, as the processs of receiving those logs would would in turn
generate more IO activity. To receive a complete trace of every process on
every machine, file-based logging is required. File-based logging can be
enabled by setting ``MITOGEN_ROUTER_DEBUG=1`` in your environment.

When file-based logging is enabled, one file per context will be created on the
local machine and every target machine, as ``/tmp/mitogen.<pid>.log``.


Implementation Notes
--------------------

Interpreter Reuse
~~~~~~~~~~~~~~~~~

The extension aggressively reuses the single target Python interpreter to
execute every module. While this works well, it violates an unwritten
assumption regarding Ansible modules, and so it is possible a buggy module
could cause a run to fail, or for unrelated modules to interact with each other
due to bad hygiene. Mitigations (such as forking) will be added as necessary if
problems of this sort ever actually manfest.

Patches
~~~~~~~

Three small runtime patches are employed to hook into Ansible in desirable
locations, in order to override uses of shell, the module executor, and the
mechanism for selecting a connection plug-in. While it is hoped the patches can
be avoided in future, for interesting versions of Ansible deployed today this
simply is not possible, and so they continue to be required.

The patches are concise and behave conservatively, including by disabling
themselves when non-Mitogen connections are in use. Additional third party
plug-ins are unlikely to attempt similar patches, so the risk to an established
configuration should be minimal.

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

