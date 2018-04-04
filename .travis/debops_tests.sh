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


echo travis_fold:start:docker_setup
docker run --rm --detach --name=target d2mw/mitogen-test /bin/sleep 86400
echo travis_fold:end:docker_setup


echo travis_fold:start:job_setup
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
dhparam__bits: ["128", "64"]
EOF

echo target >> ansible/inventory/hosts
echo travis_fold:end:job_setup


echo travis_fold:start:first_run
/usr/bin/time debops common
echo travis_fold:end:first_run


echo travis_fold:start:second_run
/usr/bin/time debops common
echo travis_fold:end:second_run
