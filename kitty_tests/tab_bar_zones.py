#!/usr/bin/env python
# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>
from .base import BaseTest


class TestTabBarZones(BaseTest):
    def test_flat_zone_cells(self):
        from kitty.tab_bar_zones import draw

        zc = draw.ZoneContent(icon='I', parts=(('aa', 7), ('bb', 8)), icon_color=2)

        cells = draw._zone_cells(zc)
        self.ae([g for _, _, _, g in cells], ['I', ' ', 'aa', 'bb'])
        self.assertTrue(all(bg == 0 for bg, _, _, _ in cells))
        self.ae(cells[0][1:3], (2, True))
        self.ae([fg for _, fg, _, _ in cells[2:]], [7, 8])

        mirrored = draw._zone_cells(zc, mirrored=True)
        self.ae([g for _, _, _, g in mirrored], ['aa', 'bb', ' ', 'I'])
        self.ae(mirrored[-1][1:3], (2, True))

        self.ae(draw._zone_width(zc), 6)

        empty = draw.ZoneContent(icon='I', parts=(), icon_color=2)
        self.ae([g for _, _, _, g in draw._zone_cells(empty)], ['I'])

        no_icon = draw.ZoneContent(icon='', parts=(('title', 7),), icon_color=2)
        self.ae([g for _, _, _, g in draw._zone_cells(no_icon, mirrored=True)], ['title'])
        self.ae(draw._zone_width(no_icon), 5)

    def test_icon_default_and_override(self):
        from kitty.tab_bar_zones.config import DEFAULT_ICON_FALLBACK, icon_for

        self.set_options({'tab_bar_icon': {'myprog': 'Z'}})
        self.ae(icon_for('myprog'), 'Z')
        self.ae(icon_for('kitty'), chr(0xF011B))
        self.ae(icon_for('unknown-xyz'), DEFAULT_ICON_FALLBACK)

    def test_parse_git_output(self):
        from kitty.tab_bar_zones.gitstatus import parse_git_output

        raw = (
            '# branch.head main\n'
            '# branch.ab +2 -1\n'
            '1 .M N... 100644 100644 100644 aaa bbb file1\n'
            '1 M. N... 100644 100644 100644 aaa bbb file2\n'
            '? untracked.txt\n'
            'u UU N... ...\n'
            '# stash 3\n'
        )
        branch, counts = parse_git_output(raw)
        self.ae(branch, 'main')
        self.ae(counts['ahead'], 2)
        self.ae(counts['behind'], 1)
        self.ae(counts['modified'], 1)
        self.ae(counts['staged'], 1)
        self.ae(counts['untracked'], 1)
        self.ae(counts['conflicted'], 1)
        self.ae(counts['stashed'], 3)

    def test_parse_git_output_no_double_count_delete(self):
        from kitty.tab_bar_zones.gitstatus import parse_git_output

        raw = '# branch.head main\n1 DD N... 100644 100644 100644 aaa bbb gone\n'
        _, counts = parse_git_output(raw)
        self.ae(counts['deleted'], 1)
        self.ae(counts['modified'], 0)

    def test_find_git_dir_relative_gitdir_pointer(self):
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
        long = home + '/aaaaaa/bbbbbb/cccccc/target'
        out = abbreviate_path(long, 20, home, '…')
        self.assertLessEqual(len(out), 20)
        self.assertTrue(out.endswith('target'))

    def test_icon_exe_candidates(self):
        from kitty.tab_bar_zones import content

        def P(pid, *cmd):
            return {'pid': pid, 'cmdline': list(cmd)}

        self.ae(content._icon_exe_candidates([P(200, 'lazygit'), P(300, 'git', 'status')], 200, None), ['lazygit'])
        self.ae(content._icon_exe_candidates([P(2951, 'gh', 'pr', 'view'), P(94728, 'claude', '--resume')], 94728, None), ['claude'])
        self.ae(content._icon_exe_candidates([P(10, 'node', '/x/y/claude'), P(20, 'caffeinate')], 10, 'cc'), ['claude', 'node', 'cc'])
        self.ae(content._icon_exe_candidates([P(1, 'python3', '-u', '/x/tool.py')], 1, None), ['tool.py', 'python3'])
        self.ae(content._icon_exe_candidates([P(100, '/bin/zsh'), P(200, 'vim')], 100, None), ['vim'])
        self.ae(content._icon_exe_candidates([P(5, '-zsh')], 5, None), ['zsh'])
        self.ae(content._icon_exe_candidates([{'pid': None, 'cmdline': None}], -1, 'lg'), ['lg'])
        self.ae(content._icon_exe_candidates([], -1, None), [])

    def test_icon_exe_candidates_session_wrapper(self):
        from kitty.tab_bar_zones import content

        def P(pid, *cmd):
            return {'pid': pid, 'cmdline': list(cmd)}

        self.ae(content._icon_exe_candidates([P(10, 'zmx', 'attach', 'kitty-a3f9', '/bin/zsh')], 10, None), ['zsh'])
        self.ae(content._icon_exe_candidates([P(10, 'zmx', 'attach', 'kitty-a3f9', '/bin/zsh')], 10, 'nvim'), ['nvim', 'zsh'])
        self.ae(content._icon_exe_candidates([P(10, 'zmx', 'attach', 'work', 'nvim', 'foo.txt')], 10, None), ['nvim'])
        self.ae(content._icon_exe_candidates([P(10, '/usr/bin/zmx', 'attach', 'work', '-zsh')], 10, None), ['zsh'])
        sh = content._default_shell_name()
        self.assertTrue(sh)
        self.ae(content._icon_exe_candidates([P(10, 'zmx', 'attach', 'work')], 10, 'lg'), ['lg', sh])
        self.ae(content._icon_exe_candidates([P(10, 'zmx', 'attach', 'work')], 10, None), [sh])
        self.ae(content._icon_exe_candidates([P(10, 'zmxctl', 'attach', 'x', 'y')], 10, None), ['zmxctl'])

    def test_pick_exe_for_icon(self):
        from kitty.tab_bar_zones import content
        from kitty.tab_bar_zones.config import clear_caches

        clear_caches()
        self.set_options({})
        self.ae(content._pick_exe_for_icon(['unknown-xyz', 'node']), 'node')
        self.ae(content._pick_exe_for_icon(['unknown-xyz', 'also-unknown']), 'unknown-xyz')
        clear_caches()
        self.set_options({'tab_bar_icon': {'myalias': 'Z'}})
        self.ae(content._pick_exe_for_icon(['myalias', 'node']), 'myalias')
        clear_caches()

    def test_pad_pua_icon(self):
        from kitty.tab_bar_zones.text import pad_pua_icon

        self.ae(pad_pua_icon(''), ' ')
        self.ae(pad_pua_icon('\U000f011b'), '\U000f011b ')
        self.ae(pad_pua_icon('1 '), '1  ')
        self.ae(pad_pua_icon('LEADER'), 'LEADER')
        self.ae(pad_pua_icon('\U0001f980'), '\U0001f980')
        self.ae(pad_pua_icon(''), '')

    def test_truncate_text_respects_display_width(self):
        from kitty.tab_bar_zones.text import display_width, truncate_text

        out = truncate_text('日本語abc', 5, '…')
        self.assertLessEqual(display_width(out), 5)
        self.assertTrue(out.endswith('…'))
        self.assertLessEqual(display_width(truncate_text('日本語', 1, '…')), 1)
        self.ae(truncate_text('abcdef', 4, '…'), 'abc…')

    def test_pill_layout(self):
        from kitty.tab_bar_zones import draw

        bl, br = '\ue0b6', '\ue0b4'
        # icon, drawn width including both caps, lead pad, trail pad
        for icon, width, lead, trail in (
            ('\ue6ae', 6, 1, 1),
            ('1', 6, 1, 2),
            ('', 6, 2, 2),
            ('1 \ue6ae', 8, 1, 1),
            ('\U000f011b', 6, 1, 1),
        ):
            content = draw.TabContent(icon=icon, icon_fg=1, icon_bg=2)
            cells = draw._pill_cells(content, bl, br)
            texts = [t for _, _, _, t in cells]
            self.ae(sum(draw.display_width(t) for t in texts), width, f'unexpected width for {icon!r}')
            self.ae(draw._pill_width(content, bl, br), width, f'width != cells for {icon!r}')

            screen = self.create_screen(cols=40, lines=1)
            screen.cursor.x = 0
            draw._draw_pill(screen, content, bl, br)
            self.ae(screen.cursor.x, width, f'drawn advance != width for {icon!r}')

            self.ae(cells[0][:3], (0, 2, False))
            self.ae(cells[-1][:3], (0, 2, False))
            self.assertTrue(all(bg == 2 for bg, _, _, _ in cells[1:-1]), f'body not pill coloured for {icon!r}')
            padded = draw.pad_pua_icon(icon)
            self.ae((draw.display_width(texts[1]), draw.display_width(texts[-2])), (lead, trail), f'off centre for {icon!r}')
            self.ae(lead, (width - 2 - draw.display_width(padded)) // 2, f'lead is not the centring rule for {icon!r}')
            if icon:
                self.assertIn(padded, texts, f'{icon!r} emitted split from its pad')
                self.ae(cells[2][2], True, f'icon not bold for {icon!r}')

    def test_truncate_text_keeps_pua_icon_whole(self):
        from kitty.tab_bar_zones.text import display_width, pad_pua_icon, truncate_text

        icon = pad_pua_icon('')
        self.ae(display_width(icon), 2)
        text = icon + 'nvim'
        for budget in range(1, display_width(text) + 2):
            out = truncate_text(text, budget, '…')
            self.assertLessEqual(display_width(out), budget, f'overflowed at budget={budget}')
            if '' in out:
                self.assertIn(icon, out, f'icon split from its space at budget={budget}')

    def test_abbreviate_path_respects_display_width(self):
        from kitty.tab_bar_zones.text import abbreviate_path, display_width

        out = abbreviate_path('/x/日本語日本語日本語', 6, '/none', '…')
        self.assertLessEqual(display_width(out), 6)

    def test_to_int(self):
        from kitty.fast_data_types import Color
        from kitty.tab_bar import as_rgb
        from kitty.tab_bar_zones.content import to_int

        self.ae(to_int(Color(255, 0, 0)), as_rgb(0xFF0000))
        self.ae(to_int(Color(4, 5, 6)), as_rgb(0x040506))
        self.ae(to_int(None), as_rgb(0xCCCCCC))

    def test_title_renderer_sticky(self):
        from kitty.tab_bar import TabBarData
        from kitty.tab_bar_zones import content

        content.clear_caches()

        def make_tab(cmd_title):
            return TabBarData(title='', tab_id=-1, cmd_title=cmd_title, override_title='')

        tab = make_tab('vim')
        self.ae(content.resolve_title(tab, sticky=False), 'vim')
        idle = make_tab('')
        self.ae(content.resolve_title(idle, sticky=True), 'vim')
        self.ae(content.resolve_title(idle, sticky=False), '')
