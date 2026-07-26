# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>
"""Content engine for the zones tab-bar style.

Ported from the config-side tab_bar.py. Provides:
  - tab_content()         : icon, text, and colors for each tab pill
  - left_zone_content()   : configured content kinds for the left zone
  - right_zone_content()  : configured content kinds for the right zone
  - get_engine_callables(): returns (tab_content, left_zone_content, right_zone_content)
  - resolve_title()       : title precedence + sticky logic (exposed for testing)
  - clear_caches()        : reset sticky-title cache
"""
from __future__ import annotations
import os
from typing import Callable, NamedTuple

from ..fast_data_types import get_boss, get_options
from ..tab_bar import DrawData, TabBarData, TabAccessor, as_rgb
from .draw import TabContent, ZoneContent
from .config import get_config
from .colors import ColorResolver
from .text import abbreviate_path, truncate_text, display_width, pad_pua_icon
from . import gitstatus


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_HOME = os.path.expanduser('~')

_SHELLS = {
    'zsh',
    'bash',
    'fish',
    'sh',
    'nu',
    'tcsh',
    'dash',
    'ksh',
    'pwsh',
    'elvish',
    'xonsh',
    '-zsh',
    '-bash',
    '-fish',
    '-sh',
}

# Order matters: matches the source tabbar_config._GIT_STATUS_FIELDS
_GIT_STATUS_FIELDS: tuple[str, ...] = (
    'stashed',
    'deleted',
    'staged',
    'modified',
    'renamed',
    'untracked',
    'conflicted',
    'ahead',
    'behind',
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

Parts = tuple[tuple[str, int], ...]


class ZoneSpec(NamedTuple):
    """Per-zone rendering spec, built from ZonesConfig at dispatch time."""
    content: tuple[str, ...]
    icon: str
    ssh_icon: str
    min_text_budget: int
    show_mode_indicator: bool


# ---------------------------------------------------------------------------
# Sticky-title cache
# ---------------------------------------------------------------------------

_last_titles: dict[int, str] = {}
_LAST_TITLES_MAX = 50


def resolve_title(tab: TabBarData, sticky: bool) -> str:
    """Resolve the active title for *tab* with optional sticky fallback.

    Resolution order: override_title -> program_title -> shell_title ->
    sticky cache (when *sticky* is True and all of the above are empty).
    """
    current_cmd_title = tab.program_title or tab.shell_title
    if current_cmd_title:
        if len(_last_titles) >= _LAST_TITLES_MAX:
            _last_titles.clear()
        _last_titles[tab.tab_id] = current_cmd_title
    title = tab.override_title or tab.program_title or tab.shell_title
    if not title and sticky:
        title = _last_titles.get(tab.tab_id, '')
    return title or ''


def clear_caches() -> None:
    """Clear the sticky-title cache."""
    _last_titles.clear()


# ---------------------------------------------------------------------------
# Process detection
# ---------------------------------------------------------------------------

# Interpreters whose argv[1:] names the real program (node /path/claude).
_INTERPRETERS = {
    'node', 'bun', 'deno',
    'python', 'python2', 'python3',
    'ruby', 'perl', 'lua', 'luajit',
}


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

    The group *leader* (pid == pgrp) is the job's main process -- the thing
    the shell forked for the typed command. Anchoring on it is immune to
    both transient children (git spawned by lazygit, caffeinate spawned by
    claude) and macOS pid wraparound, which makes pid ordering meaningless
    as an age signal. When the leader is a shell or gone, fall back to the
    lowest-pid non-shell member. Interpreter processes additionally yield
    their script's basename as a stronger candidate. proc_var (the typed
    first word reported by shell integration; aliases expand, shell
    functions don't) comes last.
    """
    candidates: list[str] = []
    main: tuple[str, list[str]] | None = None
    shell: tuple[str, list[str]] | None = None

    leader = next((p for p in procs if p.get('pid') == pgrp), None)
    if leader is not None:
        name, cmdline = _proc_name(leader)
        if name and name not in _SHELLS:
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
            if name in _SHELLS:
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
    if proc_var and proc_var not in _SHELLS:
        candidates.append(proc_var)
    return candidates


def _pick_exe_for_icon(candidates: list[str]) -> str:
    """First candidate with an explicit icon mapping, else the first."""
    cfg = get_config()
    for c in candidates:
        if c and cfg.has_icon(c):
            return c
    return candidates[0]


def get_foreground_process(tab_id: int) -> tuple[str, str, str | None]:
    """Return (exe, cwd, remote_host) for the tab's foreground process."""
    try:
        ta = TabAccessor(tab_id)
        # active_exe is the exe the window was *launched* with (usually the
        # shell) -- only a fallback. The live foreground process below is
        # what should drive the icon.
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
                    # Remote session: the local foreground process is just
                    # ssh; the remote shell integration's PROC report is the
                    # only view of the real process.
                    if proc and proc not in _SHELLS:
                        exe = proc
                elif proc and proc in get_config().icon_overrides:
                    # An explicit tab_bar_icon mapping for the typed word
                    # (e.g. `tab_bar_icon lg ...`) beats process detection.
                    exe = proc
                else:
                    # Local: resolve from the live foreground process group.
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


# ---------------------------------------------------------------------------
# Keyboard mode
# ---------------------------------------------------------------------------

def get_keyboard_mode() -> str:
    try:
        mode = get_boss().mappings.current_keyboard_mode_name
        return mode if mode else ''
    except Exception:
        return ''


# ---------------------------------------------------------------------------
# tab_content: per-tab pill content
# ---------------------------------------------------------------------------

def tab_content(
    tab: TabBarData,
    index: int,
    is_active: bool,
    draw_data: DrawData,
) -> TabContent:
    """Return display content for a single tab pill (icon + index only)."""
    cfg = get_config()
    resolver = ColorResolver.from_draw_data(draw_data)

    exe, _cwd, _hostname = get_foreground_process(tab.tab_id)
    icon_str = cfg.icon_for(exe)

    # No PUA padding here: the pill's own trailing pad cell feeds the
    # icon's two-cell ligature, and the caps close it snugly.
    icon_parts = []
    for element in cfg.icon_elements:
        if element == 'index':
            icon_parts.append(str(index))
        elif element == 'icon':
            icon_parts.append(icon_str)
    icon = ' '.join(icon_parts) if icon_parts else str(index)

    if is_active:
        icon_bg = resolver.to_int('active_tab_background')
        icon_fg = resolver.to_int('active_tab_foreground')
    else:
        icon_bg = resolver.to_int('inactive_tab_background')
        icon_fg = resolver.to_int('inactive_tab_foreground')

    return TabContent(
        icon=icon,
        icon_fg=icon_fg,
        icon_bg=icon_bg,
    )


# ---------------------------------------------------------------------------
# Content-kind renderers
# ---------------------------------------------------------------------------
# Each renderer returns a tuple of (text, color_int) parts, or None.
# Zone dispatch owns icon resolution, mode-color shift, SSH override,
# chrome overhead, composition, and foreground-process resolution: proc is
# the (exe, cwd, hostname) tuple resolved once per zone.


def _render_cwd(
    zone_cfg: ZoneSpec,
    active_tab: TabBarData,
    proc: tuple[str, str, str | None],
    text_budget: int,
    resolver: ColorResolver,
    opts,
) -> Parts | None:
    """Abbreviated working directory."""
    _exe, cwd, _hostname = proc
    if not cwd:
        return None
    cfg = get_config()
    cwd_text = abbreviate_path(cwd, text_budget, _HOME, cfg.ellipsis)
    if not cwd_text:
        return None
    return ((cwd_text, resolver.to_int(opts.tab_bar_git_directory_color)),)


def _render_git(
    zone_cfg: ZoneSpec,
    active_tab: TabBarData,
    proc: tuple[str, str, str | None],
    text_budget: int,
    resolver: ColorResolver,
    opts,
) -> Parts | None:
    """Git branch + status indicators. Skipped for remote sessions."""
    _exe, cwd, hostname = proc
    if hostname or not cwd:
        return None
    git_data = gitstatus.get_git_status(cwd)
    if not git_data:
        return None
    branch, counts = git_data
    full = _format_git_parts(branch, counts, False, resolver, opts)
    full_len = sum(display_width(t) for t, _ in full)
    if full_len <= text_budget:
        return tuple(full)
    branch_only = _format_git_parts(branch, counts, True, resolver, opts)
    branch_len = sum(display_width(t) for t, _ in branch_only)
    if branch_len <= text_budget:
        return tuple(branch_only)
    return None


def _render_cwd_git(
    zone_cfg: ZoneSpec,
    active_tab: TabBarData,
    proc: tuple[str, str, str | None],
    text_budget: int,
    resolver: ColorResolver,
    opts,
) -> Parts | None:
    """Compound cwd + git renderer.

    Progressive collapse on tight budgets:
        cwd + full_git  ->  full_git only  ->  branch_only  ->  empty
    """
    cfg = get_config()
    _exe, cwd, hostname = proc

    git_data = None
    if cwd and not hostname:
        git_data = gitstatus.get_git_status(cwd)

    if git_data:
        branch, counts = git_data
        full = _format_git_parts(branch, counts, False, resolver, opts)
        branch_only = _format_git_parts(branch, counts, True, resolver, opts)
        full_len = sum(display_width(t) for t, _ in full)
        branch_len = sum(display_width(t) for t, _ in branch_only)

        cwd_text = abbreviate_path(cwd, text_budget - full_len - 1, _HOME, cfg.ellipsis)
        if cwd_text and display_width(cwd_text) + 1 + full_len <= text_budget:
            parts: list[tuple[str, int]] = [
                (cwd_text + ' ', resolver.to_int(opts.tab_bar_git_directory_color))
            ]
            parts.extend(full)
            return tuple(parts)
        if full_len <= text_budget:
            return tuple(full)
        if branch_len <= text_budget:
            return tuple(branch_only)
        return None

    cwd_text = abbreviate_path(cwd, text_budget, _HOME, cfg.ellipsis) if cwd else None
    if cwd_text:
        return ((cwd_text, resolver.to_int(opts.tab_bar_git_directory_color)),)
    return None


def _render_text_parts(
    zone_cfg: ZoneSpec,
    text: str,
    text_budget: int,
    resolver: ColorResolver,
    opts,
) -> Parts | None:
    """Format a single text string as the zone's text part.

    Returns None for empty input or when text_budget is below the zone's
    min_text_budget. Truncates overflow with the configured ellipsis.
    """
    cfg = get_config()
    if not text or text_budget < zone_cfg.min_text_budget:
        return None
    if display_width(text) > text_budget:
        text = truncate_text(text, text_budget, cfg.ellipsis)
    text_fg = opts.tab_bar_zone_text_fg if opts.tab_bar_zone_text_fg is not None else opts.foreground
    return ((text, resolver.to_int(text_fg)),)


def _render_title(
    zone_cfg: ZoneSpec,
    active_tab: TabBarData,
    proc: tuple[str, str, str | None],
    text_budget: int,
    resolver: ColorResolver,
    opts,
) -> Parts | None:
    """Active tab title with sticky-cache fallback."""
    cfg = get_config()
    title = resolve_title(active_tab, cfg.sticky_last_cmd)
    return _render_text_parts(zone_cfg, title, text_budget, resolver, opts)


def _render_tab_label(
    zone_cfg: ZoneSpec,
    active_tab: TabBarData,
    proc: tuple[str, str, str | None],
    text_budget: int,
    resolver: ColorResolver,
    opts,
) -> Parts | None:
    """User-set tab name (Tab.name, set by set_tab_title)."""
    return _render_text_parts(
        zone_cfg, active_tab.tab_name or '', text_budget, resolver, opts
    )


_RENDERERS = {
    'cwd': _render_cwd,
    'git': _render_git,
    'cwd_git': _render_cwd_git,
    'title': _render_title,
    'tab_label': _render_tab_label,
}


# ---------------------------------------------------------------------------
# Zone dispatch
# ---------------------------------------------------------------------------

def _dispatch_zone_content(
    zone_cfg: ZoneSpec,
    active_tab: TabBarData,
    draw_data: DrawData,
    max_width: int,
) -> ZoneContent | None:
    """Render zone content from configured kinds.

    Resolves the zone icon (with SSH/mode override) and its color once,
    then walks zone_cfg.content in order, allocating remaining text budget
    per kind. Renderers return parts only; this function composes them
    with cfg.content_separator.

    Always-visible zone: when the zone is configured but every renderer
    returns None, emit a zero-width text segment so the engine still
    draws the icon.
    """
    if not zone_cfg.content:
        return None

    cfg = get_config()
    opts = get_options()
    resolver = ColorResolver.from_draw_data(draw_data)
    mode = get_keyboard_mode()

    proc = get_foreground_process(active_tab.tab_id)
    _exe, _cwd, hostname = proc

    mode_active = bool(mode) and cfg.mode_indicator

    if mode_active and zone_cfg.show_mode_indicator:
        icon = cfg.mode_names.get(mode, mode.upper())
    elif hostname and zone_cfg.ssh_icon:
        icon = zone_cfg.ssh_icon
    else:
        icon = zone_cfg.icon
    icon = pad_pua_icon(icon)

    # Zones are flat: the icon is a colored glyph on the bar background.
    # The mode indicator recolors it via tab_bar_mode_bg.
    if mode_active and opts.tab_bar_mode_bg is not None:
        icon_color = resolver.to_int(opts.tab_bar_mode_bg)
    else:
        icon_color = resolver.to_int('active_tab_background')

    text_fg_raw = opts.tab_bar_zone_text_fg if opts.tab_bar_zone_text_fg is not None else opts.foreground
    text_fg = resolver.to_int(text_fg_raw)

    # Fixed zone overhead: the icon plus one pad cell before the content
    # (nothing when the zone has no icon).
    overhead = display_width(icon) + 1 if icon else 0
    text_budget = max_width - overhead
    if text_budget < zone_cfg.min_text_budget:
        return None

    sep = cfg.content_separator
    sep_width = display_width(sep)

    merged_parts: list[tuple[str, int]] = []
    used_width = 0

    for kind in zone_cfg.content:
        renderer = _RENDERERS.get(kind)
        if renderer is None:
            continue
        remaining = text_budget - used_width
        if merged_parts:
            remaining -= sep_width
        if remaining <= 0:
            break
        kind_parts = renderer(zone_cfg, active_tab, proc, remaining, resolver, opts)
        if not kind_parts:
            continue
        kind_width = sum(display_width(t) for t, _ in kind_parts)
        if kind_width == 0:
            continue
        if merged_parts:
            sep_color = merged_parts[-1][1]
            merged_parts.append((sep, sep_color))
            used_width += sep_width
        merged_parts.extend(kind_parts)
        used_width += kind_width

    if not merged_parts:
        merged_parts = [('', text_fg)]

    return ZoneContent(
        icon=icon,
        parts=tuple(merged_parts),
        icon_color=icon_color,
    )


# ---------------------------------------------------------------------------
# Public zone entry-points
# ---------------------------------------------------------------------------

def left_zone_content(
    active_tab: TabBarData,
    draw_data: DrawData,
    max_width: int,
) -> ZoneContent | None:
    """Render left zone content."""
    cfg = get_config()
    zone_cfg = ZoneSpec(
        content=cfg.zone_left,
        icon=cfg.left_icon,
        ssh_icon=cfg.left_ssh_icon,
        min_text_budget=cfg.left_min_text_budget,
        show_mode_indicator=cfg.left_mode_indicator,
    )
    return _dispatch_zone_content(zone_cfg, active_tab, draw_data, max_width)


def right_zone_content(
    active_tab: TabBarData,
    draw_data: DrawData,
    max_width: int,
) -> ZoneContent | None:
    """Render right zone content."""
    cfg = get_config()
    zone_cfg = ZoneSpec(
        content=cfg.zone_right,
        icon=cfg.right_icon,
        ssh_icon=cfg.right_ssh_icon,
        min_text_budget=cfg.right_min_text_budget,
        show_mode_indicator=False,
    )
    return _dispatch_zone_content(zone_cfg, active_tab, draw_data, max_width)


def get_engine_callables() -> tuple[Callable[..., TabContent], Callable[..., ZoneContent | None], Callable[..., ZoneContent | None]]:
    """Return (tab_content, left_zone_content, right_zone_content)."""
    return (tab_content, left_zone_content, right_zone_content)


# ---------------------------------------------------------------------------
# Git formatting
# ---------------------------------------------------------------------------

def _format_git_parts(
    branch: str,
    counts: dict[str, int],
    branch_only: bool,
    resolver: ColorResolver,
    opts,
) -> list[tuple[str, int]]:
    """Format git info into (text, color_int) pairs."""
    parts: list[tuple[str, int]] = []

    branch_icon_glyph = opts.tab_bar_git_branch_icon
    if branch_icon_glyph:
        parts.append(
            (pad_pua_icon(branch_icon_glyph) + ' ', resolver.to_int(opts.tab_bar_git_branch_icon_color))
        )
    parts.append((branch, resolver.to_int(opts.tab_bar_git_branch_color)))

    if branch_only:
        return parts

    status_parts: list[tuple[str, int]] = []
    git_status = opts.tab_bar_git_status
    for key in _GIT_STATUS_FIELDS:
        if counts.get(key, 0) <= 0:
            continue
        entry = git_status.get(key)
        if not entry:
            continue
        glyph, color = entry
        status_parts.append((f'{glyph}{counts[key]}', resolver.to_int(color)))

    if status_parts:
        sep_color = resolver.to_int(opts.tab_bar_git_branch_color)
        parts.append((' ', sep_color))
        for i, (text, color) in enumerate(status_parts):
            if i > 0:
                parts.append((' ', sep_color))
            parts.append((text, color))

    return parts
