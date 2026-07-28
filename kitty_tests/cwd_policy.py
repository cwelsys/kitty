#!/usr/bin/env python
# License: GPLv3 Copyright: 2026, Kovid Goyal <kovid at kovidgoyal.net>

import os
import tempfile

from . import BaseTest


class CwdPolicy(BaseTest):

    def test_known_shell_names_from_file(self):
        from kitty.cwd_policy import known_shell_names
        with tempfile.NamedTemporaryFile('w', suffix='.shells', delete=False) as f:
            f.write('# a comment\n/bin/bash\n/usr/bin/fish\n\n/opt/weirdsh\n')
            path = f.name
        try:
            names = known_shell_names(path)
        finally:
            os.unlink(path)
        self.assertIn('bash', names)
        self.assertIn('fish', names)
        self.assertIn('weirdsh', names)
        # static fallback set is always present
        self.assertIn('zsh', names)

    def test_known_shell_names_missing_file(self):
        from kitty.cwd_policy import known_shell_names
        names = known_shell_names('/nonexistent/path/to/shells')
        # static fallback still present, no exception
        self.assertIn('bash', names)
        self.assertIn('zsh', names)

    def test_is_shell_exe(self):
        from kitty.cwd_policy import is_shell_exe
        self.assertTrue(is_shell_exe('/usr/bin/zsh'))
        self.assertTrue(is_shell_exe('/bin/bash'))
        self.assertFalse(is_shell_exe('/usr/bin/make'))
        self.assertFalse(is_shell_exe('/home/u/.local/bin/claude'))
        self.assertFalse(is_shell_exe(''))

    def test_choose_cwd_current_prefers_reported(self):
        from kitty.cwd_policy import choose_cwd
        # build/clipboard case: job running, reported set, not a nested shell,
        # heuristic would return junk ('/')
        self.ae(choose_cwd(
            reported='/home/u/proj', child_is_remote=False, at_prompt=False,
            foreground_is_nested_shell=False, heuristic_cwd='/', mode='current'),
            '/home/u/proj')

    def test_choose_cwd_current_nested_shell_uses_heuristic(self):
        from kitty.cwd_policy import choose_cwd
        self.ae(choose_cwd(
            reported='/home/u/proj', child_is_remote=False, at_prompt=False,
            foreground_is_nested_shell=True, heuristic_cwd='/etc', mode='current'),
            '/etc')

    def test_choose_cwd_current_remote_uses_heuristic(self):
        from kitty.cwd_policy import choose_cwd
        self.ae(choose_cwd(
            reported='/home/u/proj', child_is_remote=True, at_prompt=False,
            foreground_is_nested_shell=False, heuristic_cwd='/local', mode='current'),
            '/local')

    def test_choose_cwd_current_no_osc7_uses_heuristic(self):
        from kitty.cwd_policy import choose_cwd
        self.ae(choose_cwd(
            reported='', child_is_remote=False, at_prompt=False,
            foreground_is_nested_shell=False, heuristic_cwd='/proc/cwd', mode='current'),
            '/proc/cwd')

    def test_choose_cwd_last_reported_forces_reported(self):
        from kitty.cwd_policy import choose_cwd
        self.ae(choose_cwd(
            reported='/home/u/proj', child_is_remote=False, at_prompt=False,
            foreground_is_nested_shell=True, heuristic_cwd='/x', mode='last_reported'),
            '/home/u/proj')
        # but not when remote
        self.ae(choose_cwd(
            reported='/home/u/proj', child_is_remote=True, at_prompt=False,
            foreground_is_nested_shell=False, heuristic_cwd='/x', mode='last_reported'),
            '/x')

    def test_choose_cwd_prompt_gated(self):
        from kitty.cwd_policy import choose_cwd
        # at prompt -> reported
        self.ae(choose_cwd(
            reported='/home/u/proj', child_is_remote=False, at_prompt=True,
            foreground_is_nested_shell=False, heuristic_cwd='/h', mode='prompt_gated'),
            '/home/u/proj')
        # not at prompt -> heuristic
        self.ae(choose_cwd(
            reported='/home/u/proj', child_is_remote=False, at_prompt=False,
            foreground_is_nested_shell=False, heuristic_cwd='/h', mode='prompt_gated'),
            '/h')

    def _fake_window(self, **kw):
        from types import SimpleNamespace
        from kitty.window import Window
        defaults = dict(
            last_reported_cwd='kitty-shell-cwd://host/home/u/proj',
            child_is_remote=False, at_prompt=False,
            fg_pid=2000, root_pid=1000, fg_exe='/usr/bin/make',
            heuristic='/', root_cwd='/home/u',
        )
        defaults.update(kw)
        child = SimpleNamespace(
            pid=defaults['root_pid'],
            # the window's own root process, which for a persisted window is the
            # process inside the session rather than the wrapper kitty forked
            effective_pid=defaults['root_pid'],
            get_pid_for_cwd=lambda oldest=False: defaults['fg_pid'],
            get_foreground_exe=lambda oldest=False: defaults['fg_exe'],
        )
        fake = SimpleNamespace(
            screen=SimpleNamespace(last_reported_cwd=defaults['last_reported_cwd']),
            child=child,
            child_is_remote=defaults['child_is_remote'],
            at_prompt=defaults['at_prompt'],
            get_cwd_of_child=lambda oldest=False: defaults['heuristic'],
            get_cwd_of_root_child=lambda: defaults['root_cwd'],
        )
        # bind the real methods under test to the fake
        fake._foreground_is_nested_shell = lambda oldest=False: Window._foreground_is_nested_shell(fake, oldest)
        fake.resolved_cwd = lambda oldest=False, request_type=None: (
            Window.resolved_cwd(fake, oldest) if request_type is None
            else Window.resolved_cwd(fake, oldest, request_type))
        return fake

    def test_nested_shell_detection(self):
        # foreground is make (not a shell) -> not nested
        w = self._fake_window(fg_exe='/usr/bin/make', fg_pid=2000, root_pid=1000)
        self.assertFalse(w._foreground_is_nested_shell())
        # foreground is a nested zsh (pid != integrated shell) -> nested
        w = self._fake_window(fg_exe='/usr/bin/zsh', fg_pid=2000, root_pid=1000)
        self.assertTrue(w._foreground_is_nested_shell())
        # foreground IS the integrated shell -> not nested
        w = self._fake_window(fg_exe='/usr/bin/zsh', fg_pid=1000, root_pid=1000)
        self.assertFalse(w._foreground_is_nested_shell())

    def test_resolved_cwd_build_case_prefers_reported(self):
        # job running, heuristic poisoned to '/', non-shell foreground
        w = self._fake_window(heuristic='/', fg_exe='/usr/bin/make', at_prompt=False)
        self.ae(w.resolved_cwd(), '/home/u/proj')

    def test_resolved_cwd_nested_shell_uses_heuristic(self):
        w = self._fake_window(heuristic='/etc', fg_exe='/usr/bin/zsh', fg_pid=2000, root_pid=1000)
        self.ae(w.resolved_cwd(), '/etc')

    def test_resolved_cwd_no_osc7_uses_heuristic(self):
        w = self._fake_window(last_reported_cwd='', heuristic='/srv')
        self.ae(w.resolved_cwd(), '/srv')

    def test_resolved_cwd_last_reported_request(self):
        from kitty.window import CwdRequestType
        # nested shell would normally use heuristic, but last_reported forces reported
        w = self._fake_window(heuristic='/etc', fg_exe='/usr/bin/zsh', fg_pid=2000, root_pid=1000)
        self.ae(w.resolved_cwd(request_type=CwdRequestType.last_reported), '/home/u/proj')

    def test_resolved_cwd_root_request_prompt_gated(self):
        from kitty.window import CwdRequestType
        # not at prompt -> root child cwd (heuristic root)
        w = self._fake_window(at_prompt=False, root_cwd='/home/u', heuristic='/x')
        self.ae(w.resolved_cwd(request_type=CwdRequestType.root), '/home/u')
        # at prompt -> reported
        w = self._fake_window(at_prompt=True, root_cwd='/home/u')
        self.ae(w.resolved_cwd(request_type=CwdRequestType.root), '/home/u/proj')
