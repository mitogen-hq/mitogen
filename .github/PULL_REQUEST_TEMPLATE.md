
Thanks for creating a PR! Here's a quick checklist to pay attention to:

* [ ] Add an entry to `docs/changelog.rst` as appropriate.
      E.g.
      ```rst
      - :gh:issue:1234 Fix leaky drain pipe
      ```
      Some changes don't need a change log entry (e.g. CI fixes), but if in doubt please include one.

* [ ] Update relevant documention if introducing new features, or a change to semantics.
      E.g. has a parameter has been added, or semantics modified somehow? Please ensure relevant documentation is updated in `docs/ansible.rst`, and `docs/api.rst`.

* [ ] For a bug fix or new functionality, please include  at least a basic test.
      For pure mitogen this will be in `tests/*.py`, for ansible_mitogen it will be in `tests/ansible/`?

* [ ] For a new connection method, please try to stub out the implementation as in `tests/data/stubs/`.
      This is so that construction can be tested without having a working configuration.

