# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>
from __future__ import annotations

import subprocess
from pathlib import Path

_git_cache: dict[str, tuple[tuple[float, ...], tuple[str, dict[str, int]]]] = {}
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
                    if not result.is_absolute():  # submodules use a relative pointer
                        result = (parent / result).resolve()
                    _git_dir_cache[cwd] = result
                    return result
        # Don't cache a non-repo cwd: it's cheap to re-probe and caching None
        # would hide a later `git init` until the cache cap clears.
        return None
    except Exception:
        return None


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except Exception:
        return 0.0


def status_cache_key(git_dir: Path) -> tuple[float, ...]:
    """mtimes of every file whose change should invalidate cached git status.

    `git status --branch` reports HEAD and tracking-ref state, none of which is
    reflected in .git/index. So the key must also watch .git/HEAD (branch rename,
    detached-HEAD checkout), the current branch ref (fetch/push/reset moving it;
    packed-refs as the fallback when the loose ref is absent) and FETCH_HEAD
    (ahead/behind drift after a fetch).
    """
    index_mtime = _mtime(git_dir / "index")
    stash_mtime = _mtime(git_dir / "refs" / "stash")
    head_path = git_dir / "HEAD"
    head_mtime = _mtime(head_path)
    fetch_head_mtime = _mtime(git_dir / "FETCH_HEAD")

    branch_ref_mtime = 0.0
    try:
        head_content = head_path.read_text().strip()
    except Exception:
        head_content = ""
    if head_content.startswith("ref: "):
        loose = git_dir / head_content[5:].strip()
        if loose.exists():
            branch_ref_mtime = _mtime(loose)
        else:
            branch_ref_mtime = _mtime(git_dir / "packed-refs")
    return (index_mtime, stash_mtime, head_mtime, branch_ref_mtime, fetch_head_mtime)


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
                        if xy[0] != "D":  # don't double-count a fully-deleted file
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

    stash_ref = git_dir / "refs" / "stash"
    combined_mtime = status_cache_key(git_dir)
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
