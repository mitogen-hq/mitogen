
Ansible Extension
=================

.. image:: images/ansible/cell_division.png
    :align: right

An experimental extension to `Ansible`_ is included that implements host
connections over Mitogen, replacing embedded shell invocations with pure-Python
equivalents invoked over SSH via highly efficient remote procedure calls. No
changes are required to the target hosts.

The extension isn't nearly in a generally dependable state yet, however it
already works well enough for testing against real-world playbooks. `Bug
reports`_ in this area are very welcome – Ansible is a huge beast, and only
significant testing will prove the extension's soundness.

.. _Ansible: https://www.ansible.com/

.. _Bug reports: https://goo.gl/yLKZiJ


Overview
--------

You should expect a general speedup ranging from 1.5x to 5x depending on
network conditions, the specific modules executed, and time spent by the target
host already doing useful work. Mitogen cannot speed up a module once it is
executing, it can only ensure the module executes as quickly as possible.

* A single SSH connection is used for each target host, in addition to one sudo
  invocation per distinct user account. Subsequent playbook steps always reuse
  the same connection. This is much better than SSH multiplexing combined with
  pipelining, as significant state can be maintained in RAM between steps, and
  the system logs aren't filled with spam from repeat SSH and sudo invocations.

* A single Python interpreter is used per host and sudo account combination for
  the duration of the run, avoiding the repeat cost of invoking multiple
  interpreters and recompiling imports, saving 300-1000 ms for every playbook
  step.

* Remote interpreters reuse Mitogen's module import mechanism, caching uploaded
  dependencies between steps at the host and user account level. As a
  consequence, bandwidth usage is consistently an order of magnitude lower
  compared to SSH pipelining, and around 5x fewer frames are required to
  traverse the wire for a run to complete successfully.

* No writes to the target host's filesystem occur, unless explicitly
  triggered by a playbook step. In all typical configurations, Ansible
  repeatedly rewrites and extracts ZIP files to multiple temporary directories
  on the target host. Since no temporary files are used, security issues
  relating to those files in cross-account scenarios are entirely avoided.


Limitations
-----------

This is a proof of concept: issues below are exclusively due to code immaturity.

* Only UNIX machines running Python 2.x are supported, Windows will come later.

* Only the ``sudo`` become method is available, however adding new methods is
  straightforward, and eventually at least ``su`` will be included.

* The only supported strategy is ``linear``, which is Ansible's default.

* The remote interpreter is temporarily hard-wired to ``/usr/bin/python``,
  matching Ansible's default. The ``ansible_python_interpreter`` variable is
  ignored.

* Connection establishment is single-threaded until more pressing issues are
  solved. To evaluate performance, target only one host. Many hosts still work,
  the first playbook step will simply run unnecessarily slowly.

* For now only Python command modules work, however almost all modules shipped
  with Ansible are Python-based.

* Interaction with modules employing special action plugins is mostly untested,
  except for the ``synchronize`` module.

* More situations likely exist where the playbook's execution conditions are
  not respected (``delegate_to``, ``connection: local``, etc.).


Configuration
-------------

1. Ensure the host machine is using Python 2.x for Ansible by verifying the
   output of ``ansible --version``
2. ``python2 -m pip install git+https://github.com/dw/mitogen.git`` **on the
   host machine only**.
3. ``python2 -c 'import ansible_mitogen as a; print a.__path__'``
4. Add ``strategy_plugins = /path/to/../ansible_mitogen/strategy`` using the
   path from above to the ``[defaults]`` section of ``ansible.cfg``.
5. Add ``strategy = mitogen`` to the ``[defaults]`` section of ``ansible.cfg``.
6. Cross your fingers and try it out.


Demo
----

Local VM connection
~~~~~~~~~~~~~~~~~~~

This demonstrates Mitogen vs. connection pipelining to a local VM, executing
the 100 simple repeated steps of ``run_hostname_100_times.yml`` from the
examples directory. Mitogen uses 43x less bandwidth and 4.25x less time.

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
some control flow to the target host.

.. image:: images/ansible/costapp.png


SSH Variables
-------------

This list will grow as more missing pieces are discovered.

* remote_addr
* remote_user
* ssh_port
* ssh_path
* password (default: assume passwordless)


Sudo Variables
--------------

* username (default: root)
* password (default: assume passwordless)


Debugging
---------

See :ref:`logging-env-vars` in the Getting Started guide for environment
variables that activate debug logging.
