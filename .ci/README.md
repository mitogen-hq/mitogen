
# `.ci`

This directory contains scripts for Continuous Integration platforms. Currently
GitHub Actions, but ideally they will also run on any Debian-like machine.

The scripts are usually split into `_install` and `_test` steps. The `_install`
step will damage your machine, the `_test` step will just run the tests the way
CI runs them.

There is a common library, `ci_lib.py`, which just centralized a bunch of
random macros and also environment parsing.

Some of the scripts allow you to pass extra flags through to the component
under test, e.g. `../../.ci/ansible_tests.py -vvv` will run with verbose.

Hack these scripts until your heart is content. There is no pride to be found
here, just necessity.


### `ci_lib.run_batches()`

There are some weird looking functions to extract more paralellism from the
build. The above function takes lists of strings, arranging for the strings in
each list to run in order, but for the lists to run in parallel. That's great
for doing `setup.py install` while pulling a Docker container, for example.


### Environment Variables

* `MITOGEN_TEST_DISTRO_SPECS`: a space delimited list of distro specs to run
  the tests against. (e.g. `centos6 ubuntu2004-py3*4`). Each spec determines
  the Linux distribution, target Python interepreter & number of instances.
  Only distributions with a pre-built Linux container image can be used.
    * `debian-py3`: when generating Ansible inventory file, set
      `ansible_python_interpreter` to `python3`, i.e. run a test where the
      target interpreter is Python 3.
    * `debian*16`: generate 16 Docker containers running Debian. Also works
      with -py3.

* `MITOGEN_TEST_IMAGE_TEMPLATE`: specifies the Linux container image name,
  and hence the container registry used for test targets.
