
Thanks for creating a PR! Here's a quick checklist to pay attention to:

* Please add an entry to docs/changelog.rst as appropriate.

* Has some new parameter been added or semantics modified somehow? Please
  ensure relevant documentation is updated in docs/ansible.rst and
  docs/api.rst.

* If it's for new functionality, is there at least a basic test in either
  tests/ or tests/ansible/ covering it?

* If it's for a new connection method, please try to stub out the
  implementation as in tests/data/stubs/, so that construction can be tested
  without having a working configuration.

