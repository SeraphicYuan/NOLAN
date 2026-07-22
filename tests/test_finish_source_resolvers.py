"""Finish-DAG wiring guard for the two source resolvers (the 'defined-but-never-called' risk).

Both dataset and document binding are materialized as steps of the finish DAG, right after word-sync and
BEFORE the number-provenance gate + recompose. Each has thorough unit tests for the resolver itself
(test_data_source.py / test_document.py), but nothing pins the one line that makes the path reachable:
finish.py must actually CALL resolve_datasets(comp) and resolve_documents(comp). Delete either call and
every other test stays green while authored bindings silently stop resolving. This guards those calls.
"""
import re
from pathlib import Path

FINISH = Path(__file__).resolve().parents[1] / "src" / "nolan" / "hyperframes" / "finish.py"
SRC = FINISH.read_text(encoding="utf-8")


def test_resolve_datasets_is_called_in_finish():
    assert re.search(r"\bresolve_datasets\(comp\)", SRC), \
        "finish.py must call resolve_datasets(comp) — the dataset binding step of the DAG is unwired"


def test_resolve_documents_is_called_in_finish():
    assert re.search(r"\bresolve_documents\(comp\)", SRC), \
        "finish.py must call resolve_documents(comp) — the document binding step of the DAG is unwired"


def test_binding_runs_before_recompose():
    """Materialization must precede recompose (a bound scene needs its real data field before the block
    is composed to HTML). Assert both resolver calls appear before the recompose invocation in the file."""
    ds = SRC.index("resolve_datasets(comp)")
    doc = SRC.index("resolve_documents(comp)")
    recompose = re.search(r"recompose_frame\(comp", SRC)  # the actual recompose STEP call, not a doc mention
    assert recompose and ds < recompose.start() and doc < recompose.start(), \
        "dataset/document resolution must run before the recompose step in the finish DAG"
