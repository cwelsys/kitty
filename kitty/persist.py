#!/usr/bin/env python
# License: GPLv3 Copyright: 2026, Kovid Goyal <kovid at kovidgoyal.net>

import os
import re
import secrets
from collections.abc import Callable, Mapping, Sequence

MAX_SLUG_LEN = 24
FALLBACK_SLUG = 'shell'

_unsafe = re.compile(r'[^a-z0-9]+')


def slugify(cwd: str) -> str:
    ' Human-readable, filesystem-safe stem for a session name, from a cwd '
    base = os.path.basename(cwd.rstrip('/'))
    slug = _unsafe.sub('-', base.lower()).strip('-')
    if not slug:
        return FALLBACK_SLUG
    return slug[:MAX_SLUG_LEN].strip('-') or FALLBACK_SLUG


def make_session_name(cwd: str, rand: Callable[[], str] | None = None) -> str:
    '''
    Generate a unique zmx session name for a window launched in cwd.

    A random suffix is used rather than the lowest free integer because the
    latter requires a synchronous `zmx list` fork+exec on every window launch,
    and with persist_windows enabled that is every window. Auto-generated names
    are rarely typed by hand: workspace names are the ones humans type.
    '''
    suffix = rand() if rand is not None else secrets.token_hex(2)
    return f'{slugify(cwd)}-{suffix}'


def should_reap(user_vars: Mapping[str, str]) -> bool:
    '''
    Whether closing a window should kill its zmx session.

    Only sessions kitty generated a name for are reaped. A session named
    explicitly by the user via --persist-name is an explicit request to keep
    it, so it survives its window.
    '''
    if not user_vars.get('zmx_session'):
        return False
    return user_vars.get('zmx_owned') == '1'


def zmx_command(session_name: str, cmd: Sequence[str] | None) -> list[str]:
    ' The command that runs cmd (or a login shell) inside a zmx session '
    ans = ['zmx', 'attach', session_name]
    if cmd:
        ans.extend(cmd)
    return ans


def reap_command(session_name: str, zmx_exe: str = 'zmx') -> list[str]:
    '''
    The command that kills a zmx session, or [] if there is nothing to kill.

    zmx_exe must be an absolute path resolved by kitty's which(). Under
    LaunchServices kitty's own PATH is only /usr/bin:/bin:/usr/sbin:/sbin, so a
    bare 'zmx' fails to exec even on machines where which() finds it via
    /etc/paths or the login shell.
    '''
    if not session_name:
        return []
    return [zmx_exe, 'kill', session_name]
