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
    """Content for a left or right zone pill, returned by the content provider."""
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
        # No text: close directly after the icon.
        screen.cursor.bg = 0
        screen.cursor.fg = content.icon_bg
        screen.draw(border_right)


# Powerline separator glyphs that flip direction; unknown separators pass through
_SEPARATOR_MIRROR = {
    '\ue0b0': '\ue0b2',  # solid right-pointing -> solid left-pointing
    '\ue0b1': '\ue0b3',  # outline right-pointing -> outline left-pointing
}


def _zone_pill_cells(
    content: ZoneContent,
    border_left: str,
    border_right: str,
    separator: str,
    mirrored: bool = False,
) -> list[tuple[int, int, bool, str]]:
    """Return a list of (bg, fg, bold, glyph) cells for a zone pill.

    Layouts:
        Standard:  [BL][icon][' '][SEP][' '][parts][BR]
        Mirrored:  [BL][parts][' '][SEP_M][' '][icon][BR]

    Mirrored is the literal cell-by-cell reverse of standard with BL/BR
    positions kept and SEP swapped via _SEPARATOR_MIRROR. Parts stay LTR.
    """
    icon_bg = content.icon_bg
    icon_fg = content.icon_fg
    text_bg = content.text_bg

    if not content.parts:
        return [
            (0, icon_bg, False, border_left),
            (icon_bg, icon_fg, True, content.icon),
            (icon_bg, icon_fg, True, ' '),
            (0, icon_bg, False, border_right),
        ]

    if mirrored:
        sep_glyph = _SEPARATOR_MIRROR.get(separator, separator)
        cells: list[tuple[int, int, bool, str]] = [
            (0, text_bg, False, border_left),
        ]
        for text, fg in content.parts:
            cells.append((text_bg, fg, False, text))
        cells.extend([
            (text_bg, icon_bg, False, ' '),                 # text-trail-sp
            (text_bg, icon_bg, False, sep_glyph),           # SEP_M
            (icon_bg, icon_fg, True, ' '),                  # icon-lead-sp
            (icon_bg, icon_fg, True, content.icon),         # icon
            (0, icon_bg, False, border_right),
        ])
        return cells

    cells = [
        (0, icon_bg, False, border_left),
        (icon_bg, icon_fg, True, content.icon + ' '),       # icon + icon-trail-sp
        (text_bg, icon_bg, False, separator),
        (text_bg, icon_bg, False, ' '),                     # text-lead-sp
    ]
    for text, fg in content.parts:
        cells.append((text_bg, fg, False, text))
    cells.append((0, text_bg, False, border_right))
    return cells


def _draw_zone_pill(
    screen: Screen,
    content: ZoneContent,
    border_left: str,
    border_right: str,
    separator: str,
    mirrored: bool = False,
) -> None:
    """Draw a zone pill from the cell list returned by _zone_pill_cells."""
    for bg, fg, bold, glyph in _zone_pill_cells(
        content, border_left, border_right, separator, mirrored
    ):
        screen.cursor.bg = bg
        screen.cursor.fg = fg
        screen.cursor.bold = bold
        screen.draw(glyph)


def _zone_pill_width(
    content: ZoneContent,
    border_left: str,
    border_right: str,
    separator: str,
    mirrored: bool = False,
) -> int:
    """Calculate drawn width of a zone pill.

    Both layouts produce the same cell count: BL + icon + 1 pad + BR,
    plus separator + 1 pad + parts when parts are present.
    """
    del mirrored  # widths match for both layouts
    width = _display_width(border_left) + _display_width(content.icon) + 1 + _display_width(border_right)
    if content.parts:
        text_width = sum(_display_width(text) for text, _ in content.parts)
        width += _display_width(separator) + 1 + text_width
    return width


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
        Center: Tab pills (centered, uniform width)
        Right:  Provider content pill (right_zone_func, e.g. active title)
    """
    if not tabs:
        return []

    from .content import get_engine_callables
    from .config import get_config
    tab_content_func, left_zone_func, right_zone_func = get_engine_callables()
    cfg = get_config()
    border_left = cfg.pill_border_left
    border_right = cfg.pill_border_right
    separator = cfg.pill_separator
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
            content = TabContent(icon=str(visual_idx), text=None, icon_fg=fg, icon_bg=bg, text_fg=0, text_bg=0)
        center_contents.append(content)

    # Pills are icon+index only (text=None) so widths are uniform; switching
    # tabs never reflows the bar.
    center_widths = [
        _pill_width(c.icon, c.text, border_left, border_right, separator)
        for c in center_contents
    ]

    n_center = len(center_tabs)
    center_spacing = (n_center - 1) * spacing if n_center > 1 else 0
    center_width = min(sum(center_widths) + center_spacing, screen.columns)

    center_start = max(0, (screen.columns - center_width) // 2)

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

        if i > 0:
            screen.cursor.bg = 0
            screen.draw(' ' * spacing)

        content = center_contents[i]
        start = screen.cursor.x
        _draw_pill(screen, content, border_left, border_right, separator)
        end = screen.cursor.x

        # CellRange for this tab
        if is_drag and tab.tab_id == last_center_tab_id:
            tab_extents.append(TabExtent(tab.tab_id, CellRange(start, screen.columns)))
        else:
            tab_extents.append(TabExtent(tab.tab_id, CellRange(start, end)))

    # Draw right zone (active-tab content from provider, e.g. title)
    center_end = center_start + center_width
    right_max = max(0, screen.columns - center_end - 2)
    if right_zone_func and right_max > 10:
        active_tab = tabs[0]
        for tab in tabs:
            if tab.is_active:
                active_tab = tab
                break
        try:
            right_content = right_zone_func(active_tab, draw_data, right_max)
        except Exception as e:
            log_error(f'zones: right_zone_content failed: {e}')
            right_content = None

        if right_content is not None:
            zone_w = _zone_pill_width(right_content, border_left, border_right, separator, mirrored=True)
            zone_w = min(zone_w, right_max)
            # Pin to the right edge when the pill fits; otherwise butt up against
            # the center zone with the standard 2-cell gap.
            screen.cursor.x = max(center_end + 2, screen.columns - zone_w)
            _draw_zone_pill(
                screen, right_content, border_left, border_right, separator,
                mirrored=True,
            )

    return tab_extents
