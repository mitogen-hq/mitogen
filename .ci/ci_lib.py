
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

def have_brew():
    proc = subprocess.Popen('brew help >/dev/null 2>/dev/null', shell=True)
    return proc.wait() == 0


def have_docker():
    proc = subprocess.Popen('docker info >/dev/null 2>/dev/null', shell=True)
    return proc.wait() == 0


# -----------------

# Force line buffering on stdout.
sys.stdout = os.fdopen(1, 'w', 1)

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
    """Interpolate a command line using *args, return an argv style list.

    >>> _argv('git commit -m "Use frobnicate 2.0 (fixes #%d)"', 1234)
    ['git', commit', '-m', 'Use frobnicate 2.0 (fixes #1234)']
    """
    if args:
        s %= args
    return shlex.split(s)


def run(s, *args, **kwargs):
    """ Run a command, with arguments, and print timing information

    >>> rc = run('echo "%s %s"', 'foo', 'bar')
    Running: ['/usr/bin/time', '--', 'echo', 'foo bar']
    foo bar
    0.00user 0.00system 0:00.00elapsed ?%CPU (0avgtext+0avgdata 1964maxresident)k
    0inputs+0outputs (0major+71minor)pagefaults 0swaps
    Finished running: ['/usr/bin/time', '--', 'echo', 'foo bar']
    >>> rc
    0
    """
    argv = ['/usr/bin/time', '--'] + _argv(s, *args)
    print('Running: %s' % (argv,))
    try:
        ret = subprocess.check_call(argv, **kwargs)
        print('Finished running: %s' % (argv,))
    except Exception:
        print('Exception occurred while running: %s' % (argv,))
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
    print('Running: %s' % (argv,))
    return subprocess.check_output(argv, **kwargs)


def exists_in_path(progname):
    """
    Return True if proganme exists in $PATH.

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
    """
    Bracket a section of stdout with travis_fold markers.

    This allows the section to be collapsed or expanded in Travis CI web UI.

    >>> with Fold('stage 1'):
    ...     print('Frobnicate the frobnitz')
    ...
    travis_fold:start:stage 1
    Frobnicate the frobnitz
    travis_fold:end:stage 1
    """
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
      'name': 'target-debian-1',
      'port': 2201,
      'python_path': '/usr/bin/python'},
     {'distro': 'centos6',
      'hostname': 'localhost',
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
                "mitogen/%(distro)s-test "
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
        print('%r had stray processes running:' % (hostname,))
        for pid, line in new:
            if pid not in oldpids:
                print('New process:', line)

        print()
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
