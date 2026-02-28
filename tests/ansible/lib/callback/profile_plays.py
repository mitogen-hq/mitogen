# SPDX-FileCopyrightText: 2026 Mitogen authors <https://github.com/mitogen-hq>
# SPDX-License-Identifier: BSD-3-Clause
from __future__ import absolute_import, division, print_function
__metaclass__ = type

import itertools
import time

import ansible.plugins.callback
import ansible.utils.display

display = ansible.utils.display.Display()


class CallbackModule(ansible.plugins.callback.CallbackBase):
    CALLBACK_NAME = 'profile_plays'
    CALLBACK_NEEDS_WHITELIST = True
    CALLBACK_TYPE = 'aggregate'
    CALLBACK_VERSION = 2.0

    def __init__(self):
        self._data = []
        self._play_counter = itertools.count()
        super(CallbackModule, self).__init__()

    def v2_playbook_on_play_start(self, play):
        start = time.time()
        if self._data:
            prev = self._data[-1]
            prev.update({
                'end': start,
                'duration': start - prev['start'],
            })

        serial = next(self._play_counter)
        self._data.append({
            'serial': serial,
            'name': play.get_name().strip() or u'PLAY %d' % serial,
            'uuid': play._uuid,
            'start': start,
        })

    def v2_playbook_on_stats(self, stats):
        start = time.time()
        if self._data:
            prev = self._data[-1]
            prev.update({
                'end': start,
                'duration': start - prev['start'],
            })

        data = self._data.copy()
        data.sort(key=lambda d: d['duration'], reverse=True)

        display.display(u'{:=<79}'.format(u'Play durations '))
        for d in data[:10]:
            display.display(u'{name:70.70}  {duration:>6,.2f}s'.format(**d))
