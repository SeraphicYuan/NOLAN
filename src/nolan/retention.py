"""Retention linter (SOTA #4) — static analysis of the plan for attention rot.

Editors feel monotony; a pipeline has to MEASURE it. This lints the authored
plan (+ the compiled brief's pacing targets) for the patterns that lose
viewers, each rule seeded by an observed failure:

  treatment-monotony   run 1 shipped SEVEN consecutive `statistic` cards
  energy-plateau       the tempo pass authored per-section-flat levers
  visual-mode-run      "6 consecutive art stills" reads as a slideshow
  pacing-vs-brief      brief.pacing was authored with no consumer — this is
                       its consumer (measured durations vs the targets)
  slow-hook            an opening section that outstays its welcome
  static-hold          a long low-energy scene with nothing moving in it

Pure analysis: no LLM, no render. Findings are REPORTED (a step report for
the Step Inspector + `nolan lint`), never silently enforced — taste calls
stay with the human; the linter just refuses to let them pass unseen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

SEV_WARN = "warn"
SEV_INFO = "info"


def _scenes_in_order(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = [s for sc in (plan.get("sections") or {}).values()
           if isinstance(sc, list) for s in sc if isinstance(s, dict)]
    out.sort(key=lambda s: float(s.get("start_seconds") or 0.0))
    return out


def _dur(s: Dict[str, Any]) -> float:
    try:
        return max(0.0, float(s.get("end_seconds") or 0)
                   - float(s.get("start_seconds") or 0))
    except (TypeError, ValueError):
        return 0.0


def _treatment(s: Dict[str, Any]) -> str:
    """The scene's treatment identity, most specific first."""
    spec = s.get("layout_spec")
    if isinstance(spec, dict) and spec.get("template"):
        return f"layout:{spec['template']}"
    ms = s.get("motion_spec")
    if isinstance(ms, dict) and ms.get("effect"):
        return f"motion:{ms['effect']}"
    if s.get("shots"):
        return "shots"
    if s.get("rendered_clip") or s.get("matched_clip"):
        return "video"
    if s.get("matched_asset") or s.get("generated_asset"):
        return "still"
    return "unresolved"


def _treatment_class(t: str) -> str:
    """Coarse class for pattern-interrupt analysis: text vs data vs media."""
    if t.startswith("layout:"):
        tpl = t.split(":", 1)[1]
        data = {"statistic", "stat_comparison", "bar_chart", "line_chart",
                "percentage_bar", "pie_percentage", "counter", "data_table",
                "ranking", "progress_bar", "loop_diagram", "timeline"}
        return "data" if tpl in data else "text"
    if t in ("video", "still", "shots"):
        return "media"
    if t.startswith("motion:"):
        return "motion"
    return t


def lint_plan(plan: Dict[str, Any],
              brief: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """{"findings": [{rule, severity, at, message}], "stats": {...}}."""
    scenes = _scenes_in_order(plan)
    findings: List[Dict[str, Any]] = []
    if not scenes:
        return {"findings": [{"rule": "empty-plan", "severity": SEV_WARN,
                              "at": "0.0s", "message": "plan has no scenes"}],
                "stats": {}}

    def add(rule, sev, scene, msg):
        findings.append({"rule": rule, "severity": sev,
                         "at": f"{float(scene.get('start_seconds') or 0):.1f}s",
                         "scene": scene.get("id"), "message": msg})

    # 1. treatment monotony: >2 consecutive scenes, same specific treatment
    run_start, run_t = 0, _treatment(scenes[0])
    for i in range(1, len(scenes) + 1):
        t = _treatment(scenes[i]) if i < len(scenes) else None
        if t != run_t:
            n = i - run_start
            if n > 2 and run_t not in ("unresolved",):
                add("treatment-monotony", SEV_WARN, scenes[run_start],
                    f"{n} consecutive scenes render as {run_t} "
                    f"({scenes[run_start].get('id')}…{scenes[i-1].get('id')}) "
                    "— vary the treatment (see the blocks/motion catalogs)")
            run_start, run_t = i, t

    # 2. visual-mode runs: >4 consecutive scenes in the same coarse class
    run_start, run_c = 0, _treatment_class(_treatment(scenes[0]))
    for i in range(1, len(scenes) + 1):
        c = _treatment_class(_treatment(scenes[i])) if i < len(scenes) else None
        if c != run_c:
            n = i - run_start
            span = sum(_dur(s) for s in scenes[run_start:i])
            if n > 4:
                add("visual-mode-run", SEV_WARN, scenes[run_start],
                    f"{n} consecutive {run_c} scenes ({span:.0f}s) — a "
                    "pattern interrupt is overdue")
            run_start, run_c = i, c

    # 3. energy plateau: a ≥45s window where energy never moves ±0.05
    window: List[Dict[str, Any]] = []
    for s in scenes:
        e = s.get("energy")
        if e is None:
            continue
        if window and abs(float(e) - float(window[0].get("energy"))) > 0.05:
            span = sum(_dur(x) for x in window)
            if span >= 45:
                add("energy-plateau", SEV_INFO, window[0],
                    f"energy flat at ~{float(window[0]['energy']):.2f} for "
                    f"{span:.0f}s across {len(window)} scenes — the arc "
                    "isn't moving (tempo levers are per-beat; consider "
                    "varying within the section)")
            window = [s]
        else:
            window.append(s)
    if window:
        span = sum(_dur(x) for x in window)
        if span >= 45:
            add("energy-plateau", SEV_INFO, window[0],
                f"energy flat at ~{float(window[0].get('energy') or 0):.2f} "
                f"for {span:.0f}s across {len(window)} scenes")

    # 4. pacing vs the brief's authored targets
    stats: Dict[str, Any] = {}
    durs = [_dur(s) for s in scenes if _dur(s) > 0]
    if durs:
        stats["avg_scene_s"] = round(sum(durs) / len(durs), 2)
        stats["scene_count"] = len(durs)
    pacing = (brief or {}).get("pacing") or {}
    if durs and pacing:
        lo = float(pacing.get("avg_scene_s_min", 0) or 0)
        hi = float(pacing.get("avg_scene_s_max", 1e9) or 1e9)
        outside = [s for s in scenes if _dur(s) > 0
                   and not lo * 0.5 <= _dur(s) <= hi * 1.5]
        stats["brief_pacing"] = f"{lo:.0f}-{hi:.0f}s"
        if stats["avg_scene_s"] > hi or stats["avg_scene_s"] < lo:
            add("pacing-vs-brief", SEV_WARN, scenes[0],
                f"average scene {stats['avg_scene_s']}s vs the brief's "
                f"{lo:.0f}-{hi:.0f}s target")
        for s in outside:
            add("pacing-vs-brief", SEV_INFO, s,
                f"{s.get('id')} runs {_dur(s):.1f}s — far outside the "
                f"brief's {lo:.0f}-{hi:.0f}s window")

    # 5. slow hook: the first section overstays
    sections = [sc for sc in (plan.get("sections") or {}).values()
                if isinstance(sc, list) and sc]
    if sections:
        first = sections[0]
        first_span = sum(_dur(s) for s in first if isinstance(s, dict))
        total = sum(durs) if durs else 0
        if total and (first_span > 45 or first_span / total > 0.25):
            add("slow-hook", SEV_WARN, first[0],
                f"opening section runs {first_span:.0f}s "
                f"({100 * first_span / total:.0f}% of the video) — viewers "
                "decide in the first 30s")

    # 6. static holds: a long, low-energy scene with nothing moving
    for s in scenes:
        e = float(s.get("energy") or 0.5)
        if (_dur(s) > 12 and e < 0.4 and _treatment(s) == "still"
                and not s.get("shots")):
            add("static-hold", SEV_INFO, s,
                f"{s.get('id')}: {_dur(s):.0f}s low-energy single still — "
                "consider a shot list or a video match")

    # 7-9. script-craft rules (quality program step 6) — driven by the style
    # pack's format section (the show bible). The reference-video habits:
    # hooks pose questions and anchor on concrete OBJECTS; sections end on
    # forward tension, not a closed thought.
    fmt = _pack_format(brief)
    lint_cfg = fmt.get("lint") or {}
    hook_text = " ".join(
        (s.get("narration_excerpt") or s.get("narration") or "")
        for s in (sections[0][:3] if sections else []) if isinstance(s, dict))
    if lint_cfg.get("hook_question") and sections and hook_text:
        if not _reads_as_question(hook_text):
            add("hook-question", SEV_WARN, sections[0][0],
                f"[pack:{fmt.get('pack')}] the hook never poses or implies "
                "the question the video answers — reference hooks open on "
                "mystery, ours opens on exposition")
    if lint_cfg.get("object_anchor") and sections and hook_text:
        if not _has_object_anchor(hook_text):
            add("object-anchor", SEV_WARN, sections[0][0],
                f"[pack:{fmt.get('pack')}] the hook names no concrete "
                "object/document/place to anchor on ('a secret contained in "
                "THESE TWO LETTERS') — abstractions don't hold a cold open")
    if lint_cfg.get("section_out_tension") and len(sections) > 1:
        for sec in sections[:-1]:
            last = next((s for s in reversed(sec)
                         if isinstance(s, dict)
                         and (s.get("narration_excerpt") or s.get("narration"))), None)
            if last is None:
                continue
            out = (last.get("narration_excerpt") or last.get("narration") or "").strip()
            if out and not _reads_as_tension(out):
                add("section-out-tension", SEV_INFO, last,
                    f"[pack:{fmt.get('pack')}] section ends on a closed "
                    f"thought ('…{out[-60:]}') — an out should pull forward "
                    "(question, reversal, 'but/until/yet')")

    stats["warn"] = sum(1 for f in findings if f["severity"] == SEV_WARN)
    stats["info"] = sum(1 for f in findings if f["severity"] == SEV_INFO)
    return {"findings": findings, "stats": stats}


# --- script-craft heuristics (deterministic, report-only) ---------------------

_QUESTION_WORDS = ("why ", "how ", "what ", "who ", "where ", "when ",
                   "secret", "mystery", "no one knew", "nobody knew",
                   "unanswered", "strange", "puzzle", "vanish")
_OBJECT_CUES = ("this ", "these ", "that ", "those ", "the letter",
                "a letter", "document", "manuscript", "map ", "vase",
                "painting", "photograph", "artifact", "diary", "archive",
                "amphora", "inscription", "ruins")
_TENSION_CUES = ("but ", "until ", "yet ", "except", "unless", "however",
                 "what happened next", "that was about to change",
                 "would change everything", "no one expected", "…", "...")


def _pack_format(brief: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    try:
        from nolan.style_packs import format_rules, get_pack
        pack = get_pack((brief or {}).get("pack") or "default")
        if pack:
            return format_rules(pack)
    except Exception:
        pass
    return {"pack": "default", "lint": {}}


def _reads_as_question(text: str) -> bool:
    t = " " + text.lower()
    return "?" in text or any(w in t for w in _QUESTION_WORDS)


def _has_object_anchor(text: str) -> bool:
    t = " " + text.lower()
    return any(w in t for w in _OBJECT_CUES)


def _reads_as_tension(text: str) -> bool:
    t = text.lower()
    return "?" in text or any(w in t for w in _TENSION_CUES)


def render_report(result: Dict[str, Any], title: str = "Retention lint") -> str:
    lines = [f"# {title}", ""]
    st = result.get("stats", {})
    lines.append(f"**{st.get('warn', 0)} warnings · {st.get('info', 0)} notes** "
                 f"· {st.get('scene_count', '?')} scenes · avg "
                 f"{st.get('avg_scene_s', '?')}s"
                 + (f" · brief pacing {st['brief_pacing']}" if st.get("brief_pacing") else ""))
    lines.append("")
    if not result["findings"]:
        lines.append("Clean — no retention flags.")
    for f in result["findings"]:
        mark = "⚠" if f["severity"] == SEV_WARN else "·"
        lines.append(f"- {mark} `{f['rule']}` @{f['at']}: {f['message']}")
    lines.append("")
    lines.append("_Rules are seeded from observed failures; the linter reports, "
                 "humans decide. Findings never block a render._")
    return "\n".join(lines)


def lint_project(project_path: Path) -> Dict[str, Any]:
    import json
    plan = json.loads((Path(project_path) / "scene_plan.json")
                      .read_text(encoding="utf-8"))
    brief = None
    try:
        from nolan.project_brief import load_brief
        brief = load_brief(Path(project_path))
    except Exception:
        pass
    return lint_plan(plan, brief)
