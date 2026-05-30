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
from .text import abbreviate_path, truncate_text, display_width
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
                user_vars = tab.active_window.user_vars
                proc = user_vars.get('PROC')
                if proc and proc not in _SHELLS:
                    exe = proc
                remote_cwd = user_vars.get('REMOTE_CWD')
                if remote_cwd:
                    cwd = remote_cwd
                remote_host = user_vars.get('REMOTE_HOST') or None
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
        text=None,
        icon_fg=icon_fg,
        icon_bg=icon_bg,
        text_fg=0,
        text_bg=0,
    )


# ---------------------------------------------------------------------------
# Content-kind renderers
# ---------------------------------------------------------------------------
# Each renderer returns a tuple of (text, color_int) parts, or None.
# Zone dispatch owns icon resolution, mode-color shift, SSH override,
# chrome overhead, and composition.


def _render_cwd(
    zone_cfg: ZoneSpec,
    active_tab: TabBarData,
    text_budget: int,
    resolver: ColorResolver,
    opts,
) -> Parts | None:
    """Abbreviated working directory."""
    _exe, cwd, _hostname = get_foreground_process(active_tab.tab_id)
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
    text_budget: int,
    resolver: ColorResolver,
    opts,
) -> Parts | None:
    """Git branch + status indicators. Skipped for remote sessions."""
    _exe, cwd, hostname = get_foreground_process(active_tab.tab_id)
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
    text_budget: int,
    resolver: ColorResolver,
    opts,
) -> Parts | None:
    """Compound cwd + git renderer.

    Progressive collapse on tight budgets:
        cwd + full_git  ->  full_git only  ->  branch_only  ->  empty
    """
    cfg = get_config()
    _exe, cwd, hostname = get_foreground_process(active_tab.tab_id)

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

    Resolves zone-level chrome once (icon with SSH/mode override, icon
    colors, text background), then walks zone_cfg.content in order,
    allocating remaining text budget per kind. Renderers return parts
    only; this function composes them with cfg.content_separator.

    Always-visible empty pill: when the zone is configured but every
    renderer returns None, emit a zero-width text segment so the engine
    still draws the pill chrome.
    """
    if not zone_cfg.content:
        return None

    cfg = get_config()
    opts = get_options()
    resolver = ColorResolver.from_draw_data(draw_data)
    mode = get_keyboard_mode()

    _exe, _cwd, hostname = get_foreground_process(active_tab.tab_id)

    mode_active = bool(mode) and cfg.mode_indicator

    if mode_active and zone_cfg.show_mode_indicator:
        icon = cfg.mode_names.get(mode, mode.upper())
    elif hostname and zone_cfg.ssh_icon:
        icon = zone_cfg.ssh_icon
    else:
        icon = zone_cfg.icon

    if mode_active:
        raw_mode_bg = opts.tab_bar_mode_bg if opts.tab_bar_mode_bg is not None else 'active_tab_background'
        raw_mode_fg = opts.tab_bar_mode_fg if opts.tab_bar_mode_fg is not None else 'active_tab_foreground'
        icon_bg = resolver.to_int(raw_mode_bg)
        icon_fg = resolver.to_int(raw_mode_fg)
    else:
        icon_bg = resolver.to_int('active_tab_background')
        icon_fg = resolver.to_int('active_tab_foreground')

    text_bg_raw = opts.tab_bar_zone_text_bg if opts.tab_bar_zone_text_bg is not None else 'inactive_tab_background'
    text_bg = resolver.to_int(text_bg_raw)
    text_fg_raw = opts.tab_bar_zone_text_fg if opts.tab_bar_zone_text_fg is not None else opts.foreground
    text_fg = resolver.to_int(text_fg_raw)

    # Fixed zone overhead: BL + icon-pad + SEP + text-pad + BR = 5 cells (plus icon width).
    overhead = display_width(icon) + 5
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
        kind_parts = renderer(zone_cfg, active_tab, remaining, resolver, opts)
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
        icon_fg=icon_fg,
        icon_bg=icon_bg,
        text_bg=text_bg,
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
            (branch_icon_glyph + ' ', resolver.to_int(opts.tab_bar_git_branch_icon_color))
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
