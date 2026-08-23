#!/usr/bin/env python
# License: GPLv3 Copyright: 2026, Kovid Goyal <kovid at kovidgoyal.net>

from .base import BaseTest


class Persist(BaseTest):
    def test_slugify(self):
        from kitty.persist import slugify

        self.assertEqual(slugify('/Users/cwel/src/kmux'), 'kmux')
        self.assertEqual(slugify('/Users/cwel/src/My Project'), 'my-project')
        self.assertEqual(slugify('/Users/cwel/src/weird!!name'), 'weird-name')
        self.assertEqual(slugify('/'), 'shell')
        self.assertEqual(slugify(''), 'shell')
        self.assertEqual(slugify('/tmp/--a--b--'), 'a-b')
        self.assertEqual(slugify('/tmp/' + 'x' * 40), 'x' * 24)

    def test_make_session_name(self):
        from kitty.persist import make_session_name

        name = make_session_name('/Users/cwel/src/kmux', rand=lambda: 'a3f9')
        self.assertEqual(name, 'kmux-a3f9')
        self.assertEqual(make_session_name('', rand=lambda: 'beef'), 'shell-beef')

    def test_make_session_name_is_random_by_default(self):
        from kitty.persist import make_session_name

        a = make_session_name('/tmp/proj')
        b = make_session_name('/tmp/proj')
        self.assertNotEqual(a, b)
        self.assertTrue(a.startswith('proj-'))

    def test_drop_inherited_session(self):
        from kitty.persist import drop_inherited_session

        env = {'ZMX_SESSION': 'cwel-7f46', 'ZMX_SESSION_PREFIX': 'ws.', 'PATH': '/bin'}
        drop_inherited_session(env)
        self.assertEqual(env, {'ZMX_SESSION_PREFIX': 'ws.', 'PATH': '/bin'})
        env = {'PATH': '/bin'}
        drop_inherited_session(env)
        self.assertEqual(env, {'PATH': '/bin'})

    def test_should_reap(self):
        from kitty.persist import should_reap

        self.assertTrue(should_reap({'zmx_session': 'kmux-a3f9', 'zmx_owned': '1'}))
        self.assertFalse(should_reap({'zmx_session': 'mywork'}))
        self.assertFalse(should_reap({'zmx_session': 'mywork', 'zmx_owned': '0'}))
        self.assertFalse(should_reap({}))
        self.assertFalse(should_reap({'zmx_owned': '1'}))

    def test_auto_persist_applies(self):
        from kitty.persist import auto_persist_applies

        self.assertFalse(auto_persist_applies(True, is_layer_shell=True))
        self.assertTrue(auto_persist_applies(True, is_layer_shell=False))
        self.assertFalse(auto_persist_applies(False, is_layer_shell=False))
        self.assertFalse(auto_persist_applies(False, is_layer_shell=True))

    def test_zmx_command(self):
        from kitty.persist import zmx_command

        self.assertEqual(zmx_command('kmux-a3f9', None), ['zmx', 'attach', 'kmux-a3f9'])
        self.assertEqual(zmx_command('kmux-a3f9', ['nvim', 'foo.txt']), ['zmx', 'attach', 'kmux-a3f9', 'nvim', 'foo.txt'])
        self.assertEqual(zmx_command('kmux-a3f9', []), ['zmx', 'attach', 'kmux-a3f9'])

    def test_reap_command(self):
        from kitty.persist import reap_command

        self.assertEqual(reap_command('kmux-a3f9'), ['zmx', 'kill', 'kmux-a3f9'])
        self.assertEqual(reap_command('kmux-a3f9', '/opt/homebrew/bin/zmx'), ['/opt/homebrew/bin/zmx', 'kill', 'kmux-a3f9'])

    def test_reap_command_rejects_empty(self):
        from kitty.persist import reap_command

        self.assertEqual(reap_command(''), [])

    def test_session_pid_command(self):
        from kitty.persist import session_pid_command

        self.assertEqual(session_pid_command('kmux-a3f9'), ['zmx', 'list', '--where', 'name=kmux-a3f9'])
        self.assertEqual(session_pid_command('work', '/opt/homebrew/bin/zmx'), ['/opt/homebrew/bin/zmx', 'list', '--where', 'name=work'])

    def test_parse_session_pid(self):
        from kitty.persist import parse_session_pid

        line = '  name=kmux-a3f9\tpid=3954121\tclients=1\tcreated=1785274134\tstart_dir=/home/cwel/src\tcmd=/bin/zsh\n'
        self.assertEqual(parse_session_pid(line, 'kmux-a3f9'), 3954121)
        line = "  name=w\tpid=42\tcmd=/bin/sh -c 'x=1 sleep 60'\n"
        self.assertEqual(parse_session_pid(line, 'w'), 42)
        self.assertEqual(parse_session_pid('  name=work-2\tpid=7\n', 'work'), 0)
        self.assertEqual(parse_session_pid('no sessions found in /run/user/1000/zmx\n', 'w'), 0)
        self.assertEqual(parse_session_pid('  name=w\tclients=0\n', 'w'), 0)
        self.assertEqual(parse_session_pid('  name=w\tpid=notanint\n', 'w'), 0)
        self.assertEqual(parse_session_pid('', 'w'), 0)
