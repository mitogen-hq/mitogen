
from __future__ import absolute_import
from __future__ import print_function

import atexit
import os
import shlex
import shutil
import subprocess
import sys
import tempfile

try:
    import urlparse
except ImportError:
    import urllib.parse as urlparse

os.chdir(
    os.path.join(
        os.path.dirname(__file__),
        '..'
    )
)


#
# check_output() monkeypatch cutpasted from testlib.py
#

def subprocess__check_output(*popenargs, **kwargs):
    # Missing from 2.6.
    process = subprocess.Popen(stdout=subprocess.PIPE, *popenargs, **kwargs)
    output, _ = process.communicate()
    retcode = process.poll()
    if retcode:
        cmd = kwargs.get("args")
        if cmd is None:
            cmd = popenargs[0]
        raise subprocess.CalledProcessError(retcode, cmd)
    return output

if not hasattr(subprocess, 'check_output'):
    subprocess.check_output = subprocess__check_output


# ------------------

def have_apt():
    proc = subprocess.Popen('apt --help >/dev/null 2>/dev/null', shell=True)
    return proc.wait() == 0


def have_docker():
    proc = subprocess.Popen('docker info >/dev/null 2>/dev/null', shell=True)
    return proc.wait() == 0


# -----------------

# Force stdout FD 1 to be a pipe, so tools like pip don't spam progress bars.

if 'TRAVIS_HOME' in os.environ:
    proc = subprocess.Popen(
        args=['stdbuf', '-oL', 'cat'],
        stdin=subprocess.PIPE
    )

    os.dup2(proc.stdin.fileno(), 1)
    os.dup2(proc.stdin.fileno(), 2)

    def cleanup_travis_junk(stdout=sys.stdout, stderr=sys.stderr, proc=proc):
        stdout.close()
        stderr.close()
        proc.terminate()

    atexit.register(cleanup_travis_junk)

# -----------------

def _argv(s, *args):
    if args:
        s %= args
    return shlex.split(s)


def run(s, *args, **kwargs):
    argv = ['/usr/bin/time', '--'] + _argv(s, *args)
    print('Running: %s' % (argv,))
    ret = subprocess.check_call(argv, **kwargs)
    print('Finished running: %s' % (argv,))
    return ret


def run_batches(batches):
    combine = lambda batch: 'set -x; ' + (' && '.join(
        '( %s; )' % (cmd,)
        for cmd in batch
    ))

    procs = [
        subprocess.Popen(combine(batch), shell=True)
        for batch in batches
    ]
    assert [proc.wait() for proc in procs] == [0] * len(procs)


def get_output(s, *args, **kwargs):
    argv = _argv(s, *args)
    print('Running: %s' % (argv,))
    return subprocess.check_output(argv, **kwargs)


def exists_in_path(progname):
    return any(os.path.exists(os.path.join(dirname, progname))
               for dirname in os.environ['PATH'].split(os.pathsep))


class TempDir(object):
    def __init__(self):
        self.path = tempfile.mkdtemp(prefix='mitogen_ci_lib')
        atexit.register(self.destroy)

    def destroy(self, rmtree=shutil.rmtree):
        rmtree(self.path)


class Fold(object):
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        print('travis_fold:start:%s' % (self.name))

    def __exit__(self, _1, _2, _3):
        print('')
        print('travis_fold:end:%s' % (self.name))


os.environ.setdefault('ANSIBLE_STRATEGY',
    os.environ.get('STRATEGY', 'mitogen_linear'))
ANSIBLE_VERSION = os.environ.get('VER', '2.6.2')
GIT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DISTRO = os.environ.get('DISTRO', 'debian')
DISTROS = os.environ.get('DISTROS', 'debian centos6 centos7').split()
TARGET_COUNT = int(os.environ.get('TARGET_COUNT', '2'))
BASE_PORT = 2200
TMP = TempDir().path


# We copy this out of the way to avoid random stuff modifying perms in the Git
# tree (like git pull).
src_key_file = os.path.join(GIT_ROOT,
    'tests/data/docker/mitogen__has_sudo_pubkey.key')
key_file = os.path.join(TMP,
    'mitogen__has_sudo_pubkey.key')
shutil.copyfile(src_key_file, key_file)
os.chmod(key_file, int('0600', 8))


os.environ['PYTHONDONTWRITEBYTECODE'] = 'x'
os.environ['PYTHONPATH'] = '%s:%s' % (
    os.environ.get('PYTHONPATH', ''),
    GIT_ROOT
)

def get_docker_hostname():
    url = os.environ.get('DOCKER_HOST')
    if url in (None, 'http+docker://localunixsocket'):
        return 'localhost'

    parsed = urlparse.urlparse(url)
    return parsed.netloc.partition(':')[0]


def image_for_distro(distro):
    return 'mitogen/%s-test' % (distro.partition('-')[0],)


def make_containers(name_prefix='', port_offset=0):
    docker_hostname = get_docker_hostname()
    firstbit = lambda s: (s+'-').split('-')[0]
    secondbit = lambda s: (s+'-').split('-')[1]

    i = 1
    lst = []

    for distro in DISTROS:
        distro, star, count = distro.partition('*')
        if star:
            count = int(count)
        else:
            count = 1

        for x in range(count):
            lst.append({
                "distro": firstbit(distro),
                "name": name_prefix + ("target-%s-%s" % (distro, i)),
                "hostname": docker_hostname,
                "port": BASE_PORT + i + port_offset,
                "python_path": (
                    '/usr/bin/python3'
                    if secondbit(distro) == 'py3'
                    else '/usr/bin/python'
                )
            })
            i += 1

    return lst


def start_containers(containers):
    if os.environ.get('KEEP'):
        return

    run_batches([
        [
            "docker rm -f %(name)s || true" % container,
            "docker run "
                "--rm "
                "--detach "
                "--privileged "
                "--cap-add=SYS_PTRACE "
                "--publish 0.0.0.0:%(port)s:22/tcp "
                "--hostname=%(name)s "
                "--name=%(name)s "
                "mitogen/%(distro)s-test "
            % container
        ]
        for container in containers
    ])
    return containers


def dump_file(path):
    print()
    print('--- %s ---' % (path,))
    print()
    with open(path, 'r') as fp:
        print(fp.read().rstrip())
    print('---')
    print()


# SSH passes these through to the container when run interactively, causing
# stdout to get messed up with libc warnings.
os.environ.pop('LANG', None)
os.environ.pop('LC_ALL', None)
