#!/usr/bin/env python
# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>
import types
from collections import deque

from kitty.window import Window

from .base import BaseTest


def make_title_window():
    w = Window.__new__(Window)
    w.default_title = 'default'
    w.child_title = w.default_title
    w.program_title = ''
    w.shell_title = ''
    w.override_title = None
    w.title_stack = deque(maxlen=10)
    w.watchers = types.SimpleNamespace(on_title_change=None)
    w.call_watchers = lambda *a, **k: None
    w.title_updated = lambda *a, **k: None
    return w


class TestWindowTitle(BaseTest):
    def test_title_stack_restore_clears_stale_program_title(self):
        w = make_title_window()
        w.title_changed(memoryview(b'vim'))
        self.ae(w.title, 'vim')
        w.manipulate_title_stack(pop=False, title='x', icon=None)
        w.title_changed(memoryview(b'vim - README'))
        self.ae(w.title, 'vim - README')
        w.manipulate_title_stack(pop=True, title='x', icon=None)
        self.ae(w.title, 'vim')

    def test_title_chain_priority(self):
        w = make_title_window()
        w.shell_title = 'shell'
        self.ae(w.title, 'shell')
        w.program_title = 'prog'
        self.ae(w.title, 'prog')
        w.override_title = 'override'
        self.ae(w.title, 'override')
