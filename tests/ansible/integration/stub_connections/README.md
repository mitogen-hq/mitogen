
# `stub_connections/`

The playbooks in this directory use stub implementations of various third party
tools (kubectl etc.) to verify arguments passed by Ansible to Mitogen and
subsequently onward to the tool result in something that looks sane.

These are bare minimum tests just to ensure sporadically tested connection
methods haven't broken in embarrasingly obvious ways.
