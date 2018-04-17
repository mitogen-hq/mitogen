#!/bin/bash -ex
# Run tests/ansible/integration/all.yml under Ansible and Ansible-Mitogen

TRAVIS_BUILD_DIR="${TRAVIS_BUILD_DIR:-`pwd`}"
TMPDIR="/tmp/ansible-tests-$$"
ANSIBLE_VERSION="${ANSIBLE_VERSION:-2.4.3.0}"
MITOGEN_TEST_DISTRO="${MITOGEN_TEST_DISTRO:-debian}"

export PYTHONPATH="${PYTHONPATH}:${TRAVIS_BUILD_DIR}"

# SSH passes these through to the container when run interactively, causing
# stdout to get messed up with libc warnings.
unset LANG LC_ALL

function on_exit()
{
    rm -rf "$TMPDIR"
    docker kill target || true
}

trap on_exit EXIT
mkdir "$TMPDIR"


echo travis_fold:start:docker_setup
DOCKER_HOSTNAME="$(python ${TRAVIS_BUILD_DIR}/tests/show_docker_hostname.py)"

docker run \
    --rm \
    --detach \
    --publish 0.0.0.0:2201:22/tcp \
    --name=target \
    d2mw/mitogen-${MITOGEN_TEST_DISTRO}-test
echo travis_fold:end:docker_setup


echo travis_fold:start:job_setup
pip install -U ansible=="${ANSIBLE_VERSION}"
cd ${TRAVIS_BUILD_DIR}/tests/ansible

chmod go= ${TRAVIS_BUILD_DIR}/tests/data/docker/mitogen__has_sudo_pubkey.key
echo \
    target \
    ansible_host=$DOCKER_HOSTNAME \
    ansible_port=2201 \
    ansible_python_interpreter=/usr/bin/python2.7 \
    ansible_user=mitogen__has_sudo_nopw \
    ansible_password=has_sudo_nopw_password \
    >> ${TMPDIR}/hosts

# Build the binaries.
make -C ${TRAVIS_BUILD_DIR}/tests/ansible

sudo apt install -y sshpass bsdmainutils
xxd ${TRAVIS_BUILD_DIR}/tests/ansible/lib/modules/custom_binary_producing_junk

echo travis_fold:end:job_setup


echo travis_fold:start:mitogen_linear
/usr/bin/time ./mitogen_ansible_playbook.sh \
    integration/all.yml \
    -vvv \
    -i "${TMPDIR}/hosts"
echo travis_fold:end:mitogen_linear


echo travis_fold:start:vanilla_ansible
/usr/bin/time ./run_ansible_playbook.sh \
    integration/all.yml \
    -vvv \
    -i "${TMPDIR}/hosts"
echo travis_fold:end:vanilla_ansible
