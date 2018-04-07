#!/bin/bash
# Wrap ansible-playbook, setting up some test of the test environment.

# Used by delegate_to.yml to ensure "sudo -E" preserves environment.
export I_WAS_PRESERVED=1

exec ansible-playbook "$@"
