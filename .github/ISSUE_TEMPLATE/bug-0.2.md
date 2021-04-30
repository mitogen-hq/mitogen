---
name: Mitogen 0.2.x bug report
about: Report a bug in Mitogen 0.2.x (for Ansible 2.5, 2.6, 2.7, 2.8, or 2.9)
title: ''
labels: affects-0.2, bug
assignees: ''

---

Please drag-drop large logs as text file attachments.

Feel free to write an issue in your preferred format, however if in doubt, use
the following checklist as a guide for what to include.

* Which version of Ansible are you running?
* Is your version of Ansible patched in any way?
* Are you running with any custom modules, or `module_utils` loaded?

* Have you tried the latest master version from Git?
* Do you have some idea of what the underlying problem may be?
  https://mitogen.networkgenomics.com/ansible_detailed.html#common-problems has
  instructions to help figure out the likely cause and how to gather relevant
  logs.
* Mention your host and target OS and versions
* Mention your host and target Python versions
* If reporting a performance issue, mention the number of targets and a rough
  description of your workload (lots of copies, lots of tiny file edits, etc.)
* If reporting a crash or hang in Ansible, please rerun with -vvv and include
  200 lines of output around the point of the error, along with a full copy of
  any traceback or error text in the log. Beware "-vvv" may include secret
  data! Edit as necessary before posting.
* If reporting any kind of problem with Ansible, please include the Ansible
  version along with output of "ansible-config dump --only-changed".
