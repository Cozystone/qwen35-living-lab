"""Track A home body: the file body of the Qwen life lab's home (TRACK_A_DESIGN.md §1.2), a body adapter only.

Same tools semantics as the filesystem body (fs_world.Workspace), with two observations added and two tools removed:
  head  the first whitespace-separated token of a file's first line (NFC, at most 24 characters; '-' for a dir or
        an absent path). It is what a glance at the top of a file shows; the content beyond it is not observed.
  loc   the last segment of the parent id ('-' at the top). Like ext it is computed from the id alone, exists or not,
        so no action changes it; it can only select objects, never be an effect.
Tools: mkdir, move, copy. delete/convert are not part of this body (the Qwen life agent cannot delete; the mind
grants every capability a body declares, so a tool that must not be used is simply absent). Nothing here is learned
and nothing here knows a task.
"""
from __future__ import annotations

import sys
import unicodedata

from .fs_world import Workspace, parent_of

TOOLS = {'mkdir': 1, 'move': 2, 'copy': 2}
ENV_VERSION = f'homeworld-1/py{sys.version_info.major}.{sys.version_info.minor}/{sys.platform}'
HEAD_BYTES = 256


def head_of(data: bytes) -> str:
    text = unicodedata.normalize('NFC', data[:HEAD_BYTES].decode('utf-8', errors='replace'))
    first = text.splitlines()[0] if text.splitlines() else ''
    tok = first.split()
    return tok[0][:24] if tok else '-'


def loc_of(path: str) -> str:
    par = parent_of(path)
    return par.rsplit('/', 1)[-1] if par else '-'


class HomeWorkspace(Workspace):
    BODY = 'home'
    TOOLS = TOOLS
    CAPABILITY = {}

    def __init__(self, root, create=True):
        super().__init__(root, create)
        self.env_version = ENV_VERSION

    def attrs(self, value):
        a = super().attrs(value)
        p = self.path(value)
        a['head'] = head_of(p.read_bytes()) if a['kind'] == 'file' else '-'
        a['loc'] = loc_of(value)
        return a

    def tools(self):
        return dict(TOOLS)

    def lab_from_state(self, root, state):
        """Rebuilt from an observed state; a file's placeholder content starts with its observed head, so a receipt
        stays a receipt in the re-verification lab (contents beyond the head were never observed)."""
        lab = super().lab_from_state(root, state)
        for path, a in state.items():
            if a.get('kind') == 'file':
                h = a.get('head')
                lab.path(path).write_bytes(((h if h not in (None, '-', 'unknown') else 'placeholder') + ' placeholder\n').encode('utf-8'))
        return lab
