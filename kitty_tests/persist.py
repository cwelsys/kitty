#!/usr/bin/env python
# License: GPLv3 Copyright: 2026, Kovid Goyal <kovid at kovidgoyal.net>

from . import BaseTest


class Persist(BaseTest):

    def test_slugify(self):
        from kitty.persist import slugify
        self.assertEqual(slugify('/Users/cwel/src/kmux'), 'kmux')
        self.assertEqual(slugify('/Users/cwel/src/My Project'), 'my-project')
        self.assertEqual(slugify('/Users/cwel/src/weird!!name'), 'weird-name')
        self.assertEqual(slugify('/'), 'shell')
        self.assertEqual(slugify(''), 'shell')
        # collapses runs and strips leading/trailing separators
        self.assertEqual(slugify('/tmp/--a--b--'), 'a-b')
        # truncated to 24 chars
        self.assertEqual(slugify('/tmp/' + 'x' * 40), 'x' * 24)

    def test_make_session_name(self):
        from kitty.persist import make_session_name
        name = make_session_name('/Users/cwel/src/kmux', rand=lambda: 'a3f9')
        self.assertEqual(name, 'kmux-a3f9')
        # unusable cwd still yields a valid name
        self.assertEqual(make_session_name('', rand=lambda: 'beef'), 'shell-beef')

    def test_make_session_name_is_random_by_default(self):
        from kitty.persist import make_session_name
        a = make_session_name('/tmp/proj')
        b = make_session_name('/tmp/proj')
        self.assertNotEqual(a, b)
        self.assertTrue(a.startswith('proj-'))

    def test_drop_inherited_session(self):
        from kitty.persist import drop_inherited_session
        # a kitty launched from inside a zmx session must not pass the var on,
        # or zmx attach switches the launching terminal instead of creating
        env = {'ZMX_SESSION': 'cwel-7f46', 'ZMX_SESSION_PREFIX': 'ws.', 'PATH': '/bin'}
        drop_inherited_session(env)
        self.assertEqual(env, {'ZMX_SESSION_PREFIX': 'ws.', 'PATH': '/bin'})
        # absent is not an error
        env = {'PATH': '/bin'}
        drop_inherited_session(env)
        self.assertEqual(env, {'PATH': '/bin'})

    def test_should_reap(self):
        from kitty.persist import should_reap
        # kitty created this session, so kitty owns its lifetime
        self.assertTrue(should_reap({'zmx_session': 'kmux-a3f9', 'zmx_owned': '1'}))
        # user named it explicitly via --persist-name: never reap
        self.assertFalse(should_reap({'zmx_session': 'mywork'}))
        self.assertFalse(should_reap({'zmx_session': 'mywork', 'zmx_owned': '0'}))
        # not persisted at all
        self.assertFalse(should_reap({}))
        self.assertFalse(should_reap({'zmx_owned': '1'}))

    def test_zmx_command(self):
        from kitty.persist import zmx_command
        self.assertEqual(zmx_command('kmux-a3f9', None), ['zmx', 'attach', 'kmux-a3f9'])
        self.assertEqual(
            zmx_command('kmux-a3f9', ['nvim', 'foo.txt']),
            ['zmx', 'attach', 'kmux-a3f9', 'nvim', 'foo.txt'])
        self.assertEqual(zmx_command('kmux-a3f9', []), ['zmx', 'attach', 'kmux-a3f9'])

    def test_reap_command(self):
        from kitty.persist import reap_command
        self.assertEqual(reap_command('kmux-a3f9'), ['zmx', 'kill', 'kmux-a3f9'])
        # callers must pass the absolute path: kitty's PATH under LaunchServices
        # does not contain the directory zmx is usually installed in
        self.assertEqual(
            reap_command('kmux-a3f9', '/opt/homebrew/bin/zmx'),
            ['/opt/homebrew/bin/zmx', 'kill', 'kmux-a3f9'])

    def test_reap_command_rejects_empty(self):
        from kitty.persist import reap_command
        self.assertEqual(reap_command(''), [])
