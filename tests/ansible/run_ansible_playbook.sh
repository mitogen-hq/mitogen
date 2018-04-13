#!/bin/bash
# Wrap ansible-playbook, setting up some test of the test environment.

# Used by delegate_to.yml to ensure "sudo -E" preserves environment.
export I_WAS_PRESERVED=1
export MITOGEN_MAX_INTERPRETERS=3

if [ "${ANSIBLE_STRATEGY:0:7}" = "mitogen" ]
then
    extra="-e is_mitogen=1"
else
    extra="-e is_mitogen=0"
fi

exec ansible-playbook $extra "$@"
