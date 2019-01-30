# Copyright 2017, David Wilson
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import ctypes
import mmap
import multiprocessing
import os
import struct

import mitogen.parent


try:
    _libc = ctypes.CDLL(None, use_errno=True)
    _strerror = _libc.strerror
    _strerror.restype = ctypes.c_char_p
    _pthread_mutex_init = _libc.pthread_mutex_init
    _pthread_mutex_lock = _libc.pthread_mutex_lock
    _pthread_mutex_unlock = _libc.pthread_mutex_unlock
    _sched_setaffinity = _libc.sched_setaffinity
except (OSError, AttributeError):
    _libc = None


class pthread_mutex_t(ctypes.Structure):
    _fields_ = [
        ('data', ctypes.c_uint8 * 512),
    ]

    def init(self):
        if _pthread_mutex_init(self.data, 0):
            raise Exception(_strerror(ctypes.get_errno()))

    def acquire(self):
        if _pthread_mutex_lock(self.data):
            raise Exception(_strerror(ctypes.get_errno()))

    def release(self):
        if _pthread_mutex_unlock(self.data):
            raise Exception(_strerror(ctypes.get_errno()))


class State(ctypes.Structure):
    _fields_ = [
        ('lock', pthread_mutex_t),
        ('counter', ctypes.c_uint8),
    ]


class Manager(object):
    """
    Bind this process to a randomly selected CPU. If done prior to starting
    threads, all threads will be bound to the same CPU. This call is a no-op on
    systems other than Linux.

    A hook is installed that causes `reset_affinity(clear=True)` to run in the
    child of any process created with :func:`mitogen.parent.detach_popen`,
    ensuring CPU-intensive children like SSH are not forced to share the same
    core as the (otherwise potentially very busy) parent.

    Threads bound to the same CPU share cache and experience the lowest
    possible inter-thread roundtrip latency, for example ensuring the minimum
    possible time required for :class:`mitogen.service.Pool` to interact with
    :class:`mitogen.core.Broker`, as required for every message transmitted or
    received.

    Binding threads of a Python process to one CPU makes sense, as they are
    otherwise unable to operate in parallel, and all must acquire the same lock
    prior to executing.
    """
    def __init__(self):
        self.mem = mmap.mmap(-1, 4096)
        self.state = State.from_buffer(self.mem)
        self.state.lock.init()

    def _set_affinity(self, mask):
        mitogen.parent._preexec_hook = self.clear
        s = struct.pack('L', mask)
        _sched_setaffinity(os.getpid(), len(s), s)

    def cpu_count(self):
        return multiprocessing.cpu_count()

    def clear(self):
        """
        Clear any prior binding, except for reserved CPUs.
        """
        self._set_affinity(0xffffffff & ~3)

    def set_cpu(self, cpu):
        """
        Bind to 0-based `cpu`.
        """
        self._set_affinity(1 << cpu)

    def assign(self):
        self.state.lock.acquire()
        try:
            n = self.state.counter
            self.state.counter += 1
        finally:
            self.state.lock.release()

        self.set_cpu(2 + (n % (self.cpu_count() - 2)))


manager = Manager()
