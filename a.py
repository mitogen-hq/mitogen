import os, socket

def CreateChild(*args):
  '''
  Create a child process whos stdin/stdout is connected to a socketpair.
  Returns:
    fd
  '''
  sock1, sock2 = socket.socketpair()
  if os.fork():
    for pair in ((0, sock1), (1, sock2)):
      os.dup2(sock2.fileno(), pair[0])
      os.close(pair[1].fileno())
    os.execvp(args[0], args)
    raise SystemExit
  return sock1
