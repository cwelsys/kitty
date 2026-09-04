"""Stateless text helpers for the tab-bar zones engine."""

from kitty.fast_data_types import wcswidth


def display_width(s: str) -> int:
    w = wcswidth(s)
    return w if w >= 0 else len(s)


def _ends_with_pua(s: str) -> bool:
    if not s:
        return False
    cp = ord(s[-1])
    return 0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD or 0x100000 <= cp <= 0x10FFFD


def pad_pua_icon(icon: str) -> str:
    """Pad PUA icons with a space: kitty renders glyph+space as one two-cell ligature."""
    if _ends_with_pua(icon):
        return icon + ' '
    return icon


def _take_width(text: str, budget: int) -> str:
    """Longest prefix of text whose display width is <= budget; PUA glyph + pad stay together."""
    out = []
    w = 0
    i = 0
    while i < len(text):
        chunk = text[i]
        if _ends_with_pua(chunk) and text[i + 1 : i + 2] == ' ':
            chunk = text[i : i + 2]
        cw = display_width(chunk)
        if w + cw > budget:
            break
        out.append(chunk)
        w += cw
        i += len(chunk)
    return ''.join(out)


def abbreviate_path(cwd: str, max_len: int, home: str, ellipsis: str) -> str | None:
    if not cwd:
        return None
    if len(cwd) > 1 and cwd.endswith('/'):
        cwd = cwd.rstrip('/')
    if cwd.startswith(home):
        remainder = cwd[len(home) :]
        if remainder == '' or remainder.startswith('/'):
            cwd = '~' + remainder
    if display_width(cwd) <= max_len:
        return cwd
    parts = cwd.split('/')
    if len(parts) <= 1:
        return cwd if display_width(cwd) <= max_len else None
    abbreviated = []
    for part in parts[:-1]:
        if part in ('~', ''):
            abbreviated.append(part)
        elif part.startswith('.'):
            abbreviated.append(part[:3] if len(part) > 3 else part)
        else:
            abbreviated.append(part[:2] if len(part) > 2 else part)
    abbreviated.append(parts[-1])
    result = '/'.join(abbreviated)
    if display_width(result) <= max_len:
        return result
    if display_width(parts[-1]) <= max_len:
        return parts[-1]
    if max_len > display_width(ellipsis):
        return _take_width(parts[-1], max_len - display_width(ellipsis)) + ellipsis
    return None


def truncate_text(text: str, budget: int, ellipsis: str) -> str:
    """Truncate text to fit budget cells (end-truncation only)."""
    if budget < 1:
        return ''
    ell_w = display_width(ellipsis)
    if budget <= ell_w:
        return _take_width(text, budget)
    if display_width(text) <= budget:
        return text
    return _take_width(text, budget - ell_w) + ellipsis
