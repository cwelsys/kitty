#!/usr/bin/env python
# License: GPLv3 Copyright: 2026, Kovid Goyal <kovid at kovidgoyal.net>

import os
from contextlib import suppress
from functools import lru_cache

from .constants import shell_path
from .utils import resolved_shell

# Shells that may be used as an interactive nested shell. Basenames only.
_STATIC_SHELLS = frozenset({
    'bash', 'zsh', 'fish', 'sh', 'dash', 'ksh', 'mksh', 'tcsh', 'csh',
    'nu', 'elvish', 'xonsh', 'ash', 'pwsh',
})


@lru_cache(maxsize=4)
def known_shell_names(shells_file: str = '/etc/shells') -> frozenset[str]:
    names = set(_STATIC_SHELLS)
    with suppress(Exception):
        names.add(os.path.basename(resolved_shell()[0]))
    with suppress(Exception):
        names.add(os.path.basename(shell_path))
    try:
        with open(shells_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    names.add(os.path.basename(line))
    except OSError:
        pass
    return frozenset(names)


def is_shell_exe(path: str) -> bool:
    if not path:
        return False
    return os.path.basename(path) in known_shell_names()


def choose_cwd(
    *, reported: str, child_is_remote: bool, at_prompt: bool,
    foreground_is_nested_shell: bool, heuristic_cwd: str, mode: str,
) -> str:
    local_reported = bool(reported) and not child_is_remote
    if mode == 'last_reported':
        return reported if local_reported else heuristic_cwd
    if mode == 'prompt_gated':
        return reported if (local_reported and at_prompt) else heuristic_cwd
    # mode == 'current'
    if local_reported and not foreground_is_nested_shell:
        return reported
    return heuristic_cwd
