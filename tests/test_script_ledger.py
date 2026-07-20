"""Phase-4 tests: the review learning ledger (record → distill → draft priors)."""

import json

from nolan.scriptwriter import ScriptProjectStore, ledger


def _seed(tmp_path, subject="the economy debate", style="chan"):
    store = ScriptProjectStore(tmp_path)
    slug = store.create("L", subject=subject, style_id=style, target_minutes=20)
    store.set_ad_hoc_questions(slug, ["Are all the metaphors strong and fitting?"])
    store.reviews_dir(slug).mkdir(parents=True, exist_ok=True)
    findings = [
        {"id": "f1", "dim": "evidential-sufficiency", "severity": "med"},
        {"id": "f2", "dim": "figurative-fitness", "severity": "low"},
        {"id": "f3", "dim": "evidential-sufficiency", "severity": "high"},
    ]
    store.review_findings_path(slug, 1).write_text(json.dumps(findings), encoding="utf-8")
    return store, slug


def test_record_splits_approved_and_rejected(tmp_path):
    store, slug = _seed(tmp_path)
    ev = ledger.record_review_decision(slug, store, 1, ["f1", "f3"])   # approve both ev-suff
    assert ev and len(ev["approved"]) == 2 and len(ev["rejected"]) == 1
    assert ev["archetype"] == "long-form-argument" and ev["style_id"] == "chan"
    assert ledger._ledger_path(tmp_path).exists()


def test_distill_computes_rates(tmp_path):
    store, slug = _seed(tmp_path)
    ledger.record_review_decision(slug, store, 1, ["f1", "f3"])
    d = ledger.distill(tmp_path)
    assert d["events"] == 1
    assert d["by_dim"]["evidential-sufficiency"] == {"approved": 2, "rejected": 0, "rate": 1.0}
    assert d["by_dim"]["figurative-fitness"]["rejected"] == 1
    # scoping
    assert ledger.distill(tmp_path, archetype="explainer")["events"] == 0


def test_draft_priors_needs_enough_data(tmp_path):
    store, slug = _seed(tmp_path)
    ledger.record_review_decision(slug, store, 1, ["f1", "f3"])   # 1 event only
    assert ledger.draft_priors(tmp_path, "long-form-argument", "chan") == ""
    for _ in range(3):
        ledger.record_review_decision(slug, store, 1, ["f1", "f3"])  # 4 events total
    priors = ledger.draft_priors(tmp_path, "long-form-argument", "chan")
    assert "Producer priors" in priors
    assert "metaphors" in priors.lower()              # recurring ad-hoc surfaced
    assert "evidential-sufficiency" in priors         # hot dimension surfaced


def test_draft_priors_empty_for_unseen_scope(tmp_path):
    store, slug = _seed(tmp_path)
    for _ in range(4):
        ledger.record_review_decision(slug, store, 1, ["f1", "f3"])
    assert ledger.draft_priors(tmp_path, "biography", "other-style") == ""
