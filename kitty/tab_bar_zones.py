#!/usr/bin/env python
# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>
# Zones tab bar style — three-zone layout with content provider

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from .fast_data_types import Screen, get_boss, wcswidth
from .tab_bar import (
    CellRange,
    DrawData,
    TabBarData,
    TabExtent,
    as_rgb,
)


class TabContent(NamedTuple):
    """Content for a single tab pill, returned by the content provider."""
    icon: str           # icon section text (e.g. "1 " or "")
    text: str | None    # text section (None = collapsed/icon-only)
    icon_fg: int        # as_rgb color ints
    icon_bg: int
    text_fg: int
    text_bg: int
    bold_icon: bool = True


class ZoneContent(NamedTuple):
    """Content for the left zone, returned by the content provider."""
    icon: str
    parts: tuple[tuple[str, int], ...]  # (text, fg_color_int) pairs
    icon_fg: int
    icon_bg: int
    text_bg: int


def _display_width(s: str) -> int:
    """Return display width of a string (handles double-width glyphs)."""
    w = wcswidth(s)
    return w if w >= 0 else len(s)


def _pill_width(icon: str, text: str | None, border_left: str, border_right: str, separator: str) -> int:
    """Calculate drawn width of a pill.

    Structure: [border_left][icon ][separator][ text][border_right]
    """
    width = _display_width(border_left) + _display_width(icon) + 1 + _display_width(border_right)  # border + icon + pad + border
    if text:
        width += _display_width(separator) + 1 + _display_width(text)  # sep + pad + text
    return width


def _draw_pill(screen: Screen, content: TabContent, border_left: str, border_right: str, separator: str) -> None:
    """Draw a single pill to screen at current cursor position.

    Structure: [border_left][icon ][separator][ text][border_right]
    Colors come from the TabContent — the engine never resolves colors.
    """
    # Left border (icon_bg on transparent)
    screen.cursor.bg = 0
    screen.cursor.fg = content.icon_bg
    screen.draw(border_left)

    # Icon section
    screen.cursor.bg = content.icon_bg
    screen.cursor.fg = content.icon_fg
    screen.cursor.bold = content.bold_icon
    screen.draw(content.icon + ' ')
    screen.cursor.bold = False

    if content.text:
        # Separator (transition from icon_bg to text_bg)
        screen.cursor.bg = content.text_bg
        screen.cursor.fg = content.icon_bg
        screen.draw(separator)

        # Text section
        screen.cursor.fg = content.text_fg
        screen.draw(' ' + content.text)

        # Right border
        screen.cursor.fg = content.text_bg
        screen.cursor.bg = 0
        screen.draw(border_right)
    else:
        # No text — close directly after icon
        screen.cursor.bg = 0
        screen.cursor.fg = content.icon_bg
        screen.draw(border_right)


def _draw_zone_pill(
    screen: Screen,
    content: ZoneContent,
    border_left: str,
    border_right: str,
    separator: str,
) -> None:
    """Draw the left zone pill with colorized text segments.

    Like _draw_pill but text is a list of (text, fg_color) pairs for
    per-segment coloring (e.g., git branch in magenta, status counts in yellow).
    """
    # Left border
    screen.cursor.bg = 0
    screen.cursor.fg = content.icon_bg
    screen.draw(border_left)

    # Icon section
    screen.cursor.bg = content.icon_bg
    screen.cursor.fg = content.icon_fg
    screen.cursor.bold = True
    screen.draw(content.icon + ' ')
    screen.cursor.bold = False

    if content.parts:
        # Separator
        screen.cursor.bg = content.text_bg
        screen.cursor.fg = content.icon_bg
        screen.draw(separator)

        # Draw each part with its own color
        screen.draw(' ')
        for text, fg in content.parts:
            screen.cursor.fg = fg
            screen.draw(text)

        # Right border
        screen.cursor.fg = content.text_bg
        screen.cursor.bg = 0
        screen.draw(border_right)
    else:
        # No text — icon only
        screen.cursor.bg = 0
        screen.cursor.fg = content.icon_bg
        screen.draw(border_right)


def _zone_pill_width(content: ZoneContent, border_left: str, border_right: str, separator: str) -> int:
    """Calculate drawn width of a zone pill."""
    width = _display_width(border_left) + _display_width(content.icon) + 1 + _display_width(border_right)
    if content.parts:
        text_width = sum(_display_width(text) for text, _ in content.parts)
        width += _display_width(separator) + 1 + text_width
    return width


# Content provider loader and layout engine

import os
import runpy

from .constants import config_dir
from .types import run_once
from .utils import log_error


@run_once
def _load_content_provider() -> dict:
    """Load content provider functions from config dir tab_bar.py."""
    import traceback
    try:
        return runpy.run_path(os.path.join(config_dir, 'tab_bar.py'))
    except FileNotFoundError:
        return {}
    except Exception as e:
        traceback.print_exc()
        log_error(f'Failed to load zones content provider: {e}')
        return {}


def _get_tab_content_func():
    """Get tab_content function from content provider, or None."""
    return _load_content_provider().get('tab_content')


def _get_left_zone_content_func():
    """Get left_zone_content function from content provider, or None."""
    return _load_content_provider().get('left_zone_content')


def _get_pill_glyphs() -> tuple[str, str, str, int]:
    """Get pill glyphs from content provider, with defaults.

    Returns: (border_left, border_right, separator, spacing)
    """
    m = _load_content_provider()
    return (
        m.get('PILL_BORDER_LEFT', '\ue0b6'),
        m.get('PILL_BORDER_RIGHT', '\ue0b4'),
        m.get('PILL_SEPARATOR', '\ue0b0'),
        m.get('PILL_SPACING', 1),
    )


def _default_tab_content(tab: TabBarData, index: int, draw_data: DrawData) -> TabContent:
    """Fallback content when no content provider is loaded."""
    fg = as_rgb(draw_data.tab_fg(tab))
    bg = as_rgb(draw_data.tab_bg(tab))
    return TabContent(
        icon=str(index) if index > 0 else tab.title[:3],
        text=tab.title[:20] if tab.title else None,
        icon_fg=fg,
        icon_bg=bg,
        text_fg=fg,
        text_bg=bg,
    )


def draw_tab_with_zones(
    draw_data: DrawData,
    screen: Screen,
    tabs: Sequence[TabBarData],
) -> list[TabExtent]:
    """Draw all tabs using three-zone layout. Returns tab_extents for click detection.

    Called once per render cycle (not per tab). Owns all layout, positioning,
    and CellRange generation.

    Zones:
        Left:   CWD/git status pill (content from provider)
        Center: Tab pills (centered, responsive strategy)
        Right:  Pinned tab pills (right-aligned)
    """
    if not tabs:
        return []

    border_left, border_right, separator, spacing = _get_pill_glyphs()
    tab_content_func = _get_tab_content_func()
    left_zone_func = _get_left_zone_content_func()

    # Detect drag state
    is_drag = False
    try:
        boss = get_boss()
        tm = boss.active_tab_manager if boss else None
        is_drag = tm is not None and getattr(tm, 'tab_being_dropped', None) is not None
    except Exception:
        pass

    # Split into center (non-pinned) and right (pinned) tabs
    center_tabs: list[tuple[int, TabBarData]] = []  # (visual_index, tab)
    right_tabs: list[TabBarData] = []
    for tab in tabs:
        if tab.pinned:
            right_tabs.append(tab)
        else:
            center_tabs.append((len(center_tabs) + 1, tab))  # 1-based visual index

    # Get content for each tab
    center_contents: list[tuple[TabContent, TabContent]] = []  # (expanded, collapsed)
    right_contents: list[TabContent] = []

    for visual_idx, tab in center_tabs:
        if tab_content_func:
            try:
                expanded = tab_content_func(tab, visual_idx, tab.is_active, False, draw_data)
                collapsed = expanded._replace(text=None)
            except Exception as e:
                log_error(f'zones: tab_content failed: {e}')
                expanded = _default_tab_content(tab, visual_idx, draw_data)
                collapsed = expanded._replace(text=None)
        else:
            expanded = _default_tab_content(tab, visual_idx, draw_data)
            collapsed = expanded._replace(text=None)
        center_contents.append((expanded, collapsed))

    for tab in right_tabs:
        if tab_content_func:
            try:
                content = tab_content_func(tab, 0, tab.is_active, True, draw_data)
            except Exception as e:
                log_error(f'zones: tab_content failed for pinned: {e}')
                content = _default_tab_content(tab, 0, draw_data)
        else:
            content = _default_tab_content(tab, 0, draw_data)
        right_contents.append(content)

    # Compute widths
    center_expanded_widths = [
        _pill_width(exp.icon, exp.text, border_left, border_right, separator)
        for exp, _ in center_contents
    ]
    center_collapsed_widths = [
        _pill_width(col.icon, col.text, border_left, border_right, separator)
        for _, col in center_contents
    ]
    right_widths = [
        _pill_width(c.icon, c.text, border_left, border_right, separator)
        for c in right_contents
    ]

    n_center = len(center_tabs)
    n_right = len(right_tabs)
    center_spacing = (n_center - 1) * spacing if n_center > 1 else 0
    right_spacing = (n_right - 1) * spacing if n_right > 1 else 0
    right_total = sum(right_widths) + right_spacing
    right_margin = 2 if right_tabs else 0

    # Available space for center zone
    available = screen.columns - right_total - right_margin if right_tabs else screen.columns
    max_center = int(available * 0.6)

    # Find active tab in center
    center_active_idx: int | None = None
    for i, (_, tab) in enumerate(center_tabs):
        if tab.is_active:
            center_active_idx = i
            break

    # Strategy selection
    all_expanded = sum(center_expanded_widths) + center_spacing
    active_expanded = (
        sum(
            center_expanded_widths[i] if i == center_active_idx else center_collapsed_widths[i]
            for i in range(n_center)
        ) + center_spacing
    ) if center_tabs else 0
    all_collapsed = sum(center_collapsed_widths) + center_spacing

    if all_expanded <= max_center:
        strategy = 'expand_all'
        center_width = all_expanded
    elif active_expanded <= max_center:
        strategy = 'expand_active'
        center_width = active_expanded
    else:
        strategy = 'collapse_all'
        center_width = all_collapsed

    center_width = min(center_width, screen.columns)

    # Center position with clamping
    center_start = max(0, (screen.columns - center_width) // 2)
    if right_tabs:
        max_end = screen.columns - right_total - right_margin
        if center_start + center_width > max_end:
            center_start = max(0, max_end - center_width)

    # Draw left zone
    left_max = max(0, center_start - 2)
    if left_zone_func and left_max > 10:
        active_tab = tabs[0]
        for tab in tabs:
            if tab.is_active:
                active_tab = tab
                break
        try:
            left_content = left_zone_func(active_tab, draw_data, left_max)
        except Exception as e:
            log_error(f'zones: left_zone_content failed: {e}')
            left_content = None

        if left_content is not None:
            screen.cursor.x = 0
            _draw_zone_pill(screen, left_content, border_left, border_right, separator)

    # Draw center zone
    tab_extents: list[TabExtent] = []
    screen.cursor.x = center_start
    last_center_tab_id: int | None = center_tabs[-1][1].tab_id if center_tabs else None

    for i, (visual_idx, tab) in enumerate(center_tabs):
        if screen.cursor.x >= screen.columns:
            break

        # Spacing between pills
        if i > 0:
            screen.cursor.bg = 0
            screen.draw(' ' * spacing)

        # Select content based on strategy
        expanded, collapsed = center_contents[i]
        if strategy == 'expand_all':
            content = expanded
        elif strategy == 'expand_active' and tab.is_active:
            content = expanded
        else:
            content = collapsed

        start = screen.cursor.x
        _draw_pill(screen, content, border_left, border_right, separator)
        end = screen.cursor.x

        # CellRange for this tab
        if is_drag and tab.tab_id == last_center_tab_id:
            tab_extents.append(TabExtent(tab.tab_id, CellRange(start, screen.columns)))
        else:
            tab_extents.append(TabExtent(tab.tab_id, CellRange(start, end)))

    # Draw right zone (pinned tabs)
    if right_tabs:
        right_start = screen.columns - right_total
        screen.cursor.x = right_start

        for i, (tab, content) in enumerate(zip(right_tabs, right_contents)):
            if i > 0:
                screen.cursor.bg = 0
                screen.draw(' ' * spacing)

            start = screen.cursor.x
            _draw_pill(screen, content, border_left, border_right, separator)
            end = screen.cursor.x

            # During drag: pinned tabs get empty CellRanges (not targetable)
            if is_drag:
                tab_extents.append(TabExtent(tab.tab_id, CellRange(start, start)))
            else:
                tab_extents.append(TabExtent(tab.tab_id, CellRange(start, end)))

    return tab_extents
