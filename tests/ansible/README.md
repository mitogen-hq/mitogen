
# ``tests/ansible`` Directory

This is an an organically growing collection of integration and regression
tests used for development and end-user bug reports.

It will be tidied up over time, meanwhile, the playbooks here are a useful
demonstrator for what does and doesn't work.


## ``run_ansible_playbook.sh``

This is necessary to set some environment variables used by future tests, as
there appears to be no better way to inject them into the top-level process
environment before the Mitogen connection process forks.


## Running Everything

```
ANSIBLE_STRATEGY=mitogen_linear ./run_ansible_playbook.sh all.yml
```
