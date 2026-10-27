"""Spec tests for the Track A home body (compliance, not learning evidence). TRACK_A_DESIGN.md §4.1."""
import hashlib
from pathlib import Path

import pytest

from atanor_os.agent.concepts import atoms
from atanor_os.world.home_world import HomeWorkspace, head_of, loc_of
from atanor_os.world.raw_obs import names_of, raw_attrs, to_human

RECEIPT = '영수증\n가게: 동네마트\n합계: 7,800원\n'.encode('utf-8')
MEMO = '메모\n다음 주에 친구 생일 선물 사기\n'.encode('utf-8')


def _home(tmp_path):
    ws = HomeWorkspace(tmp_path / 'w')
    (ws.root / 'inbox' / 'files').mkdir(parents=True)
    (ws.root / 'inbox' / 'files' / 'a.txt').write_bytes(RECEIPT)
    (ws.root / 'inbox' / 'files' / 'b.txt').write_bytes(MEMO)
    return ws


def test_receipt_and_memo_differ_in_atoms(tmp_path):
    """The counter-example of the design (§0.3): on the file body a receipt and a memo had the same atoms."""
    ws = _home(tmp_path)
    st = ws.observe(ws.existing())
    a = {x for x in atoms('home', st, ('inbox/files/a.txt',)) if x[0] == 'U'}
    b = {x for x in atoms('home', st, ('inbox/files/b.txt',)) if x[0] == 'U'}
    assert a != b
    assert ('U', 0, 'a4', '영수증') in a and ('U', 0, 'a4', '메모') in b
    assert ('U', 0, 'a5', 'files') in a and ('U', 0, 'a5', 'files') in b


def test_head_and_loc_values(tmp_path):
    assert head_of(RECEIPT) == '영수증' and head_of(b'') == '-' and head_of(b'   \nx') == '-'
    assert head_of(('x' * 40).encode()) == 'x' * 24
    assert loc_of('inbox/files/a.txt') == 'files' and loc_of('a.txt') == '-' and loc_of('receipts/a.txt') == 'receipts'
    ws = _home(tmp_path)
    st = ws.observe(['receipts/a.txt'])
    assert st['receipts/a.txt'] == {'kind': 'absent', 'ext': 'txt', 'hash': '-', 'parent_kind': 'absent', 'head': '-', 'loc': 'receipts'}
    assert st['inbox']['head'] == '-' and st['inbox']['loc'] == '-'


def test_move_carries_head_and_keeps_loc(tmp_path):
    ws = _home(tmp_path)
    before = ws.observe(['receipts', 'receipts/a.txt'])
    assert ws.execute('mkdir', ('receipts',), {})['ok'] is True
    assert ws.execute('move', ('inbox/files/a.txt', 'receipts/a.txt'), {})['ok'] is True
    after = ws.observe(['inbox/files/a.txt', 'receipts/a.txt'])
    assert after['receipts/a.txt']['head'] == before['inbox/files/a.txt']['head'] == '영수증'
    assert after['inbox/files/a.txt']['head'] == '-'
    for p in ('inbox/files/a.txt', 'receipts/a.txt'):
        assert after[p]['loc'] == before[p]['loc']
    assert ws.execute('move', ('inbox/files/b.txt', 'receipts/a.txt'), {})['ok'] is False      # no overwrite
    assert ws.execute('mkdir', ('x/y',), {})['ok'] is False                                     # parent missing


def test_no_delete_or_convert(tmp_path):
    ws = _home(tmp_path)
    assert set(ws.tools()) == {'mkdir', 'move', 'copy'} and ws.CAPABILITY == {}
    for tool, args in (('delete', ('inbox/files/a.txt',)), ('convert', ('inbox/files/a.txt', 'a.md'))):
        with pytest.raises(ValueError):
            ws.execute(tool, args, {'destroy': True})
    assert {t for t, _ in ws.actions(ws.universe([]))} == {'mkdir', 'move', 'copy'}


def test_lab_copy_keeps_head_and_lab_from_state_restores_it(tmp_path):
    ws = _home(tmp_path)
    lab = ws.lab_copy(tmp_path / 'lab', ['inbox/files/a.txt', 'receipts'])
    assert type(lab) is HomeWorkspace and lab.attrs('inbox/files/a.txt')['head'] == '영수증'
    st = ws.observe(ws.existing())
    lab2 = ws.lab_from_state(tmp_path / 'lab2', st)
    assert lab2.attrs('inbox/files/a.txt')['head'] == '영수증' and lab2.attrs('inbox/files/b.txt')['head'] == '메모'
    assert lab2.kind('inbox/files') == 'dir'


def test_raw_human_round_trip(tmp_path):
    ws = _home(tmp_path)
    st = ws.observe(ws.existing() + ['receipts/a.txt'])
    for p, o in st.items():
        assert to_human('home', raw_attrs('home', o), o) == o
    # a predicted arrival copies the head; loc stays the id's own
    moved = to_human('home', {**raw_attrs('home', st['receipts/a.txt']), 'a0': 1, 'a3': 'h', 'a4': '영수증'}, st['receipts/a.txt'])
    assert moved['kind'] == 'file' and moved['head'] == '영수증' and moved['loc'] == 'receipts'


def test_names_exclude_identity_and_kind(tmp_path):
    ws = _home(tmp_path)
    st = ws.observe(ws.existing())
    assert names_of('home', st['inbox/files/a.txt']) == frozenset({'txt', '영수증', 'files'})


def test_paths_are_contained(tmp_path):
    ws = _home(tmp_path)
    for bad in ('../x', '/abs', 'a\\b', 'C:x', 'a/../b'):
        with pytest.raises(ValueError):
            ws.path(bad)


def test_learner_core_unchanged():
    """Track A adds a body adapter only: the frozen core v24 (agent/life.py) is byte-identical to commit 71feaf5."""
    import subprocess
    root = Path(__file__).resolve().parents[2]
    blob = subprocess.run(['git', 'show', '71feaf5:atanor_os/agent/life.py'], cwd=root, capture_output=True, check=True).stdout
    now = (root / 'atanor_os' / 'agent' / 'life.py').read_bytes()
    assert hashlib.sha256(blob.replace(b'\r\n', b'\n')).hexdigest() == hashlib.sha256(now.replace(b'\r\n', b'\n')).hexdigest()
