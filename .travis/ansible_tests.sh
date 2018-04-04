#!/bin/bash -ex
# Run tests/ansible/integration/all.yml under Ansible and Ansible-Mitogen

TRAVIS_BUILD_DIR="${TRAVIS_BUILD_DIR:-`pwd`}"
TMPDIR="/tmp/ansible-tests-$$"
ANSIBLE_VERSION="${ANSIBLE_VERSION:-2.4.3.0}"

function on_exit()
{
    rm -rf "$TMPDIR"
    docker kill target || true
}

trap on_exit EXIT
mkdir "$TMPDIR"


echo travis_fold:start:docker_setup
docker run --rm --detach --name=target d2mw/mitogen-test /bin/sleep 86400
echo travis_fold:end:docker_setup


echo travis_fold:start:job_setup
pip install -U ansible==${ANSIBLE_VERSION}"
cd ${TRAVIS_BUILD_DIR}/tests/ansible

cat >> ${TMPDIR}/hosts <<-EOF
localhost
target ansible_connection=docker ansible_python_interpreter=/usr/bin/python2.7
EOF
echo travis_fold:end:job_setup


echo travis_fold:start:mitogen_linear
ANSIBLE_STRATEGY=mitogen_linear /usr/bin/time ansible-playbook \
    integration/all.yml \
    -i "${TMPDIR}/hosts"
echo travis_fold:end:mitogen_linear


echo travis_fold:start:vanilla_ansible
/usr/bin/time ansible-playbook \
    integration/all.yml \
    -i "${TMPDIR}/hosts"
echo travis_fold:end:vanilla_ansible
