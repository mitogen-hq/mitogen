#!/bin/bash -ex
# Run some invocations of DebOps.

TMPDIR="/tmp/debops-$$"
TRAVIS_BUILD_DIR="${TRAVIS_BUILD_DIR:-`pwd`}"
TARGET_COUNT="${TARGET_COUNT:-4}"
MITOGEN_TEST_DISTRO=debian  # Naturally DebOps only supports Debian.

export PYTHONPATH="${PYTHONPATH}:${TRAVIS_BUILD_DIR}"

function on_exit()
{
    echo travis_fold:start:cleanup
    [ "$KEEP" ] || {
        rm -rf "$TMPDIR" || true
        for i in $(seq $TARGET_COUNT)
        do
            docker kill target$i || true
        done
    }
    echo travis_fold:end:cleanup
}

trap on_exit EXIT
mkdir "$TMPDIR"


echo travis_fold:start:job_setup
pip install -qqqU debops==0.7.2 ansible==2.4.3.0
debops-init "$TMPDIR/project"
cd "$TMPDIR/project"

cat > .debops.cfg <<-EOF
[ansible defaults]
strategy_plugins = ${TRAVIS_BUILD_DIR}/ansible_mitogen/plugins/strategy
strategy = mitogen_linear
EOF

cat > ansible/inventory/group_vars/debops_all_hosts.yml <<-EOF
ansible_python_interpreter: /usr/bin/python2.7

ansible_user: mitogen__has_sudo_pubkey
ansible_become_pass: has_sudo_pubkey_password
ansible_ssh_private_key_file: ${TRAVIS_BUILD_DIR}/tests/data/docker/mitogen__has_sudo_pubkey.key

# Speed up slow DH generation.
dhparam__bits: ["128", "64"]
EOF

DOCKER_HOSTNAME="$(python ${TRAVIS_BUILD_DIR}/tests/show_docker_hostname.py)"

for i in $(seq $TARGET_COUNT)
do
    port=$((2200 + $i))
    docker run \
        --rm \
        --detach \
        --publish 0.0.0.0:$port:22/tcp \
        --name=target$i \
        d2mw/mitogen-${MITOGEN_TEST_DISTRO}-test

    echo \
        target$i \
        ansible_host=$DOCKER_HOSTNAME \
        ansible_port=$port \
        >> ansible/inventory/hosts
done

echo
echo --- ansible/inventory/hosts: ----
cat ansible/inventory/hosts
echo ---

echo travis_fold:end:job_setup


echo travis_fold:start:first_run
/usr/bin/time debops common
echo travis_fold:end:first_run


echo travis_fold:start:second_run
/usr/bin/time debops common
echo travis_fold:end:second_run
