# Monkey-patch os.fork() to produce a latency histogram on run completion.
# Requires 'hdrhsitograms' PyPI module.

from __future__ import print_function

import os
import resource
import sys
import time

import ansible.plugins.callback

try:
    import hdrh.histogram
except ImportError:
    hdrh = None


def get_fault_count(who=resource.RUSAGE_CHILDREN):
    ru = resource.getrusage(who)
    return ru.ru_minflt + ru.ru_majflt


class CallbackModule(ansible.plugins.callback.CallbackBase):
    hist = None

    def v2_playbook_on_start(self, playbook):
        if self.hist is not None:
            return

        if hdrh and 'FORK_HISTOGRAM' in os.environ:
            self.hist = hdrh.histogram.HdrHistogram(1, int(1e6*60), 3)
            self.fork_latency_sum_usec = 0.0
            self.install()

    def install(self):
        self.faults_at_start = get_fault_count(resource.RUSAGE_SELF)
        self.run_start_time = time.time()
        self.real_fork = os.fork
        os.fork = self.my_fork

    self_fault_usec = 1.113664156753052
    child_fault_usec = 4.734975610975617

    dummy_heap_size = int(os.environ.get('FORK_STATS_FAKE_HEAP_MB', '0'))
    dummy_heap = 'x' * (dummy_heap_size * 1048576)

    def my_fork(self):
        # doesnt count last child, oh well
        now_faults = get_fault_count()
        t0 = time.time()
        try:
            return self.real_fork()
        finally:
            latency_usec = (1e6 * (time.time() - t0))
            self.fork_latency_sum_usec += latency_usec
            self.hist.record_value(latency_usec)

    def playbook_on_stats(self, stats):
        if hdrh is None or 'FORK_HISTOGRAM' not in os.environ:
            return

        self_faults = get_fault_count(resource.RUSAGE_SELF) - self.faults_at_start
        child_faults = get_fault_count()
        run_duration_sec = time.time() - self.run_start_time
        fault_wastage_usec = (
            ((self.self_fault_usec * self_faults) +
             (self.child_fault_usec * child_faults))
        )
        fork_wastage = self.hist.get_total_count()
        all_wastage_usec = ((2*self.fork_latency_sum_usec) + fault_wastage_usec)

        print('--- Fork statistics ---')
        print('Post-boot run duration: %.02f ms, %d total forks' % (
            1000 * run_duration_sec,
            self.hist.get_total_count(),
        ))
        print('Self faults during boot: %d, post-boot: %d, avg %d/child' % (
            self.faults_at_start,
            self_faults,
            self_faults / self.hist.get_total_count(),
        ))
        print('Total child faults: %d, avg %d/child' % (
            child_faults,
            child_faults / self.hist.get_total_count(),
        ))
        print('Est. wastage on faults: %d ms, forks+faults+waits: %d ms (%.2f%%)' % (
            fault_wastage_usec / 1000,
            all_wastage_usec / 1000,
            100 * (all_wastage_usec / (run_duration_sec * 1e6)),
        ))
        print('99th%% fork latency: %.03f msec, max %d new tasks/sec' % (
            self.hist.get_value_at_percentile(99) / 1000.0,
            1e6 / self.hist.get_value_at_percentile(99),
        ))

        self.hist.output_percentile_distribution(sys.stdout, 1000)
        print('--- End fork statistics ---')
        print()
