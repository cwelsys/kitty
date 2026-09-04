#!/usr/bin/env python
# License: GPLv3 Copyright: 2026, Kovid Goyal <kovid at kovidgoyal.net>

import os
import re
import secrets
from collections.abc import Mapping

_unsafe = re.compile(r'[^a-z0-9]+')


def slugify(cwd: str) -> str:
    slug = _unsafe.sub('-', os.path.basename(cwd.rstrip('/')).lower()).strip('-')
    return slug[:24].strip('-') or 'shell'


def make_session_name(cwd: str) -> str:
    "Random suffix rather than lowest free integer: the latter needs a synchronous zmx list per window launch"
    return f'{slugify(cwd)}-{secrets.token_hex(2)}'


def should_reap(user_vars: Mapping[str, str]) -> bool:
    "Only sessions kitty named are killed with their window; a --persist-name session is a request to keep it"
    return bool(user_vars.get('zmx_session')) and user_vars.get('zmx_owned') == '1'


def parse_session_pid(output: str, session_name: str) -> int:
    "Root pid for session_name in `zmx list` output, or 0. The name is rechecked as --where is a prefix match"
    for line in output.splitlines():
        fields = dict(f.split('=', 1) for f in line.strip().split('\t') if '=' in f)
        if fields.get('name') == session_name:
            try:
                return int(fields['pid'])
            except (KeyError, ValueError):
                return 0
    return 0
