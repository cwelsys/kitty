#!/usr/bin/env python
# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>
from . import BaseTest


class TestTabBarZones(BaseTest):

    def test_separator_mirror_glyphs_intact(self):
        # Regression: the private-use Powerline glyphs in _SEPARATOR_MIRROR must
        # survive verbatim. If they get blanked, the mirror lookup misses and the
        # right (mirrored) zone draws an unflipped, wrong-facing separator.
        # Escapes (not raw glyphs) so this test can't itself be corrupted.
        from kitty.tab_bar_zones import draw
        self.ae(draw._SEPARATOR_MIRROR.get('\ue0b0'), '\ue0b2')  # solid right -> left
        self.ae(draw._SEPARATOR_MIRROR.get('\ue0b1'), '\ue0b3')  # outline right -> left
        # a mirrored zone pill uses the flipped separator, not the original
        zc = draw.ZoneContent(icon='I', parts=(('txt', 1),), icon_fg=1, icon_bg=2, text_bg=3)
        glyphs = [g for _, _, _, g in draw._zone_pill_cells(zc, '\ue0b6', '\ue0b4', '\ue0b0', mirrored=True)]
        self.assertIn('\ue0b2', glyphs)
        self.assertNotIn('\ue0b0', glyphs)

    def test_config_reads_options(self):
        from kitty.tab_bar_zones.config import get_config, clear_caches
        clear_caches()
        self.set_options({
            'tab_bar_zone_left': ('cwd_git',),
            'tab_bar_zone_right': ('tab_label', 'title'),
            'tab_bar_sticky_last_cmd': True,
            'tab_bar_content_separator': ' · ',
            'tab_bar_pill_spacing': 2,
        })
        cfg = get_config()
        self.ae(cfg.zone_left, ('cwd_git',))
        self.ae(cfg.zone_right, ('tab_label', 'title'))
        self.assertTrue(cfg.sticky_last_cmd)
        self.ae(cfg.content_separator, ' · ')
        self.ae(cfg.pill_spacing, 2)

    def test_icon_default_and_override(self):
        from kitty.tab_bar_zones.config import get_config, clear_caches
        clear_caches()
        self.set_options({'tab_bar_icon': {'myprog': 'Z'}})
        cfg = get_config()
        self.ae(cfg.icon_for('myprog'), 'Z')            # override wins
        self.ae(cfg.icon_for('kitty'), chr(0xf011b))    # built-in default (Nerd Font U+F011B)
        self.assertEqual(cfg.icon_for('unknown-xyz'), cfg.icon_fallback)  # fallback

    def test_parse_git_output(self):
        from kitty.tab_bar_zones.gitstatus import parse_git_output
        raw = (
            '# branch.head main\n'
            '# branch.ab +2 -1\n'
            '1 .M N... 100644 100644 100644 aaa bbb file1\n'
            '1 M. N... 100644 100644 100644 aaa bbb file2\n'
            '? untracked.txt\n'
            'u UU N... ...\n'
        )
        branch, counts = parse_git_output(raw)
        self.ae(branch, 'main')
        self.ae(counts['ahead'], 2)
        self.ae(counts['behind'], 1)
        self.ae(counts['modified'], 1)
        self.ae(counts['staged'], 1)
        self.ae(counts['untracked'], 1)
        self.ae(counts['conflicted'], 1)

    def test_git_cache_key_tracks_head_and_refs(self):
        # Regression: the status cache key must change when HEAD or the current
        # branch ref or FETCH_HEAD change, not only when .git/index changes.
        # Otherwise `git branch -m`, fetch/push ahead-behind drift and
        # `reset --soft` leave the tab-bar git zone showing stale data.
        import os
        import tempfile
        from pathlib import Path
        from kitty.tab_bar_zones.gitstatus import status_cache_key

        def settime(p, t):
            os.utime(p, (t, t))

        with tempfile.TemporaryDirectory() as td:
            gd = Path(td) / '.git'
            (gd / 'refs' / 'heads').mkdir(parents=True)
            (gd / 'index').write_text('x')
            (gd / 'HEAD').write_text('ref: refs/heads/main\n')
            (gd / 'refs' / 'heads' / 'main').write_text('abc\n')
            for p in (gd / 'index', gd / 'HEAD', gd / 'refs' / 'heads' / 'main'):
                settime(p, 1000)
            key1 = status_cache_key(gd)

            # `git branch -m` rewrites HEAD (index untouched) -> key must change
            (gd / 'HEAD').write_text('ref: refs/heads/renamed\n')
            settime(gd / 'HEAD', 2000)
            key2 = status_cache_key(gd)
            self.assertNotEqual(key1, key2)

            # fetch/reset moves the current branch ref (index untouched) -> change
            (gd / 'refs' / 'heads' / 'renamed').write_text('def\n')
            settime(gd / 'refs' / 'heads' / 'renamed', 3000)
            key3 = status_cache_key(gd)
            self.assertNotEqual(key2, key3)

            # fetch updates FETCH_HEAD (ahead/behind drift) -> change
            (gd / 'FETCH_HEAD').write_text('ghi\n')
            settime(gd / 'FETCH_HEAD', 4000)
            key4 = status_cache_key(gd)
            self.assertNotEqual(key3, key4)

    def test_git_cache_key_packed_refs_fallback(self):
        # When the current branch is packed (loose ref absent), packed-refs mtime
        # stands in so a `git pack-refs`/fetch still invalidates.
        import os
        import tempfile
        from pathlib import Path
        from kitty.tab_bar_zones.gitstatus import status_cache_key
        with tempfile.TemporaryDirectory() as td:
            gd = Path(td) / '.git'
            (gd / 'refs' / 'heads').mkdir(parents=True)
            (gd / 'index').write_text('x')
            (gd / 'HEAD').write_text('ref: refs/heads/main\n')
            (gd / 'packed-refs').write_text('abc refs/heads/main\n')
            for p in (gd / 'index', gd / 'HEAD', gd / 'packed-refs'):
                os.utime(p, (1000, 1000))
            key1 = status_cache_key(gd)
            os.utime(gd / 'packed-refs', (2000, 2000))
            key2 = status_cache_key(gd)
            self.assertNotEqual(key1, key2)

    def test_parse_git_output_no_double_count_delete(self):
        # A file deleted in both index and worktree (xy="DD") must count once.
        from kitty.tab_bar_zones.gitstatus import parse_git_output
        raw = (
            '# branch.head main\n'
            '1 DD N... 100644 100644 100644 aaa bbb gone\n'
        )
        _, counts = parse_git_output(raw)
        self.ae(counts['deleted'], 1)
        self.ae(counts['modified'], 0)  # must not leak into modified either

    def test_find_git_dir_does_not_cache_non_repo(self):
        # A non-repo cwd must not be cached as None forever; otherwise `git init`
        # in an open pane never shows a git zone until the cache cap clears.
        import tempfile
        from kitty.tab_bar_zones import gitstatus
        gitstatus.clear_caches()
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(gitstatus.find_git_dir(td))
            self.assertNotIn(td, gitstatus._git_dir_cache)

    def test_find_git_dir_relative_gitdir_pointer(self):
        # `.git` file with a relative `gitdir:` (submodules) must resolve against
        # the repo dir, not kitty's process CWD.
        import tempfile
        from pathlib import Path
        from kitty.tab_bar_zones import gitstatus
        gitstatus.clear_caches()
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / 'sub'
            repo.mkdir()
            real = Path(td) / '.git' / 'modules' / 'sub'
            real.mkdir(parents=True)
            (repo / '.git').write_text('gitdir: ../.git/modules/sub\n')
            self.ae(gitstatus.find_git_dir(str(repo)), real.resolve())

    def test_abbreviate_path(self):
        import os
        from kitty.tab_bar_zones.text import abbreviate_path
        home = os.path.expanduser('~')
        self.ae(abbreviate_path(home + '/projects/foo', 60, home, '…'), '~/projects/foo')
        # overflow collapses leading components
        long = home + '/aaaaaa/bbbbbb/cccccc/target'
        out = abbreviate_path(long, 20, home, '…')
        self.assertLessEqual(len(out), 20)
        self.assertTrue(out.endswith('target'))

    def test_truncate_text_respects_display_width(self):
        # Wide chars are 2 cells; slicing by codepoint overflows the cell budget.
        from kitty.tab_bar_zones.text import truncate_text, display_width
        out = truncate_text('日本語abc', 5, '…')
        self.assertLessEqual(display_width(out), 5)
        self.assertTrue(out.endswith('…'))
        # budget <= ellipsis width: still must not overflow
        self.assertLessEqual(display_width(truncate_text('日本語', 1, '…')), 1)
        # pure-ascii behaviour unchanged
        self.ae(truncate_text('abcdef', 4, '…'), 'abc…')

    def test_abbreviate_path_respects_display_width(self):
        from kitty.tab_bar_zones.text import abbreviate_path, display_width
        # last component itself wider than budget -> hits the final hard truncate
        out = abbreviate_path('/x/日本語日本語日本語', 6, '/none', '…')
        self.assertLessEqual(display_width(out), 6)

    def test_color_resolver(self):
        from kitty.tab_bar_zones.colors import ColorResolver
        from kitty.tab_bar import as_rgb
        from kitty.fast_data_types import Color
        r = ColorResolver(active_fg=Color(1, 2, 3), active_bg=Color(4, 5, 6),
                          inactive_fg=Color(7, 8, 9), inactive_bg=Color(10, 11, 12),
                          default_bg=Color(13, 14, 15))
        # a plain Color resolves to its as_rgb int
        self.ae(r.to_int(Color(255, 0, 0)), as_rgb(0xff0000))
        # the live theme sentinels resolve to DrawData colors
        self.ae(r.to_int('active_tab_background'), as_rgb(0x040506))
        self.ae(r.to_int('inactive_tab_background'), as_rgb(0x0a0b0c))
        # None falls back to gray
        self.ae(r.to_int(None), as_rgb(0xcccccc))

    def test_title_renderer_sticky(self):
        from kitty.tab_bar_zones import content
        from kitty.tab_bar import TabBarData
        content.clear_caches()

        def make_tab(tab_id, program_title, shell_title):
            return TabBarData(
                title='',
                tab_id=tab_id,
                program_title=program_title,
                shell_title=shell_title,
                override_title='',
            )

        tab = make_tab(tab_id=-1, program_title='vim', shell_title='')
        self.ae(content.resolve_title(tab, sticky=False), 'vim')
        idle = make_tab(tab_id=-1, program_title='', shell_title='')
        self.ae(content.resolve_title(idle, sticky=True), 'vim')   # cached from prior call
        self.ae(content.resolve_title(idle, sticky=False), '')
