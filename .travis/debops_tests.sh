#!/bin/bash -ex
# Run some invocations of DebOps.

TMPDIR="/tmp/debops-$$"
TRAVIS_BUILD_DIR="${TRAVIS_BUILD_DIR:-`pwd`}"

function on_exit()
{
    [ "$KEEP" ] || {
        rm -rvf "$TMPDIR" || true
        docker kill target || true
    }
}

trap on_exit EXIT
mkdir "$TMPDIR"

docker run --rm --detach --name=target d2mw/mitogen-test /bin/sleep 86400

pip install -U debops==0.7.2 ansible==2.4.3.0
debops-init "$TMPDIR/project"
cd "$TMPDIR/project"

cat > .debops.cfg <<-EOF
[ansible defaults]
strategy_plugins = ${TRAVIS_BUILD_DIR}/ansible_mitogen/plugins/strategy
strategy = mitogen_linear
EOF

cat > ansible/inventory/host_vars/target.yml <<-EOF
ansible_connection: docker
ansible_python_interpreter: /usr/bin/python2.7

# Speed up slow DH generation.
dhparam__bits: [128, 64]
EOF

echo target >> ansible/inventory/hosts
debops common
