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
