#!/usr/bin/env python
# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>
# Zones tab bar style: three-zone layout with content provider.

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from ..fast_data_types import Screen, get_boss, wcswidth
from ..tab_bar import (
    CellRange,
    DrawData,
    TabBarData,
    TabExtent,
    as_rgb,
)
from ..utils import log_error
from .text import _ends_with_pua


class TabContent(NamedTuple):
    """Content for a single tab pill, returned by the content provider."""
    icon: str           # icon section text (e.g. "1 " or "")
    icon_fg: int        # as_rgb color ints
    icon_bg: int
    bold_icon: bool = True


class ZoneContent(NamedTuple):
    """Content for a left or right zone, returned by the content provider.

    Zones render flat: the icon is a colored glyph on the bar background,
    followed by the content parts. No pill chrome.
    """
    icon: str
    parts: tuple[tuple[str, int], ...]  # (text, fg_color_int) pairs
    icon_color: int


def _display_width(s: str) -> int:
    """Return display width of a string (handles double-width glyphs)."""
    w = wcswidth(s)
    return w if w >= 0 else len(s)


def _pill_pad(icon: str) -> int:
    """Pad cells to draw after the icon, before the closing border.

    A PUA glyph and the space after it shape into a single two-cell ligature
    with the glyph centred across *both* cells, so that space ends up filled by
    the right half of the glyph instead of separating it from the border. Such
    an icon needs a second pad cell to leave a real gap; anything else only
    needs the one.
    """
    return 2 if _ends_with_pua(icon) else 1


def _pill_width(icon: str, border_left: str, border_right: str) -> int:
    """Calculate drawn width of a tab pill: [border_left][icon+pad][border_right]."""
    return _display_width(border_left) + _display_width(icon) + _pill_pad(icon) + _display_width(border_right)


def _draw_pill(screen: Screen, content: TabContent, border_left: str, border_right: str) -> None:
    """Draw a single tab pill to screen at current cursor position.

    Structure: [border_left][icon ][border_right]
    Colors come from the TabContent. The engine never resolves colors.
    """
    # Left border (icon_bg on transparent)
    screen.cursor.bg = 0
    screen.cursor.fg = content.icon_bg
    screen.draw(border_left)

    # Icon section
    screen.cursor.bg = content.icon_bg
    screen.cursor.fg = content.icon_fg
    screen.cursor.bold = content.bold_icon
    screen.draw(content.icon + ' ' * _pill_pad(content.icon))
    screen.cursor.bold = False

    # Right border
    screen.cursor.bg = 0
    screen.cursor.fg = content.icon_bg
    screen.draw(border_right)


# Gap (in cells) between a zone and the center tab zone.
ZONE_GAP = 2
# Zones narrower than this are not drawn at all.
MIN_ZONE_WIDTH = 10
# Cells kept clear at the window edge so the corner rounding doesn't clip glyphs.
EDGE_PAD = 1


def _zone_cells(
    content: ZoneContent,
    mirrored: bool = False,
) -> list[tuple[int, int, bool, str]]:
    """Return a list of (bg, fg, bold, glyph) cells for a flat zone.

    Layouts:
        Standard:  [icon][' '][parts]
        Mirrored:  [parts][' '][icon]

    Everything sits on the bar background (bg 0); the icon is a bold
    colored glyph and parts keep their own fg colors. Parts stay LTR.
    An empty icon emits no cell and reserves no gap.
    """
    part_cells = [(0, fg, False, text) for text, fg in content.parts if text]
    if not content.icon:
        return part_cells
    icon_cell = (0, content.icon_color, True, content.icon)
    if not part_cells:
        return [icon_cell]
    sp = (0, content.icon_color, False, ' ')
    if mirrored:
        return [*part_cells, sp, icon_cell]
    return [icon_cell, sp, *part_cells]


def _draw_zone(
    screen: Screen,
    content: ZoneContent,
    mirrored: bool = False,
) -> None:
    """Draw a flat zone from the cell list returned by _zone_cells."""
    for bg, fg, bold, glyph in _zone_cells(content, mirrored):
        screen.cursor.bg = bg
        screen.cursor.fg = fg
        screen.cursor.bold = bold
        screen.draw(glyph)
    screen.cursor.bold = False


def _zone_width(content: ZoneContent, mirrored: bool = False) -> int:
    """Calculate drawn width of a flat zone: icon + pad + parts."""
    del mirrored  # widths match for both layouts
    icon_width = _display_width(content.icon)
    text_width = sum(_display_width(text) for text, _ in content.parts)
    if icon_width and text_width:
        return icon_width + 1 + text_width
    return icon_width + text_width


def draw_tab_with_zones(
    draw_data: DrawData,
    screen: Screen,
    tabs: Sequence[TabBarData],
) -> list[TabExtent]:
    """Draw all tabs using three-zone layout. Returns tab_extents for click detection.

    Called once per render cycle (not per tab). Owns all layout, positioning,
    and CellRange generation.

    Zones:
        Left:   CWD/git status (content from provider)
        Center: Tab pills (centered, uniform width)
        Right:  Provider content (right_zone_func, e.g. active title)

    Only center tabs are pills; the left/right zones render flat on the bar
    background with EDGE_PAD cells kept clear at the window edges.
    """
    if not tabs:
        return []

    from .content import get_engine_callables
    from .config import get_config
    tab_content_func, left_zone_func, right_zone_func = get_engine_callables()
    cfg = get_config()
    border_left = cfg.pill_border_left
    border_right = cfg.pill_border_right
    spacing = cfg.pill_spacing

    # Detect drag state
    is_drag = False
    try:
        boss = get_boss()
        tm = boss.active_tab_manager if boss else None
        is_drag = tm is not None and getattr(tm, 'tab_being_dropped', None) is not None
    except Exception:
        pass

    center_tabs: list[tuple[int, TabBarData]] = [
        (i + 1, tab) for i, tab in enumerate(tabs)
    ]

    center_contents: list[TabContent] = []
    for visual_idx, tab in center_tabs:
        try:
            content = tab_content_func(tab, visual_idx, tab.is_active, draw_data)
        except Exception as e:
            log_error(f'zones: tab_content failed: {e}')
            fg = as_rgb(draw_data.tab_fg(tab))
            bg = as_rgb(draw_data.tab_bg(tab))
            content = TabContent(icon=str(visual_idx), icon_fg=fg, icon_bg=bg)
        center_contents.append(content)

    # Pills are icon+index only so widths are uniform; switching tabs never
    # reflows the bar.
    center_widths = [
        _pill_width(c.icon, border_left, border_right)
        for c in center_contents
    ]

    n_center = len(center_tabs)
    center_spacing = (n_center - 1) * spacing if n_center > 1 else 0
    center_width = min(sum(center_widths) + center_spacing, screen.columns)

    center_start = max(0, (screen.columns - center_width) // 2)
    active_tab = next((t for t in tabs if t.is_active), tabs[0])

    # Draw left zone
    left_max = max(0, center_start - ZONE_GAP - EDGE_PAD)
    if left_zone_func and left_max > MIN_ZONE_WIDTH:
        try:
            left_content = left_zone_func(active_tab, draw_data, left_max)
        except Exception as e:
            log_error(f'zones: left_zone_content failed: {e}')
            left_content = None

        if left_content is not None:
            screen.cursor.x = EDGE_PAD
            _draw_zone(screen, left_content)

    # Draw center zone
    tab_extents: list[TabExtent] = []
    screen.cursor.x = center_start
    last_center_tab_id: int | None = center_tabs[-1][1].tab_id if center_tabs else None

    for i, (visual_idx, tab) in enumerate(center_tabs):
        if screen.cursor.x >= screen.columns:
            break

        if i > 0:
            screen.cursor.bg = 0
            screen.draw(' ' * spacing)

        content = center_contents[i]
        start = screen.cursor.x
        _draw_pill(screen, content, border_left, border_right)
        end = screen.cursor.x

        # CellRange for this tab
        if is_drag and tab.tab_id == last_center_tab_id:
            tab_extents.append(TabExtent(tab.tab_id, CellRange(start, screen.columns)))
        else:
            tab_extents.append(TabExtent(tab.tab_id, CellRange(start, end)))

    # Draw right zone (active-tab content from provider, e.g. title)
    center_end = center_start + center_width
    right_max = max(0, screen.columns - center_end - ZONE_GAP - EDGE_PAD)
    if right_zone_func and right_max > MIN_ZONE_WIDTH:
        try:
            right_content = right_zone_func(active_tab, draw_data, right_max)
        except Exception as e:
            log_error(f'zones: right_zone_content failed: {e}')
            right_content = None

        if right_content is not None:
            zone_w = min(_zone_width(right_content, mirrored=True), right_max)
            # Pin to the right edge when the zone fits; otherwise butt up
            # against the center zone with the standard gap.
            screen.cursor.x = max(center_end + ZONE_GAP, screen.columns - EDGE_PAD - zone_w)
            _draw_zone(screen, right_content, mirrored=True)

    return tab_extents
