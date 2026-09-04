# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>
"""Content engine for the zones tab-bar style: icons, text and colors per pill and zone."""

from __future__ import annotations

import os
from functools import lru_cache

from ..fast_data_types import Color, get_boss, get_options
from ..options.types import Options
from ..options.utils import GIT_STATUS_FIELDS
from ..tab_bar import DrawData, TabAccessor, TabBarData, as_rgb
from ..utils import color_as_int, known_shell_names
from . import gitstatus
from .config import has_icon, icon_for
from .draw import TabContent, ZoneContent
from .text import abbreviate_path, display_width, pad_pua_icon, truncate_text

_HOME = os.path.expanduser('~')

Parts = tuple[tuple[str, int], ...]


def to_int(color: Color | None) -> int:
    return as_rgb(0xCCCCCC) if color is None else as_rgb(color_as_int(color))


_last_titles: dict[int, str] = {}
_LAST_TITLES_MAX = 50


def resolve_title(tab: TabBarData, sticky: bool) -> str:
    """override_title -> cmd_title -> sticky cache (when *sticky* and the rest are empty)."""
    if tab.cmd_title:
        if len(_last_titles) >= _LAST_TITLES_MAX:
            _last_titles.clear()
        _last_titles[tab.tab_id] = tab.cmd_title
    title = tab.override_title or tab.cmd_title
    if not title and sticky:
        title = _last_titles.get(tab.tab_id, '')
    return title or ''


def clear_caches() -> None:
    _last_titles.clear()
    _default_shell_name.cache_clear()


_INTERPRETERS = {
    'node',
    'bun',
    'deno',
    'python',
    'python2',
    'python3',
    'ruby',
    'perl',
    'lua',
    'luajit',
}


_SESSION_WRAPPERS = {'zmx'}


def _unwrap_session_cmdline(name: str, cmdline: list[str]) -> list[str] | None:
    """The argv the wrapper was asked to run, or None if this is not a wrapper.

    `zmx attach <session> [command...]` -- an empty list means no command was
    given, which is distinct from "not a wrapper" and so is not None.
    """
    if name not in _SESSION_WRAPPERS or len(cmdline) < 3:
        return None
    return cmdline[3:]


@lru_cache(maxsize=1)
def _default_shell_name() -> str:
    """Basename of the login shell a bare `zmx attach <name>` spawns for itself."""
    try:
        from ..utils import resolved_shell

        return os.path.basename(resolved_shell()[0]).lstrip('-')
    except Exception:
        return ''


def _proc_name(p: dict) -> tuple[str, list[str]]:
    """(basename, cmdline) for a ProcessDesc; empty name if unknowable.

    cmdline can be transiently unreadable (mid-exec, huge argv); the
    executable path via proc_pidpath is a second, more reliable source.
    """
    cmdline = p.get('cmdline') or []
    if cmdline and cmdline[0]:
        return os.path.basename(cmdline[0]).lstrip('-'), cmdline
    pid = p.get('pid')
    if pid:
        try:
            from ..child import abspath_of_exe

            return os.path.basename(abspath_of_exe(pid)), []
        except Exception:
            pass
    return '', []


def _icon_exe_candidates(procs: 'list[dict]', pgrp: int, proc_var: str | None) -> list[str]:
    """Best-first icon-name candidates for a foreground process group.

    Anchored on the group leader (pid == pgrp): it is the process the shell forked for
    the typed command, so it is immune to both transient children and macOS pid wraparound.
    """
    shells = known_shell_names()
    candidates: list[str] = []
    main: tuple[str, list[str]] | None = None
    shell: tuple[str, list[str]] | None = None

    leader = next((p for p in procs if p.get('pid') == pgrp), None)
    if leader is not None:
        name, cmdline = _proc_name(leader)
        wrapped = _unwrap_session_cmdline(name, cmdline)
        if wrapped is not None:
            candidates = [proc_var] if proc_var and proc_var not in shells else []
            inner = os.path.basename(wrapped[0]).lstrip('-') if wrapped and wrapped[0] else _default_shell_name()
            if inner:
                candidates.append(inner)
            return candidates
        if name and name not in shells:
            main = (name, cmdline)
        elif name:
            shell = (name, cmdline)
    if main is None:
        for p in sorted(procs, key=lambda p: p.get('pid') or 0):
            if p is leader:
                continue
            name, cmdline = _proc_name(p)
            if not name:
                continue
            if name in shells:
                if shell is None:
                    shell = (name, cmdline)
                continue
            main = (name, cmdline)
            break
    if main is None:
        main = shell
    if main is not None:
        name, cmdline = main
        if name in _INTERPRETERS and len(cmdline) > 1:
            for arg in cmdline[1:]:
                if arg and not arg.startswith('-'):
                    candidates.append(os.path.basename(arg))
                    break
        candidates.append(name)
    if proc_var and proc_var not in shells:
        candidates.append(proc_var)
    return candidates


def _pick_exe_for_icon(candidates: list[str]) -> str:
    """First candidate with an explicit icon mapping, else the first."""
    for c in candidates:
        if c and has_icon(c):
            return c
    return candidates[0]


def get_foreground_process(tab_id: int) -> tuple[str, str, str | None]:
    """Return (exe, cwd, remote_host) for the tab's foreground process."""
    try:
        ta = TabAccessor(tab_id)
        exe = ta.active_exe or 'zsh'
        cwd = ta.active_wd or ''

        remote_host = None
        try:
            boss = get_boss()
            tab = boss.tab_for_id(tab_id)
            if tab and tab.active_window:
                window = tab.active_window
                user_vars = window.user_vars
                remote_host = user_vars.get('REMOTE_HOST') or None
                remote_cwd = user_vars.get('REMOTE_CWD')
                if remote_cwd:
                    cwd = remote_cwd
                proc = user_vars.get('PROC')
                if remote_host:
                    if proc and proc not in known_shell_names():
                        exe = proc
                elif proc and proc in get_options().tab_bar_icon:
                    exe = proc
                else:
                    try:
                        procs = window.child.foreground_processes
                    except Exception:
                        procs = []
                    pgrp = -1
                    for p in procs:
                        pid = p.get('pid')
                        if pid:
                            try:
                                pgrp = os.getpgid(pid)
                            except Exception:
                                continue
                            break
                    candidates = _icon_exe_candidates(procs, pgrp, proc)
                    if candidates:
                        exe = _pick_exe_for_icon(candidates)
        except Exception:
            pass

        return (exe, cwd, remote_host)
    except Exception:
        return ('zsh', '', None)


def get_keyboard_mode() -> str:
    try:
        mode = get_boss().mappings.current_keyboard_mode_name
        return mode if mode else ''
    except Exception:
        return ''


def tab_content(
    tab: TabBarData,
    index: int,
    is_active: bool,
    draw_data: DrawData,
) -> TabContent:
    """Return display content for a single tab pill (icon + index only)."""
    exe, _cwd, _hostname = get_foreground_process(tab.tab_id)

    icon_parts = []
    for element in get_options().tab_bar_icon_elements:
        if element == 'index':
            icon_parts.append(str(index))
        elif element == 'icon':
            icon_parts.append(icon_for(exe))
    icon = ' '.join(icon_parts) if icon_parts else str(index)

    if is_active:
        icon_bg, icon_fg = to_int(draw_data.active_bg), to_int(draw_data.active_fg)
    else:
        icon_bg, icon_fg = to_int(draw_data.inactive_bg), to_int(draw_data.inactive_fg)

    return TabContent(icon=icon, icon_fg=icon_fg, icon_bg=icon_bg)


def _render_cwd_git(
    active_tab: TabBarData,
    proc: tuple[str, str, str | None],
    text_budget: int,
    opts: Options,
) -> Parts | None:
    """Compound cwd + git renderer.

    Progressive collapse on tight budgets:
        cwd + full_git  ->  full_git only  ->  branch_only  ->  empty
    """
    _exe, cwd, hostname = proc

    git_data = None
    if cwd and not hostname:
        git_data = gitstatus.get_git_status(cwd)

    if git_data:
        branch, counts = git_data
        full = _format_git_parts(branch, counts, False, opts)
        branch_only = _format_git_parts(branch, counts, True, opts)
        full_len = sum(display_width(t) for t, _ in full)
        branch_len = sum(display_width(t) for t, _ in branch_only)

        cwd_text = abbreviate_path(cwd, text_budget - full_len - 1, _HOME, opts.tab_bar_ellipsis)
        if cwd_text and display_width(cwd_text) + 1 + full_len <= text_budget:
            parts: list[tuple[str, int]] = [(cwd_text + ' ', to_int(opts.tab_bar_git_directory_color))]
            parts.extend(full)
            return tuple(parts)
        if full_len <= text_budget:
            return tuple(full)
        if branch_len <= text_budget:
            return tuple(branch_only)
        return None

    cwd_text = abbreviate_path(cwd, text_budget, _HOME, opts.tab_bar_ellipsis) if cwd else None
    if cwd_text:
        return ((cwd_text, to_int(opts.tab_bar_git_directory_color)),)
    return None


def _render_text_parts(text: str, text_budget: int, opts: Options) -> Parts | None:
    """Truncate *text* to the zone budget, or None below tab_bar_min_text_budget."""
    if not text or text_budget < opts.tab_bar_min_text_budget:
        return None
    if display_width(text) > text_budget:
        text = truncate_text(text, text_budget, opts.tab_bar_ellipsis)
    text_fg = opts.tab_bar_zone_text_fg if opts.tab_bar_zone_text_fg is not None else opts.foreground
    return ((text, to_int(text_fg)),)


def _render_title(
    active_tab: TabBarData,
    proc: tuple[str, str, str | None],
    text_budget: int,
    opts: Options,
) -> Parts | None:
    """Active tab title with sticky-cache fallback."""
    return _render_text_parts(resolve_title(active_tab, opts.tab_bar_sticky_last_cmd), text_budget, opts)


def _render_tab_label(
    active_tab: TabBarData,
    proc: tuple[str, str, str | None],
    text_budget: int,
    opts: Options,
) -> Parts | None:
    """User-set tab name (Tab.name, set by set_tab_title)."""
    return _render_text_parts(active_tab.tab_name or '', text_budget, opts)


_RENDERERS = {
    'cwd_git': _render_cwd_git,
    'title': _render_title,
    'tab_label': _render_tab_label,
}


def zone_content(active_tab: TabBarData, draw_data: DrawData, max_width: int, left: bool) -> ZoneContent | None:
    """Render one zone: its icon (with SSH/mode override) plus the configured content kinds."""
    opts = get_options()
    kinds = opts.tab_bar_zone_left if left else opts.tab_bar_zone_right
    if not kinds:
        return None

    mode = get_keyboard_mode()
    proc = get_foreground_process(active_tab.tab_id)
    hostname = proc[2]
    ssh_icon = opts.tab_bar_left_ssh_icon if left else opts.tab_bar_right_ssh_icon

    if mode and left and opts.tab_bar_left_mode_indicator:
        icon = opts.tab_bar_mode_name.get(mode, mode.upper())
    elif hostname and ssh_icon:
        icon = ssh_icon
    else:
        icon = opts.tab_bar_left_icon if left else opts.tab_bar_right_icon
    icon = pad_pua_icon(icon)

    if mode and opts.tab_bar_mode_bg is not None:
        icon_color = to_int(opts.tab_bar_mode_bg)
    else:
        icon_color = to_int(draw_data.active_bg)

    overhead = display_width(icon) + 1 if icon else 0
    text_budget = max_width - overhead
    if text_budget < opts.tab_bar_min_text_budget:
        return None

    sep = opts.tab_bar_content_separator
    sep_width = display_width(sep)

    merged_parts: list[tuple[str, int]] = []
    used_width = 0

    for kind in kinds:
        renderer = _RENDERERS.get(kind)
        if renderer is None:
            continue
        remaining = text_budget - used_width
        if merged_parts:
            remaining -= sep_width
        if remaining <= 0:
            break
        kind_parts = renderer(active_tab, proc, remaining, opts)
        if not kind_parts:
            continue
        kind_width = sum(display_width(t) for t, _ in kind_parts)
        if kind_width == 0:
            continue
        if merged_parts:
            merged_parts.append((sep, merged_parts[-1][1]))
            used_width += sep_width
        merged_parts.extend(kind_parts)
        used_width += kind_width

    return ZoneContent(icon=icon, parts=tuple(merged_parts), icon_color=icon_color)


def _format_git_parts(branch: str, counts: dict[str, int], branch_only: bool, opts: Options) -> list[tuple[str, int]]:
    """Format git info into (text, color_int) pairs."""
    parts: list[tuple[str, int]] = []

    branch_icon_glyph = opts.tab_bar_git_branch_icon
    if branch_icon_glyph:
        parts.append((pad_pua_icon(branch_icon_glyph) + ' ', to_int(opts.tab_bar_git_branch_icon_color)))
    parts.append((branch, to_int(opts.tab_bar_git_branch_color)))

    if branch_only:
        return parts

    status_parts: list[tuple[str, int]] = []
    git_status = opts.tab_bar_git_status
    for key in GIT_STATUS_FIELDS:
        if counts.get(key, 0) <= 0:
            continue
        entry = git_status.get(key)
        if not entry:
            continue
        glyph, color = entry
        status_parts.append((f'{glyph}{counts[key]}', to_int(color)))

    if status_parts:
        sep_color = to_int(opts.tab_bar_git_branch_color)
        parts.append((' ', sep_color))
        for i, (text, color) in enumerate(status_parts):
            if i > 0:
                parts.append((' ', sep_color))
            parts.append((text, color))

    return parts
