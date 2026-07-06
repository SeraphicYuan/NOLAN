"""Retention linter — each rule pinned by the failure that seeded it."""

from nolan.retention import lint_plan, render_report


def _scene(i, t0, t1, template=None, energy=0.5, **kw):
    s = {"id": f"s{i}", "start_seconds": t0, "end_seconds": t1,
         "energy": energy, **kw}
    if template:
        s["layout_spec"] = {"template": template, "params": {}}
    return s


def _plan(scenes):
    return {"sections": {"A": scenes}}


def test_treatment_monotony_the_run1_case():
    # seven consecutive statistic cards — run 1's shipped failure
    scenes = [_scene(i, i * 5, i * 5 + 5, template="statistic") for i in range(7)]
    out = lint_plan(_plan(scenes))
    assert any(f["rule"] == "treatment-monotony" for f in out["findings"])


def test_varied_treatments_stay_clean():
    tpls = ["statistic", "bar_chart", "quote", "statistic", "kinetic_headline"]
    scenes = [_scene(i, i * 5, i * 5 + 5, template=t) for i, t in enumerate(tpls)]
    out = lint_plan(_plan(scenes))
    assert not any(f["rule"] == "treatment-monotony" for f in out["findings"])


def test_energy_plateau_flags_flat_arc():
    scenes = [_scene(i, i * 10, i * 10 + 10, template="quote", energy=0.35)
              for i in range(6)]                     # 60s dead flat
    out = lint_plan(_plan(scenes))
    assert any(f["rule"] == "energy-plateau" for f in out["findings"])


def test_pacing_vs_brief_consumes_the_targets():
    scenes = [_scene(0, 0, 30, template="quote"),    # way over an 4-8s target
              _scene(1, 30, 62, template="title")]
    brief = {"pacing": {"avg_scene_s_min": 4, "avg_scene_s_max": 8}}
    out = lint_plan(_plan(scenes), brief)
    assert any(f["rule"] == "pacing-vs-brief" for f in out["findings"])
    assert out["stats"]["brief_pacing"] == "4-8s"


def test_slow_hook():
    hook = [_scene(i, i * 20, i * 20 + 20, template="quote") for i in range(3)]
    rest = [_scene(9, 60, 70, template="title")]
    out = lint_plan({"sections": {"Hook": hook, "B": rest}})
    assert any(f["rule"] == "slow-hook" for f in out["findings"])


def test_static_hold_wants_shots_or_video():
    s = _scene(0, 0, 20, energy=0.2, matched_asset="a.jpg")
    out = lint_plan(_plan([s, _scene(1, 20, 25, template="quote")]))
    assert any(f["rule"] == "static-hold" for f in out["findings"])
    # a shot list absolves it
    s2 = dict(s, shots=[{"src": "a.jpg"}, {"src": "b.jpg"}])
    out2 = lint_plan(_plan([s2, _scene(1, 20, 25, template="quote")]))
    assert not any(f["rule"] == "static-hold" for f in out2["findings"])


def test_report_renders():
    out = lint_plan(_plan([_scene(0, 0, 5, template="quote")]))
    md = render_report(out)
    assert "Retention lint" in md and "never block" in md
