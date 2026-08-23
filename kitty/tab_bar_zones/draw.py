#!/usr/bin/env python
# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>

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
from .text import pad_pua_icon


class TabContent(NamedTuple):
    """Content for a single tab pill, returned by the content provider."""

    icon: str
    icon_fg: int
    icon_bg: int
    bold_icon: bool = True


class ZoneContent(NamedTuple):
    """Content for a left or right zone, returned by the content provider.

    Zones render flat: the icon is a colored glyph on the bar background,
    followed by the content parts. No pill chrome.
    """

    icon: str
    parts: tuple[tuple[str, int], ...]
    icon_color: int


def _display_width(s: str) -> int:
    """Return display width of a string (handles double-width glyphs)."""
    w = wcswidth(s)
    return w if w >= 0 else len(s)


PILL_BODY_CELLS = 4


def _pill_cells(
    content: TabContent,
    border_left: str,
    border_right: str,
) -> list[tuple[int, int, bool, str]]:
    """Return a list of (bg, fg, bold, text) cells for one tab pill.

    Layout: [cap_left][lead][icon + pad][trail][cap_right]

    The caps are glyphs coloured with the pill colour on the bar background;
    the body between them is a run of pill-coloured cells with the content
    centred on it. A PUA icon and the space after it are one two-cell ligature
    and are emitted as a single unit, so no caller can split the glyph from its
    pad. Content wider than the body grows the body rather than being clipped,
    which is what keeps `tab_bar_icon_elements index icon` legible.
    """
    icon = pad_pua_icon(content.icon)
    icon_width = _display_width(icon)
    body = max(PILL_BODY_CELLS, icon_width + 2)
    lead = (body - icon_width) // 2
    trail = body - icon_width - lead

    cells: list[tuple[int, int, bool, str]] = []
    if border_left:
        cells.append((0, content.icon_bg, False, border_left))
    if lead:
        cells.append((content.icon_bg, content.icon_fg, False, ' ' * lead))
    if icon:
        cells.append((content.icon_bg, content.icon_fg, content.bold_icon, icon))
    if trail:
        cells.append((content.icon_bg, content.icon_fg, False, ' ' * trail))
    if border_right:
        cells.append((0, content.icon_bg, False, border_right))
    return cells


def _pill_width(content: TabContent, border_left: str, border_right: str) -> int:
    """Calculate drawn width of a tab pill from the cells it will draw."""
    return sum(_display_width(text) for _, _, _, text in _pill_cells(content, border_left, border_right))


def _draw_pill(screen: Screen, content: TabContent, border_left: str, border_right: str) -> None:
    """Draw a single tab pill from the cell list returned by _pill_cells.

    Colors come from the TabContent. The engine never resolves colors.
    """
    for bg, fg, bold, text in _pill_cells(content, border_left, border_right):
        screen.cursor.bg = bg
        screen.cursor.fg = fg
        screen.cursor.bold = bold
        screen.draw(text)
    screen.cursor.bold = False


ZONE_GAP = 2
MIN_ZONE_WIDTH = 10
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
    del mirrored
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

    is_drag = False
    try:
        boss = get_boss()
        tm = boss.active_tab_manager if boss else None
        is_drag = tm is not None and getattr(tm, 'tab_being_dropped', None) is not None
    except Exception:
        pass

    center_tabs: list[tuple[int, TabBarData]] = [(i + 1, tab) for i, tab in enumerate(tabs)]

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

    center_widths = [_pill_width(c, border_left, border_right) for c in center_contents]

    n_center = len(center_tabs)
    center_spacing = (n_center - 1) * spacing if n_center > 1 else 0
    center_width = min(sum(center_widths) + center_spacing, screen.columns)

    center_start = max(0, (screen.columns - center_width) // 2)
    active_tab = next((t for t in tabs if t.is_active), tabs[0])

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

        if is_drag and tab.tab_id == last_center_tab_id:
            tab_extents.append(TabExtent(tab.tab_id, CellRange(start, screen.columns)))
        else:
            tab_extents.append(TabExtent(tab.tab_id, CellRange(start, end)))

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
            screen.cursor.x = max(center_end + ZONE_GAP, screen.columns - EDGE_PAD - zone_w)
            _draw_zone(screen, right_content, mirrored=True)

    return tab_extents
