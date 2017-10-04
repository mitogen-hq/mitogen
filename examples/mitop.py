
import curses
import subprocess
import sys
import time

import mitogen.core
import mitogen.master
import mitogen.utils


class Host(object):
    # Incremented once for each received ps output, copied to task struct. Used
    # to find dead tasks.
    name = None
    context = None
    recv = None

    def __init__(self):
        self.procs = {}  #: pid -> Process()

class Process(object):
    host = None
    user = None
    pid = None
    ppid = None
    pgid = None
    command = None
    rss = None
    pcpu = None
    rss = None


def send_once(sender):
    args = ['ps', '-axwwo', 'user,pid,ppid,pgid,%cpu,rss,command']
    output = subprocess.check_output(args)
    sender.put(output)


@mitogen.core.takes_router
def remote_main(context_id, handle, delay, router):
    context = mitogen.core.Context(router, context_id)
    sender = mitogen.core.Sender(context, handle)

    while True:
        send_once(sender)
        time.sleep(delay)

    if sys.platform == 'darwin':
        darwin_main(sender, delay)
    elif sys.platform == 'linux':
        linux_main(sender, delay)


def parse_output(host, s):
    prev_pids = set(host.procs)

    for line in s.splitlines()[1:]:
        bits = line.split(None, 6)
        pid = int(bits[1])
        prev_pids.discard(pid)

        try:
            proc = host.procs[pid]
        except KeyError:
            host.procs[pid] = proc = Process()
            proc.hostname = host.name

        proc.user = bits[0]
        proc.pid = pid
        proc.ppid = int(bits[2])
        proc.pgid = int(bits[3])
        proc.pcpu = float(bits[4])
        proc.rss = int(bits[5]) / 1024
        proc.command = bits[6]

    # These PIDs had no update, so probably they are dead now.
    for pid in prev_pids:
        del host.procs[pid]


class Painter(object):
    def __init__(self, hosts):
        self.stdscr = curses.initscr()
        self.height, self.width = self.stdscr.getmaxyx()
        curses.cbreak()
        curses.noecho()
        self.stdscr.keypad(1)
        self.hosts = hosts
        self.format = (
            '%(hostname)10.10s '
            '%(pid)7.7s '
            '%(ppid)7.7s '
            '%(pcpu)6.6s '
            '%(rss)5.5s '
            '%(command)20s'
        )

    def close(self):
        curses.endwin()

    def paint(self):
        self.stdscr.clear()
        self.stdscr.addstr(0, 0, time.ctime())

        all_procs = []
        for host in self.hosts:
            all_procs.extend(host.procs.itervalues())

        all_procs.sort(key=(lambda proc: -proc.pcpu))

        self.stdscr.addstr(1, 0, self.format % {
            'hostname': 'HOST',
            'pid': 'PID',
            'ppid': 'PPID',
            'pcpu': '%CPU',
            'rss': 'RSS',
            'command': 'COMMAND',
        })
        for i, proc in enumerate(all_procs):
            if (i+3) >= self.height:
                break
            self.stdscr.addstr(2+i, 0, self.format % vars(proc))

        self.stdscr.refresh()


def local_main(painter, router, select, delay):
    next_paint = 0
    while True:
        recv, (msg, data) = select.get()
        parse_output(recv.host, data)
        if next_paint < time.time():
            next_paint = time.time() + delay
            painter.paint()


def main(router, argv):
    #mitogen.utils.log_to_file(level='DEBUG')
    mitogen.utils.log_to_file()

    if not len(argv):
        print 'mitop: Need a list of SSH hosts to connect to.'
        sys.exit(1)

    delay = 1.0
    select = mitogen.master.Select(oneshot=False)
    hosts = []

    for hostname in argv:
        print 'Starting on', hostname
        host = Host()
        host.name = hostname
        if host.name == 'localhost':
            host.context = router.local()
        else:
            host.context = router.ssh(hostname=host.name)

        host.recv = mitogen.core.Receiver(router)
        host.recv.host = host
        host.recv.host_main = False
        host.tasks = []
        select.add(host.recv)

        call_recv = host.context.call_async(remote_main,
            mitogen.context_id,
            host.recv.handle,
            delay,
        )
        call_recv.host = host
        call_recv.host_main = True
        select.add(call_recv)
        hosts.append(host)

    painter = Painter(hosts)
    try:
        try:
            local_main(painter, router, select, delay)
        except KeyboardInterrupt:
            pass
    finally:
        painter.close()

if __name__ == '__main__':
    mitogen.utils.run_with_router(main, sys.argv[1:])
