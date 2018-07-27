#!/bin/bash -ex
# Run tests/ansible/all.yml under Ansible and Ansible-Mitogen

TRAVIS_BUILD_DIR="${TRAVIS_BUILD_DIR:-`pwd`}"
TMPDIR="/tmp/ansible-tests-$$"
ANSIBLE_VERSION="${VER:-2.6.1}"
export ANSIBLE_STRATEGY="${STRATEGY:-mitogen_linear}"
DISTRO="${DISTRO:-debian}"

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
    mitogen/${DISTRO}-test
echo travis_fold:end:docker_setup


echo travis_fold:start:job_setup
pip install ansible=="${ANSIBLE_VERSION}"
cd ${TRAVIS_BUILD_DIR}/tests/ansible

chmod go= ${TRAVIS_BUILD_DIR}/tests/data/docker/mitogen__has_sudo_pubkey.key
echo '[test-targets]' > ${TMPDIR}/hosts
echo \
    target \
    ansible_host=$DOCKER_HOSTNAME \
    ansible_port=2201 \
    ansible_user=mitogen__has_sudo_nopw \
    ansible_password=has_sudo_nopw_password \
    >> ${TMPDIR}/hosts

# Build the binaries.
make -C ${TRAVIS_BUILD_DIR}/tests/ansible

[ ! "$(type -p sshpass)" ] && sudo apt install -y sshpass

echo travis_fold:end:job_setup


echo travis_fold:start:ansible
/usr/bin/time ./run_ansible_playbook.sh \
    all.yml \
    -i "${TMPDIR}/hosts" "$@"
echo travis_fold:end:ansible
