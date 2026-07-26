# License: GPL v3 Copyright: 2018, Kovid Goyal <kovid at kovidgoyal.net>
from __future__ import annotations
from typing import NamedTuple
from kitty.fast_data_types import get_options

# Generated from tabbar.toml [icons.mapping] -- do not hand-edit glyphs.
DEFAULT_ICONS: dict[str, str] = {
    'Python': '\ue73c',
    'R': '\U000f07d4',
    'arr': '\U000f0a08',
    'ansible': '\uf5e7',
    'ant': '\ue760',
    'apache2': '\uf0ac',
    'apt': '\ue77d',
    'atom': '\ue764',
    'aws': '\uf270',
    'babel': '\ue70d',
    'bat': '\U000f0b5f',
    'bazel': '\ue63a',
    'beam': '\ue7b1',
    'brew': '\ueb29',
    'btm': '\ueba2',
    'btop': '\ueba2',
    'caffeinate': '\uf0f4',
    'cargo': '\U0001f980',
    'cfdisk': '\uf0a0',
    'clang': '\ue61e',
    'claude': '\uee0d',
    'chezmoi': '\ue617',
    'clion': '\ue7b5',
    'cmake': '\ue624',
    'code': '\ue796',
    'composer': '\ue783',
    'console': '\U000f07b7',
    'crontab': '\uf073',
    'csharp': '\ue7af',
    'curl': '\uf019',
    'dart': '\ue798',
    'deno': '\ueb52',
    'dnf': '\uf30a',
    'docker': '\uf308',
    'ducker': '\uf308',
    'doctl': '\uf481',
    'dotnet': '\ue77f',
    'dpkg': '\ue77d',
    'eclipse': '\ue7b0',
    'elixir': '\ue62d',
    'emacs': '\ue632',
    'fdisk': '\uf0a0',
    'firebase': '\ue787',
    'flutter': '\ue798',
    'gcc': '\ue61e',
    'gcloud': '\ue270',
    'gdb': '\uf188',
    'gh': '\ue709',
    'ghc': '\ue777',
    'ghostty': '\ueefe',
    'git': '\ue702',
    'gitlab': '\ue709',
    'gitui': '\ue702',
    'glances': '\ueba2',
    'go': '\ue627',
    'gpg': '\uf084',
    'gping': '\ue714',
    'gradle': '\ue7a9',
    'grunt': '\ue611',
    'gulp': '\ue610',
    'helm': '\U000f10fe',
    'heroku': '\ue749',
    'hg': '\ue727',
    'htop': '\ueba2',
    'httpd': '\uf0ac',
    'hx': '\U000f0524',
    'idea': '\ue7b5',
    'iterm2': '\uf120',
    'java': '\ue256',
    'jekyll': '\ue630',
    'jenkins': '\ue767',
    'jest': '\ue752',
    'jj': '\ue725',
    'julia': '\ue624',
    'just': '\ue795',
    'k9s': '\U000f10fe',
    'kitten': '\U000f011b',
    'kitty': '\U000f011b',
    'kmux': '\uebc8',
    'kubectl': '\U000f10fe',
    'kubie': '\U000f10fe',
    'laravel': '\ue73f',
    'lazydocker': '\uf308',
    'lazygit': '\ue702',
    'lazyjj': '\ue725',
    'lf': '\uf07c',
    'lfcd': '\uf07c',
    'lldb': '\uf188',
    'lvim': '\ue62b',
    'mactop': '\ueba2',
    'make': '\ue624',
    'maven': '\ue7b4',
    'minikube': '\U000f10fe',
    'mocha': '\ue79e',
    'mongo': '\ue7a4',
    'mpc': '\uf001',
    'mysql': '\ue704',
    'nala': '\ue77d',
    'nano': '\uf040',
    'netbeans': '\ue768',
    'ng': '\ue753',
    'nginx': '\uf0ac',
    'node': '\ued0d',
    'npm': '\U000f01f7',
    'nu': '\ue795',
    'nvim': '\ue6ae',
    'openssl': '\uf023',
    'pacman': '\U000f0baf',
    'pi': '\U000f0baf',
    'pu': '\U000f0baf',
    'parted': '\uf0a0',
    'paru': '\U000f0baf',
    'perl': '\ue769',
    'php': '\ue73d',
    'ping': '\ue714',
    'pip': '\ue73c',
    'pip3': '\ue73c',
    'powershell': '\uebc7',
    'psql': '\ue76e',
    'puppet': '\uf499',
    'pycharm': '\ue7b5',
    'python': '\ue73c',
    'python3': '\ue73c',
    'ranger': '\uf07c',
    'react': '\ue7ba',
    'redis': '\ue76d',
    'rmpc': '\U000f0f6f',
    'rsync': '\uf021',
    'ruby': '\ue23e',
    'rustc': '\ue7a8',
    'rustup': '\ue7a8',
    'scala': '\ue737',
    'scp': '\U000f1065',
    'screen': '\uebc8',
    'sqlite': '\uf1c0',
    'ssh': '\uf0ac',
    'stack': '\ue777',
    'sudo': '\uf132',
    'svn': '\ue725',
    'swift': '\ue755',
    'systemctl': '\uf085',
    'tcsh': '\ue795',
    'terraform': '\ufcbd',
    'tickrs': '\uebe2',
    'tig': '\ue702',
    'tmux': '\uebc8',
    'top': '\ueba2',
    'topgrade': '\U000f06b0',
    'travis': '\ue77e',
    'tsc': '\ue628',
    'unicorn': '\U000f15c3',
    'unzip': '\uf1c6',
    'vagrant': '\uf2b8',
    'valgrind': '\uf188',
    'vi': '\ue62b',
    'vim': '\ue62b',
    'virtualbox': '\ue72a',
    'visualstudio': '\ue70c',
    'vue': '\ufd42',
    'webpack': '\ue770',
    'wget': '\uf019',
    'y': '\U000f01e5',
    'yarn': '\ue718',
    'yay': '\U000f0baf',
    'yazi': '\U000f01e5',
    'yum': '\uf30a',
    'zig': '\u21af',
    'zip': '\uf1c6',
    'zsh': '\uf489',
    'weathr': '\U000f0591',
}
DEFAULT_ICON_FALLBACK = '\uf489'


class ZonesConfig(NamedTuple):
    zone_left: tuple[str, ...]
    zone_right: tuple[str, ...]
    left_mode_indicator: bool
    left_min_text_budget: int
    right_min_text_budget: int
    sticky_last_cmd: bool
    content_separator: str
    ellipsis: str
    pill_border_left: str
    pill_border_right: str
    pill_spacing: int
    icon_elements: tuple[str, ...]
    left_icon: str
    left_ssh_icon: str
    right_icon: str
    right_ssh_icon: str
    mode_indicator: bool
    mode_names: dict[str, str]
    icon_overrides: dict[str, str]
    icon_fallback: str

    def icon_for(self, exe: str) -> str:
        if exe in self.icon_overrides:
            return self.icon_overrides[exe]
        return DEFAULT_ICONS.get(exe, self.icon_fallback)

    def has_icon(self, exe: str) -> bool:
        return exe in self.icon_overrides or exe in DEFAULT_ICONS


_cache: 'tuple[int, ZonesConfig] | None' = None


def get_config() -> ZonesConfig:
    global _cache
    opts = get_options()
    key = id(opts)
    if _cache is not None and _cache[0] == key:
        return _cache[1]
    cfg = ZonesConfig(
        zone_left=opts.tab_bar_zone_left,
        zone_right=opts.tab_bar_zone_right,
        left_mode_indicator=opts.tab_bar_left_mode_indicator,
        left_min_text_budget=opts.tab_bar_left_min_text_budget,
        right_min_text_budget=opts.tab_bar_right_min_text_budget,
        sticky_last_cmd=opts.tab_bar_sticky_last_cmd,
        content_separator=opts.tab_bar_content_separator,
        ellipsis=opts.tab_bar_ellipsis,
        pill_border_left=opts.tab_bar_pill_border_left,
        pill_border_right=opts.tab_bar_pill_border_right,
        pill_spacing=opts.tab_bar_pill_spacing,
        icon_elements=opts.tab_bar_icon_elements,
        left_icon=opts.tab_bar_left_icon,
        left_ssh_icon=opts.tab_bar_left_ssh_icon,
        right_icon=opts.tab_bar_right_icon,
        right_ssh_icon=opts.tab_bar_right_ssh_icon,
        mode_indicator=opts.tab_bar_mode_indicator,
        mode_names=opts.tab_bar_mode_name,
        icon_overrides=opts.tab_bar_icon,
        icon_fallback=DEFAULT_ICON_FALLBACK,
    )
    _cache = (key, cfg)
    return cfg


def clear_caches() -> None:
    global _cache
    _cache = None
    from . import gitstatus
    gitstatus.clear_caches()
    from . import content
    content.clear_caches()
