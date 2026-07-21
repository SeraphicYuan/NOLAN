"""Block-choice GATE (Track 2 #1/#2) — author.py rejects a PROVABLY-wrong block ('empty comparison'): a
connection_board that is a flow not a web, spans with no overlap, a 1-value chart, a <2-slice pie, a <2-set
venn. The rules are the single source of truth in nolan.hyperframes.sync._selection_mismatch (same rules the
sync report + authoring advisory read). A genuine web / overlapping spans / 3-bar chart PASS; `data.block_ok`
overrides a deliberate exception. Guards the two exhibits: 'Ownership hides' (converging chains, not a web)
and 'Nothing new' (a 60-years-apart sequence, not coexisting spans)."""
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
sys.path.insert(0, str(BRIDGE))
import author  # noqa: E402


def _mismatch_errs(scene):
    spec = {"frames": [{"id": "f1", "dur": 8, "scenes": [{"id": "s1", "start": 0, "dur": 8, **scene}]}]}
    return [e for e in author.validate_spec(spec) if "BLOCK MISMATCH" in e]


def test_gate_rejects_connection_board_that_is_a_flow_not_a_web():
    # the 'Ownership hides' shape: two chains converging on one sink (Google→shell→land, Meta→shell→land)
    flow = {"type": "connection_board", "data": {
        "nodes": [{"id": n} for n in ("g", "js", "m", "sc", "land")],
        "links": [{"from": "g", "to": "js"}, {"from": "js", "to": "land"},
                  {"from": "m", "to": "sc"}, {"from": "sc", "to": "land"}]}}
    assert _mismatch_errs(flow), "a converging flow must be rejected as a connection_board (no undirected cycle)"
    # a GENUINE web (a mutual/back-reference cycle) passes
    web = {"type": "connection_board", "data": {
        "nodes": [{"id": n} for n in ("a", "b", "c")],
        "links": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}, {"from": "c", "to": "a"}]}}
    assert not _mismatch_errs(web)


def test_gate_rejects_nonoverlapping_spans():
    # the 'Nothing new' shape: dated events 60 years apart — a sequence, not coexisting periods
    seq = {"type": "spans", "data": {"range": [1960, 2027], "spans": [
        {"label": "Disney", "start": 1965, "end": 1967}, {"label": "OpenAI", "start": 2024, "end": 2026}]}}
    assert _mismatch_errs(seq)
    ovl = {"type": "spans", "data": {"range": [0, 20], "spans": [
        {"label": "A", "start": 0, "end": 12}, {"label": "B", "start": 8, "end": 20}]}}
    assert not _mismatch_errs(ovl)


def test_gate_rejects_singleton_chart_and_pie():
    assert _mismatch_errs({"type": "chart", "data": {"series": [{"label": "x", "value": 5}]}})
    assert not _mismatch_errs({"type": "chart", "data": {"series": [{"label": c, "value": 1} for c in "abc"]}})
    assert _mismatch_errs({"type": "pie", "data": {"segments": [{"label": "x", "value": 100}]}})


def test_block_ok_overrides_the_gate():
    seq = {"type": "spans", "data": {"block_ok": True, "range": [1960, 2027], "spans": [
        {"label": "Disney", "start": 1965, "end": 1967}, {"label": "OpenAI", "start": 2024, "end": 2026}]}}
    assert not _mismatch_errs(seq), "data.block_ok must let a deliberate exception through"
