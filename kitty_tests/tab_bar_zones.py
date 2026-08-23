#!/usr/bin/env python
# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>
from . import BaseTest


class TestTabBarZones(BaseTest):
    def test_flat_zone_cells(self):
        # Zones render flat: [icon][' '][parts] on the bar background (bg 0),
        # mirrored as [parts][' '][icon]. No pill chrome glyphs, parts keep
        # their own fg colors, the icon is bold in its own color.
        from kitty.tab_bar_zones import draw

        zc = draw.ZoneContent(icon='I', parts=(('aa', 7), ('bb', 8)), icon_color=2)

        cells = draw._zone_cells(zc)
        self.ae([g for _, _, _, g in cells], ['I', ' ', 'aa', 'bb'])
        self.assertTrue(all(bg == 0 for bg, _, _, _ in cells))
        self.ae(cells[0][1:3], (2, True))  # icon color, bold
        self.ae([fg for _, fg, _, _ in cells[2:]], [7, 8])

        mirrored = draw._zone_cells(zc, mirrored=True)
        self.ae([g for _, _, _, g in mirrored], ['aa', 'bb', ' ', 'I'])
        self.ae(mirrored[-1][1:3], (2, True))

        # widths match the drawn cells for both layouts
        self.ae(draw._zone_width(zc), 6)
        self.ae(draw._zone_width(zc, mirrored=True), 6)

        # empty text parts (always-visible zone) collapse to just the icon
        empty = draw.ZoneContent(icon='I', parts=(('', 7),), icon_color=2)
        self.ae([g for _, _, _, g in draw._zone_cells(empty)], ['I'])
        self.ae([g for _, _, _, g in draw._zone_cells(empty, mirrored=True)], ['I'])

        # empty icon reserves no cell and no gap: parts only, exact width
        no_icon = draw.ZoneContent(icon='', parts=(('title', 7),), icon_color=2)
        self.ae([g for _, _, _, g in draw._zone_cells(no_icon, mirrored=True)], ['title'])
        self.ae(draw._zone_width(no_icon, mirrored=True), 5)

    def test_config_reads_options(self):
        from kitty.tab_bar_zones.config import get_config, clear_caches

        clear_caches()
        self.set_options(
            {
                'tab_bar_zone_left': ('cwd_git',),
                'tab_bar_zone_right': ('tab_label', 'title'),
                'tab_bar_sticky_last_cmd': True,
                'tab_bar_content_separator': ' · ',
                'tab_bar_pill_spacing': 2,
            }
        )
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
        self.ae(cfg.icon_for('myprog'), 'Z')  # override wins
        self.ae(cfg.icon_for('kitty'), chr(0xF011B))  # built-in default (Nerd Font U+F011B)
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

        raw = '# branch.head main\n1 DD N... 100644 100644 100644 aaa bbb gone\n'
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

    def test_icon_exe_candidates(self):
        from kitty.tab_bar_zones import content

        def P(pid, *cmd):
            return {'pid': pid, 'cmdline': list(cmd)}

        # the group leader (pid == pgrp) wins; transient children (git
        # spawned by lazygit) must not flicker the icon
        self.ae(content._icon_exe_candidates([P(200, 'lazygit'), P(300, 'git', 'status')], 200, None), ['lazygit'])
        # pid wraparound: children with *lower* pids than the leader
        # (observed live: gh pid 2951 vs claude pid 94728) must not win
        self.ae(content._icon_exe_candidates([P(2951, 'gh', 'pr', 'view'), P(94728, 'claude', '--resume')], 94728, None), ['claude'])
        # interpreters unwrap to their script; PROC (typed word) comes last
        self.ae(content._icon_exe_candidates([P(10, 'node', '/x/y/claude'), P(20, 'caffeinate')], 10, 'cc'), ['claude', 'node', 'cc'])
        # interpreter flags are skipped when finding the script
        self.ae(content._icon_exe_candidates([P(1, 'python3', '-u', '/x/tool.py')], 1, None), ['tool.py', 'python3'])
        # shell leader with a non-shell member (wrapper script case)
        self.ae(content._icon_exe_candidates([P(100, '/bin/zsh'), P(200, 'vim')], 100, None), ['vim'])
        # all shells -> the shell itself (login dash stripped)
        self.ae(content._icon_exe_candidates([P(5, '-zsh')], 5, None), ['zsh'])
        # unreadable cmdline and dead pid: skipped; PROC still usable
        self.ae(content._icon_exe_candidates([{'pid': None, 'cmdline': None}], -1, 'lg'), ['lg'])
        self.ae(content._icon_exe_candidates([], -1, None), [])

    def test_icon_exe_candidates_session_wrapper(self):
        from kitty.tab_bar_zones import content

        def P(pid, *cmd):
            return {'pid': pid, 'cmdline': list(cmd)}

        # Windows kitty persisted itself never reach here -- Child resolves the
        # session pid and reports the real process group. This is the fallback
        # for a wrapper kitty did not start (a hand-run `zmx attach`), where the
        # client argv is the only thing left to read.
        self.ae(content._icon_exe_candidates([P(10, 'zmx', 'attach', 'kitty-a3f9', '/bin/zsh')], 10, None), ['zsh'])
        # PROC is the only view of what the invisible shell is running, so here
        # it outranks the wrapped argv rather than trailing it
        self.ae(content._icon_exe_candidates([P(10, 'zmx', 'attach', 'kitty-a3f9', '/bin/zsh')], 10, 'nvim'), ['nvim', 'zsh'])
        # a wrapped explicit command names itself
        self.ae(content._icon_exe_candidates([P(10, 'zmx', 'attach', 'work', 'nvim', 'foo.txt')], 10, None), ['nvim'])
        # login-shell dash is stripped like anywhere else
        self.ae(content._icon_exe_candidates([P(10, '/usr/bin/zmx', 'attach', 'work', '-zsh')], 10, None), ['zsh'])
        # bare `zmx attach <name>`: launch() leaves shell resolution to the child,
        # so nothing is there to unwrap and zmx spawns a login shell of its own
        sh = content._default_shell_name()
        self.assertTrue(sh)
        self.ae(content._icon_exe_candidates([P(10, 'zmx', 'attach', 'work')], 10, 'lg'), ['lg', sh])
        self.ae(content._icon_exe_candidates([P(10, 'zmx', 'attach', 'work')], 10, None), [sh])
        # an unrelated binary that merely starts with zmx is not a wrapper
        self.ae(content._icon_exe_candidates([P(10, 'zmxctl', 'attach', 'x', 'y')], 10, None), ['zmxctl'])

    def test_pick_exe_for_icon(self):
        from kitty.tab_bar_zones import content
        from kitty.tab_bar_zones.config import clear_caches

        clear_caches()
        self.set_options({})
        # first candidate with a real icon mapping wins
        self.ae(content._pick_exe_for_icon(['unknown-xyz', 'node']), 'node')
        # no mapped candidate: first candidate (renders the fallback icon)
        self.ae(content._pick_exe_for_icon(['unknown-xyz', 'also-unknown']), 'unknown-xyz')
        # user overrides count as mappings
        clear_caches()
        self.set_options({'tab_bar_icon': {'myalias': 'Z'}})
        self.ae(content._pick_exe_for_icon(['myalias', 'node']), 'myalias')
        clear_caches()

    def test_pad_pua_icon(self):
        # PUA glyphs followed by a space render as a 2-cell ligature that
        # swallows the space; pad_pua_icon adds one back so a visible gap
        # survives. Non-PUA text must pass through untouched.
        from kitty.tab_bar_zones.text import pad_pua_icon

        self.ae(pad_pua_icon(''), ' ')  # BMP PUA (nerd font)
        self.ae(pad_pua_icon('\U000f011b'), '\U000f011b ')  # SPUA-A (nerd font)
        self.ae(pad_pua_icon('1 '), '1  ')  # pads composed strings too
        self.ae(pad_pua_icon('LEADER'), 'LEADER')  # plain text untouched
        self.ae(pad_pua_icon('\U0001f980'), '\U0001f980')  # emoji is not PUA
        self.ae(pad_pua_icon(''), '')

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

    def test_pill_cells_are_the_only_layout(self):
        # Width and drawing derive from one cell list, so they cannot drift:
        # this is the defect class the pill kept regressing into. The drawn
        # cursor advance is the ground truth _pill_width has to match.
        from kitty.tab_bar_zones import draw

        bl, br = '', ''

        def pill(icon):
            return draw.TabContent(icon=icon, icon_fg=1, icon_bg=2)

        for icon, expected in (
            ('', 6),  # icon only: the shipped configuration
            ('1', 6),  # index only: same width, pills stay uniform
            ('', 6),  # no content at all still draws a pill
            ('1 ', 8),  # index + icon: body grows rather than clipping
        ):
            content = pill(icon)
            cells = draw._pill_cells(content, bl, br)
            summed = sum(draw._display_width(text) for _, _, _, text in cells)
            self.ae(draw._pill_width(content, bl, br), summed, f'width != cells for {icon!r}')
            self.ae(summed, expected, f'unexpected width for {icon!r}')

            screen = self.create_screen(cols=40, lines=1)
            screen.cursor.x = 0
            draw._draw_pill(screen, content, bl, br)
            self.ae(screen.cursor.x, expected, f'drawn advance != width for {icon!r}')

    def test_pill_centres_content_in_the_body(self):
        # The body is a fixed run of pill-coloured cells with the content
        # centred on it; the caps sit on the bar background at either end.
        from kitty.tab_bar_zones import draw

        bl, br = '', ''
        content = draw.TabContent(icon='', icon_fg=1, icon_bg=2)
        cells = draw._pill_cells(content, bl, br)

        self.ae([text for _, _, _, text in cells], [bl, ' ', ' ', ' ', br])
        # caps: pill colour as fg on the bar background
        self.ae(cells[0][:3], (0, 2, False))
        self.ae(cells[-1][:3], (0, 2, False))
        # body: pill background throughout, icon bold
        self.assertTrue(all(bg == 2 for bg, _, _, _ in cells[1:-1]))
        self.ae(cells[2][2], True)

        # lead == (body - content) // 2 for every combination of content width
        for icon, lead, trail in (
            ('', 1, 1),  # content 2 in body 4
            ('1', 1, 2),  # content 1 in body 4
            ('', 2, 2),  # content 0 in body 4
            ('1 ', 1, 1),  # content 4 in body 6
        ):
            cells = draw._pill_cells(draw.TabContent(icon=icon, icon_fg=1, icon_bg=2), '', '')
            texts = [text for _, _, _, text in cells]
            body = sum(draw._display_width(t) for t in texts)
            content_w = draw._display_width(draw.pad_pua_icon(icon))
            if icon:
                got_lead = draw._display_width(texts[0]) if texts[0].strip() == '' else 0
                got_trail = draw._display_width(texts[-1]) if texts[-1].strip() == '' else 0
            else:  # no icon cell at all: the body is lead + trail
                got_lead, got_trail = (draw._display_width(t) for t in texts)
            self.ae((got_lead, got_trail), (lead, trail), f'off centre for {icon!r}')
            self.ae(got_lead, (body - content_w) // 2, f'lead is not the centring rule for {icon!r}')
            self.ae(got_lead + content_w + got_trail, body, f'cells do not fill the body for {icon!r}')

    def test_pill_never_splits_a_pua_icon_from_its_pad(self):
        # A PUA glyph and the space after it shape into one two-cell ligature
        # with the glyph centred across both cells. Emitting the glyph alone
        # draws a two-cell glyph into one cell — the sliced icon. The pair is
        # built here so no caller is able to split it.
        from kitty.tab_bar_zones import draw

        for icon in ('', '1 ', '\U000f011b'):
            cells = draw._pill_cells(draw.TabContent(icon=icon, icon_fg=1, icon_bg=2), '', '')
            for _, _, _, text in cells:
                if icon[-1] in text:
                    self.assertTrue(text.endswith(' '), f'{icon!r} emitted without its pad')
                    self.ae(draw._display_width(text), draw._display_width(icon) + 1)
                    break
            else:
                self.fail(f'{icon!r} never appeared in the cell list')

    def test_truncate_text_keeps_pua_icon_whole(self):
        # A PUA glyph and the space pad_pua_icon appends are one two-cell
        # ligature. Emitting the glyph without its space leaves the font drawing
        # a two-cell glyph into one cell, which renders as a sliced icon, so the
        # pair has to be dropped together.
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

        # last component itself wider than budget -> hits the final hard truncate
        out = abbreviate_path('/x/日本語日本語日本語', 6, '/none', '…')
        self.assertLessEqual(display_width(out), 6)

    def test_color_resolver(self):
        from kitty.tab_bar_zones.colors import ColorResolver
        from kitty.tab_bar import as_rgb
        from kitty.fast_data_types import Color

        r = ColorResolver(
            active_fg=Color(1, 2, 3), active_bg=Color(4, 5, 6), inactive_fg=Color(7, 8, 9), inactive_bg=Color(10, 11, 12), default_bg=Color(13, 14, 15)
        )
        # a plain Color resolves to its as_rgb int
        self.ae(r.to_int(Color(255, 0, 0)), as_rgb(0xFF0000))
        # the live theme sentinels resolve to DrawData colors
        self.ae(r.to_int('active_tab_background'), as_rgb(0x040506))
        self.ae(r.to_int('inactive_tab_background'), as_rgb(0x0A0B0C))
        # None falls back to gray
        self.ae(r.to_int(None), as_rgb(0xCCCCCC))

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
        self.ae(content.resolve_title(idle, sticky=True), 'vim')  # cached from prior call
        self.ae(content.resolve_title(idle, sticky=False), '')
