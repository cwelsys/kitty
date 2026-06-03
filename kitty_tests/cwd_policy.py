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
