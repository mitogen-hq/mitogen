#!/usr/sbin/dtrace -qs

/*
 * Copyright 2017, David Wilson
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice, this
 * list of conditions and the following disclaimer.
 *
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 * this list of conditions and the following disclaimer in the documentation
 * and/or other materials provided with the distribution.
 *
 * 3. Neither the name of the copyright holder nor the names of its contributors
 * may be used to endorse or promote products derived from this software without
 * specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
 * ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
 * WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
 * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 * CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
 * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

/*
 * OS X DTrace script to record the CPU time consumed by any python2.7 or SSH
 * process, and the exact read/write sizes to any AF_INET socket opened by an
 * SSH process.
 *
 * This introduces significant tracing overhead of between 5-10%, most likely
 * due to the SCHED events.
 *
 * Produces a CSV file containing columns:
 *      - wall_nsec: Nanoseconds wall time.
 *      - op: One of START, SCHED, EXIT, READ, WRITE 
 *      - nbytes: for READ/WRITE, size of AF_INET data read/written
 *      - cpu_nsec: for SCHED, nanoseconds spent scheduled.
 *      - pid: Process ID.
 *      - execname: argv[0]
 *
 * Operations:
 *      - START: thread relevant to the trace started up.
 *      - EXIT: thread relevant to the trace ended, cpu_nsec contains total
 *        time scheduled
 *      - SCHED: thread relevant to the trace was scheduled, cpu_nsec contains
 *        time spent before it went off-cpu again.
 *      - READ: SSH process performed a nbytes read from an AF_INET socket.
 *      - WRITE: SSH process performed a nbytes write to an AF_INET socket.
 */

inline string SSH = "ssh";
inline string PYTHON = "python2.7";
inline int PF_INET = 2;

dtrace:::BEGIN
{
    printf("wall_nsec,op,nbytes,cpu_nsec,pid,execname\n");
}

syscall::socket:entry
/execname == SSH/
{
    self->is_inet = (arg0 == PF_INET);
}

syscall::socket:return
/self->is_inet/
{
    self->inet_fds[arg0] = 1;
}

syscall::close:entry
/execname == SSH/
{
    self->inet_fds[arg0] = 0;
}

syscall::write:entry,
syscall::write_nocancel:entry
{
    self->fd = arg0;
}

syscall::write:return,
syscall::write_nocancel:return
/self->inet_fds[self->fd] && arg0 > 0/
{
    printf("%d,WRITE,%d,,,\n", walltimestamp, arg0);
}

syscall::read:entry,
syscall::read_nocancel:entry
{
    self->fd = arg0;
}

syscall::read*:return,
syscall::read_nocancel:return
/self->inet_fds[self->fd] && arg0 > 0/
{
    printf("%d,READ,%d,,,\n", walltimestamp, arg0);
}

proc:::lwp-start
/execname == SSH || execname == PYTHON/
{
    self->start_vtime = vtimestamp;
    printf("%d,START,,,%d,%s\n", walltimestamp, pid, execname);
}

proc:::lwp-exit
/(execname == SSH || execname == PYTHON) && self->start_vtime/
{
    this->nsecs = vtimestamp - self->start_vtime;
    printf("%d,EXIT,,%d,%d,%s\n", walltimestamp, this->nsecs, pid, execname);
    /* Kernel threads are recycled, variables hang around. */
    self->start_vtime = 0;
    self->ontime = 0;
}

sched:::on-cpu
/self->start_vtime/
{
    self->ontime = timestamp;
}

sched:::off-cpu
/self->ontime/
{
    printf("%d,SCHED,,%d,%d,%s\n",
        walltimestamp,
        timestamp - self->ontime,
        pid,
        execname
    );
}
