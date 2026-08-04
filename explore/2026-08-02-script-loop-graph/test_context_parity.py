"""The API judge must be given exactly what the agent judge was told to read.

If these two drift, the fleet-vs-api comparison stops being a comparison and becomes a measurement
of who got more context. That is the confound Phase 2 already lost time to once.

    D:\\env\\nolan\\python.exe -X utf8 -m pytest explore/2026-08-02-script-loop-graph/ -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import context as ctx                                             # noqa: E402
import executors as ex                                            # noqa: E402
from nolan.scriptwriter.tasks import _REVIEW_INPUTS               # noqa: E402


def test_the_inline_bundle_covers_every_declared_review_input():
    """`_REVIEW_INPUTS` is what the brief tells an AGENT to open. An API call cannot open
    anything, so every one of those tokens must be resolvable to a real file here — otherwise the
    API judge silently works from less than the agent did and the comparison is rigged."""
    covered = {"brief", "facts", "beatmap", "citations", "factcheck", "style"} | {"draft"}
    missing = set(_REVIEW_INPUTS) - covered
    assert not missing, (f"context.py cannot resolve {missing} — the API executor would inline "
                         f"less than the brief tells the agent to read")


def test_style_is_one_of_the_inputs_that_must_be_inlined():
    """The reason this whole run exists. It is also the largest single input, so an executor
    quietly dropping it would look like a cost win and be a correctness loss."""
    assert "style" in _REVIEW_INPUTS


# --- JSON extraction: a model wraps its reply however it likes -------------------------------

@pytest.mark.parametrize("raw,want", [
    ('{"verdict": "better"}', "better"),
    ('```json\n{"verdict": "better"}\n```', "better"),
    ('```\n{"verdict": "better"}\n```', "better"),
    ('Sure! Here is the verdict:\n{"verdict": "better"}\nHope that helps.', "better"),
])
def test_extract_json_survives_the_usual_wrappers(raw, want):
    assert ex._extract_json(raw)["verdict"] == want


def test_extract_json_returns_none_rather_than_guessing():
    """A half-parsed object would become a verdict and be indistinguishable from a real one.
    Failing loudly is the contract — no silent rc-0-on-failure."""
    for raw in ("no json here at all", "", "{ this is not json }", "[1, 2, 3]"):
        assert ex._extract_json(raw) is None


def test_inline_bundle_reports_what_it_actually_sent(tmp_path):
    """A run must be able to say what context it sent, not what it meant to send."""
    sg = tmp_path / "p" / "scriptgen"
    (sg / "drafts").mkdir(parents=True)
    (sg / "facts.md").write_text("F" * 50, encoding="utf-8")
    (sg / "drafts" / "draft-01.md").write_text("A" * 40, encoding="utf-8")
    (sg / "drafts" / "draft-02.md").write_text("B" * 60, encoding="utf-8")

    class _Store:
        root = tmp_path
        def get(self, _slug):                                     # noqa: D102
            return {"style_id": "does-not-exist"}

    text, notes = ctx.inline_bundle("p", _Store())
    assert "FACTS" in text and "CURRENT DRAFT" in text and "PREVIOUS DRAFT" in text
    assert any(n.startswith("facts:") for n in notes)
    assert any("draft-02" in n for n in notes)
    # a style guide that does not exist is ABSENT, never silently empty
    assert not any(n.startswith("style:") for n in notes)
