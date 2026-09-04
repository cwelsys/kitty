#!/usr/bin/env python
# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>
import types
from collections import deque

from kitty.utils import known_shell_names
from kitty.window import CwdRequestType, Window

from .base import BaseTest


def make_title_window():
    w = Window.__new__(Window)
    w.default_title = 'default'
    w.child_title = w.default_title
    w.shell_title = ''
    w.override_title = None
    w.title_stack = deque(maxlen=10)
    w.watchers = types.SimpleNamespace(on_title_change=None)
    w.call_watchers = lambda *a, **k: None
    w.title_updated = lambda *a, **k: None
    return w


def make_cwd_window(
    reported='kitty-shell-cwd://host/home/u/proj', remote=False, at_prompt=False, fg_pid=2000, fg_exe='/usr/bin/make', heuristic='/', root_cwd='/home/u'
):
    w = Window.__new__(type('W', (Window,), {'child_is_remote': remote, 'at_prompt': at_prompt}))
    w.screen = types.SimpleNamespace(last_reported_cwd=reported)
    w.child = types.SimpleNamespace(effective_pid=1000, get_pid_for_cwd=lambda oldest=False: fg_pid, get_foreground_exe=lambda oldest=False: fg_exe)
    w.get_cwd_of_child = lambda oldest=False: heuristic
    w.get_cwd_of_root_child = lambda: root_cwd
    return w


class TestWindow(BaseTest):
    def test_title_stack_restore_clears_stale_program_title(self):
        w = make_title_window()
        w.title_changed(memoryview(b'vim'))
        self.ae(w.title, 'vim')
        w.manipulate_title_stack(pop=False, title='x', icon=None)
        w.title_changed(memoryview(b'vim - README'))
        self.ae(w.title, 'vim - README')
        w.manipulate_title_stack(pop=True, title='x', icon=None)
        self.ae(w.title, 'vim')

    def test_resolved_cwd(self):
        self.assertIn('zsh', known_shell_names())
        self.assertNotIn('make', known_shell_names())
        current, last, root = CwdRequestType.current, CwdRequestType.last_reported, CwdRequestType.root
        for kw, request_type, expected in (
            ({}, current, '/home/u/proj'),
            ({'fg_exe': '/usr/bin/zsh', 'heuristic': '/etc'}, current, '/etc'),
            ({'fg_exe': '/usr/bin/zsh', 'fg_pid': 1000, 'heuristic': '/etc'}, current, '/home/u/proj'),
            ({'remote': True, 'heuristic': '/local'}, current, '/local'),
            ({'reported': '', 'heuristic': '/srv'}, current, '/srv'),
            ({'fg_exe': '/usr/bin/zsh', 'heuristic': '/etc'}, last, '/home/u/proj'),
            ({'remote': True, 'heuristic': '/x'}, last, '/x'),
            ({'heuristic': '/x'}, root, '/home/u'),
            ({'at_prompt': True}, root, '/home/u/proj'),
        ):
            self.ae(make_cwd_window(**kw).resolved_cwd(request_type=request_type), expected, f'{kw} {request_type}')
