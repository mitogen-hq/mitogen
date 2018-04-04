
# ``tests/ansible`` Directory

This is an an organically growing collection of integration and regression
tests used for development and end-user bug reports.

It will be tidied up over time, meanwhile, the playbooks here are a useful
demonstrator for what does and doesn't work.



## Running Everything

```
ANSIBLE_STRATEGY=mitogen_linear ansible-playbook all.yml
```
