#!/bin/bash -ex
# Run some invocations of DebOps.

TMPDIR="/tmp/debops-$$"
TRAVIS_BUILD_DIR="${TRAVIS_BUILD_DIR:-`pwd`}"

function on_exit()
{
    echo travis_fold:start:cleanup
    [ "$KEEP" ] || {
        rm -rvf "$TMPDIR" || true
        docker kill target || true
    }
    echo travis_fold:end:cleanup
}

trap on_exit EXIT
mkdir "$TMPDIR"


echo travis_fold:start:docker_setup
docker run --rm --detach --name=target1 d2mw/mitogen-test /bin/sleep 86400
docker run --rm --detach --name=target2 d2mw/mitogen-test /bin/sleep 86400
docker run --rm --detach --name=target3 d2mw/mitogen-test /bin/sleep 86400
docker run --rm --detach --name=target4 d2mw/mitogen-test /bin/sleep 86400
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

cat > ansible/inventory/group_vars/debops_all_hosts.yml <<-EOF
ansible_connection: docker
ansible_python_interpreter: /usr/bin/python2.7

# Speed up slow DH generation.
dhparam__bits: ["128", "64"]
EOF

cat > ansible/inventory/hosts <<-EOF
target1
target2
target3
target4
EOF
echo travis_fold:end:job_setup


echo travis_fold:start:first_run
/usr/bin/time debops common
echo travis_fold:end:first_run


echo travis_fold:start:second_run
/usr/bin/time debops common
echo travis_fold:end:second_run
