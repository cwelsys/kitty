#!/usr/bin/env python
# License: GPLv3 Copyright: 2026, Kovid Goyal <kovid at kovidgoyal.net>

from kitty.persist import make_session_name, parse_session_pid, should_reap, slugify

from .base import BaseTest


class Persist(BaseTest):
    def test_slugify(self):
        for cwd, slug in (
            ('/Users/cwel/src/kmux', 'kmux'),
            ('/Users/cwel/src/My Project', 'my-project'),
            ('/Users/cwel/src/weird!!name', 'weird-name'),
            ('/', 'shell'),
            ('', 'shell'),
            ('/tmp/--a--b--', 'a-b'),
            ('/tmp/' + 'x' * 40, 'x' * 24),
        ):
            self.ae(slugify(cwd), slug)
        a, b = make_session_name('/tmp/proj'), make_session_name('/tmp/proj')
        self.assertNotEqual(a, b)
        self.assertTrue(a.startswith('proj-'))

    def test_should_reap(self):
        self.assertTrue(should_reap({'zmx_session': 'kmux-a3f9', 'zmx_owned': '1'}))
        self.assertFalse(should_reap({'zmx_session': 'mywork'}))
        self.assertFalse(should_reap({'zmx_session': 'mywork', 'zmx_owned': '0'}))
        self.assertFalse(should_reap({}))
        self.assertFalse(should_reap({'zmx_owned': '1'}))

    def test_parse_session_pid(self):
        line = '  name=kmux-a3f9\tpid=3954121\tclients=1\tcreated=1785274134\tstart_dir=/home/cwel/src\tcmd=/bin/zsh\n'
        self.ae(parse_session_pid(line, 'kmux-a3f9'), 3954121)
        self.ae(parse_session_pid("  name=w\tpid=42\tcmd=/bin/sh -c 'x=1 sleep 60'\n", 'w'), 42)
        for output in ('  name=work-2\tpid=7\n', 'no sessions found in /run/user/1000/zmx\n', '  name=w\tclients=0\n', '  name=w\tpid=notanint\n', ''):
            self.ae(parse_session_pid(output, 'w'), 0)
