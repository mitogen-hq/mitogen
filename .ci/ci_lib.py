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

_print = print
def print(*args, **kwargs):
    file = kwargs.get('file', sys.stdout)
    flush = kwargs.pop('flush', False)
    _print(*args, **kwargs)
    if flush:
        file.flush()


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

def have_brew():
    proc = subprocess.Popen('brew help >/dev/null 2>/dev/null', shell=True)
    return proc.wait() == 0


def have_docker():
    proc = subprocess.Popen('docker info >/dev/null 2>/dev/null', shell=True)
    return proc.wait() == 0


def _argv(s, *args):
    """Interpolate a command line using *args, return an argv style list.

    >>> _argv('git commit -m "Use frobnicate 2.0 (fixes #%d)"', 1234)
    ['git', commit', '-m', 'Use frobnicate 2.0 (fixes #1234)']
    """
    if args:
        s %= args
    return shlex.split(s)


def run(s, *args, **kwargs):
    """ Run a command, with arguments

    >>> rc = run('echo "%s %s"', 'foo', 'bar')
    Running: ['echo', 'foo bar']
    foo bar
    Finished running: ['echo', 'foo bar']
    >>> rc
    0
    """
    argv = _argv(s, *args)
    print('Running: %s' % (argv,), flush=True)
    try:
        ret = subprocess.check_call(argv, **kwargs)
        print('Finished running: %s' % (argv,), flush=True)
    except Exception:
        print('Exception occurred while running: %s' % (argv,), file=sys.stderr, flush=True)
        raise

    return ret


def combine(batch):
    """
    >>> combine(['ls -l', 'echo foo'])
    'set -x; ( ls -l; ) && ( echo foo; )'
    """
    return 'set -x; ' + (' && '.join(
        '( %s; )' % (cmd,)
        for cmd in batch
    ))


def throttle(batch, pause=1):
    """
    Add pauses between commands in a batch

    >>> throttle(['echo foo', 'echo bar', 'echo baz'])
    ['echo foo', 'sleep 1', 'echo bar', 'sleep 1', 'echo baz']
    """
    def _with_pause(batch, pause):
        for cmd in batch:
            yield cmd
            yield 'sleep %i' % (pause,)
    return list(_with_pause(batch, pause))[:-1]


def run_batches(batches):
    """ Run shell commands grouped into batches, showing an execution trace.

    Raise AssertionError if any command has exits with a non-zero status.

    >>> run_batches([['echo foo', 'true']])
    + echo foo
    foo
    + true
    >>> run_batches([['true', 'echo foo'], ['false']])
    + true
    + echo foo
    foo
    + false
    Traceback (most recent call last):
    File "...", line ..., in <module>
    File "...", line ..., in run_batches
    AssertionError
    """
    procs = [
        subprocess.Popen(combine(batch), shell=True)
        for batch in batches
    ]
    assert [proc.wait() for proc in procs] == [0] * len(procs)


def get_output(s, *args, **kwargs):
    """
    Print and run command line s, %-interopolated using *args. Return stdout.

    >>> s = get_output('echo "%s %s"', 'foo', 'bar')
    Running: ['echo', 'foo bar']
    >>> s
    'foo bar\n'
    """
    argv = _argv(s, *args)
    print('Running: %s' % (argv,), flush=True)
    return subprocess.check_output(argv, **kwargs)


def exists_in_path(progname):
    """
    Return True if progname exists in $PATH.

    >>> exists_in_path('echo')
    True
    >>> exists_in_path('kwyjibo') # Only found in North American cartoons
    False
    """
    return any(os.path.exists(os.path.join(dirname, progname))
               for dirname in os.environ['PATH'].split(os.pathsep))


class TempDir(object):
    def __init__(self):
        self.path = tempfile.mkdtemp(prefix='mitogen_ci_lib')
        atexit.register(self.destroy)

    def destroy(self, rmtree=shutil.rmtree):
        rmtree(self.path)


class Fold(object):
    def __init__(self, name): pass
    def __enter__(self): pass
    def __exit__(self, _1, _2, _3): pass


GIT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# Used only when MODE=mitogen
DISTRO = os.environ.get('DISTRO', 'debian9')
# Used only when MODE=ansible
DISTROS = os.environ.get('DISTROS', 'centos6 centos8 debian9 debian11 ubuntu1604 ubuntu2004').split()
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
    """Return the hostname where the docker daemon is running.
    """
    url = os.environ.get('DOCKER_HOST')
    if url in (None, 'http+docker://localunixsocket'):
        return 'localhost'

    parsed = urlparse.urlparse(url)
    return parsed.netloc.partition(':')[0]


def image_for_distro(distro):
    """Return the container image name or path for a test distro name.

    The returned value is suitable for use with `docker pull`.

    >>> image_for_distro('centos5')
    'public.ecr.aws/n5z0e8q9/centos5-test'
    >>> image_for_distro('centos5-something_custom')
    'public.ecr.aws/n5z0e8q9/centos5-test'
    """
    return 'public.ecr.aws/n5z0e8q9/%s-test' % (distro.partition('-')[0],)


def make_containers(name_prefix='', port_offset=0):
    """
    >>> import pprint
    >>> BASE_PORT=2200; DISTROS=['debian', 'centos6']
    >>> pprint.pprint(make_containers())
    [{'distro': 'debian',
      'hostname': 'localhost',
      'image': 'public.ecr.aws/n5z0e8q9/debian-test',
      'name': 'target-debian-1',
      'port': 2201,
      'python_path': '/usr/bin/python'},
     {'distro': 'centos6',
      'hostname': 'localhost',
      'image': 'public.ecr.aws/n5z0e8q9/centos6-test',
      'name': 'target-centos6-2',
      'port': 2202,
      'python_path': '/usr/bin/python'}]
    """
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
                "image": image_for_distro(distro),
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


# ssh removed from here because 'linear' strategy relies on processes that hang
# around after the Ansible run completes
INTERESTING_COMMS = ('python', 'sudo', 'su', 'doas')


def proc_is_docker(pid):
    try:
        fp = open('/proc/%s/cgroup' % (pid,), 'r')
    except IOError:
        return False

    try:
        return 'docker' in fp.read()
    finally:
        fp.close()


def get_interesting_procs(container_name=None):
    args = ['ps', 'ax', '-oppid=', '-opid=', '-ocomm=', '-ocommand=']
    if container_name is not None:
        args = ['docker', 'exec', container_name] + args

    out = []
    for line in subprocess__check_output(args).decode().splitlines():
        ppid, pid, comm, rest = line.split(None, 3)
        if (
            (
                any(comm.startswith(s) for s in INTERESTING_COMMS) or
                'mitogen:' in rest
            ) and
            (
                container_name is not None or
                (not proc_is_docker(pid))
            )
        ):
            out.append((int(pid), line))

    return sorted(out)


def start_containers(containers):
    """Run docker containers in the background, with sshd on specified ports.

    >>> containers = start_containers([
    ...     {'distro': 'debian', 'hostname': 'localhost',
    ...      'name': 'target-debian-1', 'port': 2201,
    ...      'python_path': '/usr/bin/python'},
    ... ])
    """
    if os.environ.get('KEEP'):
        return

    run_batches([
        [
            "docker rm -f %(name)s || true" % container,
            "docker run "
                "--rm "
                # "--cpuset-cpus 0,1 "
                "--detach "
                "--privileged "
                "--cap-add=SYS_PTRACE "
                "--publish 0.0.0.0:%(port)s:22/tcp "
                "--hostname=%(name)s "
                "--name=%(name)s "
                "%(image)s"
            % container
        ]
        for container in containers
    ])

    for container in containers:
        container['interesting'] = get_interesting_procs(container['name'])

    return containers


def verify_procs(hostname, old, new):
    oldpids = set(pid for pid, _ in old)
    if any(pid not in oldpids for pid, _ in new):
        print('%r had stray processes running:' % (hostname,), file=sys.stderr, flush=True)
        for pid, line in new:
            if pid not in oldpids:
                print('New process:', line, flush=True)
        return False

    return True


def check_stray_processes(old, containers=None):
    ok = True

    new = get_interesting_procs()
    if old is not None:
        ok &= verify_procs('test host machine', old, new)

    for container in containers or ():
        ok &= verify_procs(
            container['name'],
            container['interesting'],
            get_interesting_procs(container['name'])
        )

    assert ok, 'stray processes were found'


def dump_file(path):
    print('--- %s ---' % (path,), flush=True)
    with open(path, 'r') as fp:
        print(fp.read().rstrip(), flush=True)
    print('---', flush=True)


# SSH passes these through to the container when run interactively, causing
# stdout to get messed up with libc warnings.
os.environ.pop('LANG', None)
os.environ.pop('LC_ALL', None)
