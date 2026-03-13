#!/usr/bin/env python
# License: GPLv3 Copyright: 2020, Kovid Goyal <kovid at kovidgoyal.net>


from typing import TYPE_CHECKING

from .base import MATCH_TAB_OPTION, ArgsType, Boss, PayloadGetType, PayloadType, RCOptions, RemoteCommand, ResponseType, Window

if TYPE_CHECKING:
    from kitty.cli_stub import SetTabPinnedRCOptions as CLIOptions


class SetTabPinned(RemoteCommand):

    protocol_spec = __doc__ = '''
    unpin/bool: If true, unpin the tab rather than pin it
    match/str: Which tab to pin/unpin
    '''

    short_desc = 'Pin or unpin a tab'
    desc = (
        'Pin the specified tab. Pinned tabs are always shown last in the tab bar.'
        ' If you use the :option:`kitten @ set-tab-pinned --match` option the state will be'
        ' set for all matched tabs. By default, only the tab in which the command is run is affected.'
        ' Use :option:`kitten @ set-tab-pinned --unpin` to unpin instead.'
    )
    options_spec = MATCH_TAB_OPTION + '''\n
--unpin
type=bool-set
Unpin the tab instead of pinning it.
'''

    def message_to_kitty(self, global_opts: RCOptions, opts: 'CLIOptions', args: ArgsType) -> PayloadType:
        return {'unpin': getattr(opts, 'unpin', False), 'match': opts.match}

    def response_from_kitty(self, boss: Boss, window: Window | None, payload_get: PayloadGetType) -> ResponseType:
        for tab in self.tabs_for_match_payload(boss, window, payload_get):
            if tab:
                tab.set_pinned(not payload_get('unpin'))
        return None


set_tab_pinned = SetTabPinned()
