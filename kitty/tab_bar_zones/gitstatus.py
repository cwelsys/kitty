# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>
from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path
from time import monotonic

CACHE_TTL = 2.0


def find_git_dir(cwd: str) -> Path | None:
    try:
        path = Path(cwd)
        for parent in [path, *path.parents]:
            git_path = parent / '.git'
            if git_path.is_dir():
                return git_path
            if git_path.is_file():
                content = git_path.read_text().strip()
                if content.startswith('gitdir:'):
                    result = Path(content[7:].strip())
                    if not result.is_absolute():
                        result = (parent / result).resolve()
                    return result
        return None
    except Exception:
        return None


def parse_git_output(raw: str) -> tuple[str, dict[str, int]]:
    branch = ''
    counts = {
        'ahead': 0,
        'behind': 0,
        'staged': 0,
        'modified': 0,
        'deleted': 0,
        'renamed': 0,
        'untracked': 0,
        'conflicted': 0,
        'stashed': 0,
    }
    for line in raw.splitlines():
        if line.startswith('# branch.head '):
            branch = line.split()[-1]
        elif line.startswith('# branch.ab '):
            parts = line.split()
            if len(parts) >= 4:
                counts['ahead'] = int(parts[2].lstrip('+'))
                counts['behind'] = abs(int(parts[3]))
        elif line.startswith('# stash '):
            counts['stashed'] = int(line.split()[-1])
        elif line.startswith('2 '):
            counts['renamed'] += 1
        elif line.startswith('1 '):
            parts = line.split()
            if len(parts) >= 2:
                xy = parts[1]
                if len(xy) >= 2:
                    if xy[0] == 'D':
                        counts['deleted'] += 1
                    elif xy[0] not in ('.', '?'):
                        counts['staged'] += 1
                    if xy[1] == 'D':
                        if xy[0] != 'D':
                            counts['deleted'] += 1
                    elif xy[1] not in ('.', '?'):
                        counts['modified'] += 1
        elif line.startswith('u '):
            counts['conflicted'] += 1
        elif line.startswith('? '):
            counts['untracked'] += 1
    return branch, counts


@lru_cache(maxsize=64)
def _git_status(cwd: str, ttl_bucket: int) -> tuple[str, dict[str, int]] | None:
    del ttl_bucket
    if not find_git_dir(cwd):
        return None
    try:
        result = subprocess.run(
            ['git', '-C', cwd, 'status', '--porcelain=v2', '--branch', '--show-stash'],
            capture_output=True,
            text=True,
            timeout=0.5,
        )
        if result.returncode != 0:
            return None
        branch, counts = parse_git_output(result.stdout)
        return (branch, counts) if branch else None
    except Exception:
        return None


def get_git_status(cwd: str) -> tuple[str, dict[str, int]] | None:
    return _git_status(cwd, int(monotonic() // CACHE_TTL))


def clear_caches() -> None:
    _git_status.cache_clear()
