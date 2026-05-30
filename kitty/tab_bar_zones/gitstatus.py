# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>
from __future__ import annotations

import subprocess
from pathlib import Path

_git_cache: dict[str, tuple[tuple[float, float], tuple[str, dict[str, int]]]] = {}
_GIT_CACHE_MAX = 50
_git_dir_cache: dict[str, Path | None] = {}
_GIT_DIR_CACHE_MAX = 100


def find_git_dir(cwd: str) -> Path | None:
    if cwd in _git_dir_cache:
        return _git_dir_cache[cwd]
    if len(_git_dir_cache) >= _GIT_DIR_CACHE_MAX:
        _git_dir_cache.clear()
    try:
        path = Path(cwd)
        for parent in [path, *path.parents]:
            git_path = parent / ".git"
            if git_path.is_dir():
                _git_dir_cache[cwd] = git_path
                return git_path
            if git_path.is_file():
                content = git_path.read_text().strip()
                if content.startswith("gitdir:"):
                    result = Path(content[7:].strip())
                    _git_dir_cache[cwd] = result
                    return result
        _git_dir_cache[cwd] = None
        return None
    except Exception:
        _git_dir_cache[cwd] = None
        return None


def parse_git_output(raw: str) -> tuple[str, dict[str, int]]:
    branch = ""
    counts = {
        "ahead": 0,
        "behind": 0,
        "staged": 0,
        "modified": 0,
        "deleted": 0,
        "renamed": 0,
        "untracked": 0,
        "conflicted": 0,
    }
    for line in raw.splitlines():
        if line.startswith("# branch.head "):
            branch = line.split()[-1]
        elif line.startswith("# branch.ab "):
            parts = line.split()
            if len(parts) >= 4:
                counts["ahead"] = int(parts[2].lstrip("+"))
                counts["behind"] = abs(int(parts[3]))
        elif line.startswith("2 "):
            counts["renamed"] += 1
        elif line.startswith("1 "):
            parts = line.split()
            if len(parts) >= 2:
                xy = parts[1]
                if len(xy) >= 2:
                    if xy[0] == "D":
                        counts["deleted"] += 1
                    elif xy[0] not in (".", "?"):
                        counts["staged"] += 1
                    if xy[1] == "D":
                        counts["deleted"] += 1
                    elif xy[1] not in (".", "?"):
                        counts["modified"] += 1
        elif line.startswith("u "):
            counts["conflicted"] += 1
        elif line.startswith("? "):
            counts["untracked"] += 1
    return branch, counts


def get_git_status(cwd: str) -> tuple[str, dict[str, int]] | None:
    git_dir = find_git_dir(cwd)
    if not git_dir:
        return None

    index = git_dir / "index"
    try:
        current_mtime = index.stat().st_mtime if index.exists() else 0
    except Exception:
        current_mtime = 0

    stash_ref = git_dir / "refs" / "stash"
    try:
        stash_mtime = stash_ref.stat().st_mtime if stash_ref.exists() else 0
    except Exception:
        stash_mtime = 0

    combined_mtime = (current_mtime, stash_mtime)
    repo_key = str(git_dir.parent) if git_dir.name == ".git" else str(git_dir)

    if repo_key in _git_cache:
        cached_mtime, cached_data = _git_cache[repo_key]
        if cached_mtime == combined_mtime:
            return cached_data

    try:
        result = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain=v2", "--branch"],
            capture_output=True,
            text=True,
            timeout=0.5,
        )
        if result.returncode != 0:
            return None

        branch, counts = parse_git_output(result.stdout)
        if not branch:
            return None

        if stash_ref.exists():
            try:
                stash_result = subprocess.run(
                    ["git", "-C", cwd, "stash", "list"],
                    capture_output=True,
                    text=True,
                    timeout=0.3,
                )
                if stash_result.returncode == 0:
                    stash_lines = stash_result.stdout.strip().splitlines()
                    counts["stashed"] = len(stash_lines)
            except Exception:
                pass

        if len(_git_cache) >= _GIT_CACHE_MAX:
            _git_cache.clear()
        _git_cache[repo_key] = (combined_mtime, (branch, counts))
        return (branch, counts)
    except Exception:
        return None


def clear_caches() -> None:
    _git_cache.clear()
    _git_dir_cache.clear()
