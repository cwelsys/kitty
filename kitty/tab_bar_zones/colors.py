# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>
from __future__ import annotations
from kitty.fast_data_types import Color
from kitty.tab_bar import DrawData, as_rgb
from kitty.utils import color_as_int


class ColorResolver:
    """Resolve a color reference (kitty Color, theme sentinel string, or None)
    to an as_rgb int. The 5 sentinel strings follow the live theme via DrawData.
    """

    def __init__(self, active_fg: Color, active_bg: Color, inactive_fg: Color, inactive_bg: Color, default_bg: Color) -> None:
        self._theme = {
            'active_tab_foreground': as_rgb(color_as_int(active_fg)),
            'active_tab_background': as_rgb(color_as_int(active_bg)),
            'inactive_tab_foreground': as_rgb(color_as_int(inactive_fg)),
            'inactive_tab_background': as_rgb(color_as_int(inactive_bg)),
            'tab_bar_background': as_rgb(color_as_int(default_bg)),
        }

    @classmethod
    def from_draw_data(cls, dd: DrawData) -> 'ColorResolver':
        return cls(dd.active_fg, dd.active_bg, dd.inactive_fg, dd.inactive_bg, dd.default_bg)

    def to_int(self, color: 'Color | str | None') -> int:
        if isinstance(color, str):
            return self._theme.get(color, as_rgb(0xCCCCCC))
        if color is None:
            return as_rgb(0xCCCCCC)
        return as_rgb(color_as_int(color))
