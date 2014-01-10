
import socket

def GetCurrentHostname():
    '''
    Fetch the current hostname.
    '''
    return socket.gethostname()


def LogCurrentUptime(hostname, pathname='/tmp/uptime.txt'):
    '''
    Log the current uptime along with process ID that logs it.

    Args:
        hostname: the string hostname.
    '''

    fp = file(pathname, 'a')
    fp.write('%d %s %s\n' % (os.getpid(), hostname, os.popen('uptime').read()))
    fp.close()


def try_something_silly(arg):
    file('tty', 'w').write('ARG WAS: ' + str(arg) + '\n')
