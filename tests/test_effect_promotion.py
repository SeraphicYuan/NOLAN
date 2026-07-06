"""Effect promotion — the agent contract applied to agent-authored code.

Node-free unit tests (validation, status arc, custom-registry loading).
The live gate render + accept cycle is exercised by the fixture proposal at
projects/_clips/clip_fixture/ (kept as the worked example for agents).
"""

import json

import pytest

import nolan.effect_promotion as ep


GOOD_ENTRY = {
    "id": "test-effect", "backend": "remotion", "category": "promoted",
    "purpose": "test", "target": "TestEffect",
    "content": [], "style": [], "shared": [], "duration_default": 4.0,
    "sample_props": {"label": "X"},
    "provenance": {"clip_id": "clip_t", "agent": "t", "date": "2026-07-05"},
}

GOOD_TSX = """import React from "react";
import { useCurrentFrame } from "remotion";
const T: React.FC = () => { const f = useCurrentFrame(); return <div>{f}</div>; };
export default T;
"""


def _proposal(tmp_path, monkeypatch, entry=None, tsx=GOOD_TSX):
    pdir = tmp_path / "projects" / "_clips" / "clip_t" / "proposal"
    pdir.mkdir(parents=True)
    (pdir / "entry.json").write_text(json.dumps(entry or GOOD_ENTRY), encoding="utf-8")
    if tsx is not None:
        (pdir / "effect.tsx").write_text(tsx, encoding="utf-8")
    monkeypatch.setattr(ep, "REPO", tmp_path)
    monkeypatch.setattr(ep, "CUSTOM_REGISTRY", tmp_path / "registry_custom.json")
    monkeypatch.setattr(ep, "PROMOTED_DIR", tmp_path / "promoted")
    return pdir


def test_valid_proposal_is_clean(tmp_path, monkeypatch):
    _proposal(tmp_path, monkeypatch)
    assert ep.validate_proposal("clip_t") == []
    assert ep.promotion_status("clip_t")["stage"] == "proposed"


def test_missing_tsx_rejected(tmp_path, monkeypatch):
    _proposal(tmp_path, monkeypatch, tsx=None)
    assert any("effect.tsx missing" in p for p in ep.validate_proposal("clip_t"))


def test_nondeterminism_rejected(tmp_path, monkeypatch):
    _proposal(tmp_path, monkeypatch,
              tsx=GOOD_TSX.replace("useCurrentFrame();", "Math.random();"))
    assert any("Math.random" in p for p in ep.validate_proposal("clip_t"))


def test_id_collision_rejected(tmp_path, monkeypatch):
    entry = dict(GOOD_ENTRY, id="counter")        # exists in the real registry
    _proposal(tmp_path, monkeypatch, entry=entry)
    assert any("already exists" in p for p in ep.validate_proposal("clip_t"))


def test_python_backend_rejected(tmp_path, monkeypatch):
    entry = dict(GOOD_ENTRY, backend="python")
    _proposal(tmp_path, monkeypatch, entry=entry)
    assert any("hand-reviewed" in p for p in ep.validate_proposal("clip_t"))


def test_missing_provenance_rejected(tmp_path, monkeypatch):
    entry = dict(GOOD_ENTRY, provenance={})
    _proposal(tmp_path, monkeypatch, entry=entry)
    assert any("provenance" in p for p in ep.validate_proposal("clip_t"))


def test_accept_requires_gated(tmp_path, monkeypatch):
    _proposal(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="gated"):
        ep.accept_proposal("clip_t")


def test_custom_registry_roundtrip(tmp_path, monkeypatch):
    from nolan.motion.registry import MotionEffect, Param
    custom = tmp_path / "registry_custom.json"
    custom.write_text(json.dumps([{
        "id": "rt-effect", "backend": "remotion", "target": "RtEffect",
        "purpose": "p", "content": [{"name": "label", "type": "string"}],
        "provenance": {"clip_id": "c1"},
    }]), encoding="utf-8")
    import nolan.motion.registry as reg
    monkeypatch.setattr(reg, "__file__", str(tmp_path / "registry.py"), raising=False)
    # loader path is module-relative; call it against the temp file directly
    entries = json.loads(custom.read_text(encoding="utf-8"))
    e = MotionEffect(entries[0]["id"], entries[0]["backend"], "promoted",
                     entries[0]["purpose"], entries[0]["target"],
                     content=[Param(**c) for c in entries[0]["content"]],
                     provenance=entries[0]["provenance"])
    assert e.provenance["clip_id"] == "c1" and e.content[0].name == "label"
