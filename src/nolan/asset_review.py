"""Asset Review — run an authored plan through asset acquisition BEAT BY BEAT with the full
project context (script + beatmap + facts + tempo/rhythm), saving the TOP-5 candidates + tags
per beat (accepted or not) for review and A/B comparison.

Three interchangeable "brains" (the experiment: does more context improve acquisition?):
  - engine : per-beat `auto` (in-process, full per-beat context) — the baseline.
  - plan   : ONE large-context pass plans every beat with cross-beat awareness → executor.
  - agent  : a dispatched Claude agent holding the whole project (autonomous).

Each beat result carries the same tags as the /tonal-broll gallery (mood, nonliteral, universal,
period_ok, locale_ok, flags, why) plus the beat's tempo (energy/pace/transition/motion).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, List, Optional

from .script_context import ScriptContext


def _score(c: dict) -> float:
    return (c.get("mood") or 0) + (c.get("nonliteral") or 0) * 0.3


def _tag(c: dict, accepted: bool) -> dict:
    """One candidate → the review card shape (tonal-broll tags + accepted flag + score)."""
    return {"url": c.get("url"), "poster": c.get("poster"), "kind": c.get("kind"),
            "source": c.get("source"), "duration": c.get("duration"),
            "mood": c.get("mood"), "nonliteral": c.get("nonliteral"), "universal": c.get("universal"),
            "period_ok": c.get("period_ok"), "locale_ok": c.get("locale_ok"),
            "flags": c.get("flags") or "", "why": c.get("why") or "", "reject": c.get("reject") or "",
            "metaphor": c.get("metaphor") or "", "accepted": accepted, "score": round(_score(c), 2)}


def top5(result: dict) -> List[dict]:
    """The 5 best-scored candidates from a search — accepted (picks) + rejected (considered),
    deduped by url, sorted by score. 'regardless of match'."""
    picks = result.get("picks") or []
    considered = result.get("considered") or []
    pick_urls = {p.get("url") for p in picks}
    cards = [_tag(p, True) for p in picks]
    cards += [_tag(c, False) for c in considered if c.get("url") not in pick_urls]
    cards.sort(key=lambda t: -t["score"])
    return cards[:5]


def _beat_row(ctx: ScriptContext, beat, tempo=None) -> dict:
    """The per-beat header (narration + tempo/rhythm) that every brain shares."""
    row = {"beat_idx": beat.idx, "title": beat.title, "timecode": beat.timecode,
           "pace": beat.pace, "narration": beat.narration[:600], "results": {}}
    if tempo is not None:
        bt = tempo.get(beat.idx) if hasattr(tempo, "get") else None
        if bt:
            row.update({"energy": round(bt.energy, 3), "transition": bt.transition,
                        "motion_speed": bt.motion_speed})
    return row


# ---- brain: engine (per-beat auto, baseline) --------------------------------
async def run_engine(project: str, *, media: Optional[List[str]] = None, beats: Optional[List[int]] = None,
                     progress: Callable[[float, str], None] = None) -> dict:
    """Baseline brain: each beat's `auto` search independently, in-process, full per-beat context."""
    from .config import load_config
    from .evoke_broll import EvokeBrollSearch
    progress = progress or (lambda f, m: None)
    ctx = ScriptContext.load(project)
    tempo = _tempo_map(ctx)
    searcher = EvokeBrollSearch(config=load_config())
    idxs = beats if beats is not None else [b.idx for b in ctx.beats]
    rows = []
    for n, i in enumerate(idxs):
        beat = ctx.beats[i]
        progress(n / max(1, len(idxs)), f"beat {i}: {beat.title[:30]}…")
        row = _beat_row(ctx, beat, tempo)
        res = await searcher.search(beat.narration[:600] or beat.title, operator="auto", mode="stock",
                                    project=project, beat=i, media=(media or ["image", "video"]),
                                    per_metaphor=3, max_metaphors=5)
        a = res.get("auto") or {}
        row["results"]["engine"] = {"status": res.get("status"), "operator": a.get("chosen") or res.get("operator"),
                                    "why": a.get("why") or "", "judge": (a.get("judge") or {}).get("score"),
                                    "picked": (res.get("picks") or [{}])[0].get("url") if res.get("picks") else None,
                                    "top5": top5(res)}
        rows.append(row)
    progress(1.0, "done")
    return {"project": project, "brains": ["engine"], "beats": rows}


# ---- brain: plan (one large-context pass plans all beats, cross-beat aware) -----------------
def _extract_json(text: str) -> dict:
    import re
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


async def _plan_all_beats(ctx: ScriptContext, tempo, llm) -> dict:
    """ONE large-context call: the whole script + all beats + tempo → per-beat {operator, note}
    with cross-beat awareness (avoid repeats, keep motifs, honor rhythm)."""
    lines = [f"SUBJECT: {ctx.subject}", f"SPINE: {ctx.angle}", "", "BEATS (in order):"]
    for b in ctx.beats:
        bt = tempo.get(b.idx)
        e = f" energy≈{bt.energy:.2f} ({bt.pace_dir})" if bt else ""
        lines.append(f"[{b.idx}] {b.title} · pace:{b.pace}{e}\n    {b.narration[:220]}")
    prompt = ("\n".join(lines) + "\n\n"
              "You are the b-roll director for this WHOLE video essay. For EACH beat, decide the best "
              "asset-acquisition APPROACH, thinking across the entire arc: do NOT repeat imagery between "
              "beats, keep any recurring motif deliberate, and match each beat's energy (drive→punchy/"
              "graphic, breathe→one lingering asset). Operators: literal, tonal, conceptual, ironic, "
              "trait, relational, scale, knowledge.\n"
              'STRICT JSON: {"beats":[{"idx":<int>,"operator":"<op>","note":"cross-beat guidance — what to '
              'use / avoid given the other beats (<=25 words)"}]}')
    sys = "You are a lead video-essay editor planning b-roll across a whole piece. Reply STRICT JSON."
    raw = _extract_json(await llm.generate(prompt, sys))
    out = {}
    for it in (raw.get("beats") or []):
        try:
            out[int(it["idx"])] = {"operator": it.get("operator"), "note": (it.get("note") or "")[:200]}
        except Exception:
            pass
    return out


async def run_plan(project: str, *, media: Optional[List[str]] = None, beats: Optional[List[int]] = None,
                   progress: Callable[[float, str], None] = None) -> dict:
    """Large-context brain: plan all beats in one pass (cross-beat aware), then execute each."""
    from .config import load_config
    from .llm import create_text_llm
    from .evoke_broll import EvokeBrollSearch, _OP
    progress = progress or (lambda f, m: None)
    ctx = ScriptContext.load(project)
    tempo = _tempo_map(ctx)
    llm = create_text_llm(load_config())
    progress(0.02, "Planning all beats (large context)…")
    plan = await _plan_all_beats(ctx, tempo, llm)
    searcher = EvokeBrollSearch(config=load_config())
    idxs = beats if beats is not None else [b.idx for b in ctx.beats]
    rows = []
    for n, i in enumerate(idxs):
        beat = ctx.beats[i]
        p = plan.get(i, {})
        op = p.get("operator") if p.get("operator") in _OP else "auto"
        note = p.get("note", "")
        progress(0.05 + 0.9 * n / max(1, len(idxs)), f"beat {i} via {op}…")
        row = _beat_row(ctx, beat, tempo)
        res = await searcher.search(beat.narration[:600] or beat.title, operator=op, mode="stock",
                                    project=project, beat=i, extra_context=note,
                                    media=(media or ["image", "video"]), per_metaphor=3, max_metaphors=5)
        row["results"]["plan"] = {"status": res.get("status"), "operator": op, "why": note,
                                  "picked": (res.get("picks") or [{}])[0].get("url") if res.get("picks") else None,
                                  "top5": top5(res)}
        rows.append(row)
    progress(1.0, "done")
    return {"project": project, "brains": ["plan"], "beats": rows}


def _tempo_map(ctx: ScriptContext):
    """Rule-based tempo per beat (fast, no LLM) → {idx: BeatTempo} for the review header."""
    try:
        from .tempo_plan import design_tempo
        plan = design_tempo(ctx)                       # rules (no llm) — cheap
        return {b.idx: b for b in plan.beats}
    except Exception:
        return {}


_BRAIN_LABEL = {"engine": "Engine (per-beat auto)", "plan": "Plan (large-context)",
                "agent": "Agent (autonomous)"}


def _esc(s) -> str:
    return (str(s if s is not None else "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _chip(label, v):
    if v is None:
        return f'<span class="ch" style="background:#444">{label} ?</span>'
    col = "#1f7a4d" if v >= 8 else "#7a6a1f" if v >= 5 else "#7a2f2f"
    return f'<span class="ch" style="background:{col}">{label} {v}/10</span>'


def _card(c: dict) -> str:
    isimg = c.get("kind") == "image"
    src = c.get("poster") or c.get("url") or ""
    media = (f'<img src="{_esc(src)}" loading="lazy">' if (isimg or c.get("poster"))
             else f'<div class="noimg">{_esc(c.get("kind") or "?")}</div>')
    place = ('<span class="ch" style="background:#2f5f7a">universal</span>' if c.get("universal")
             else _chip("per", c.get("period_ok")) + _chip("loc", c.get("locale_ok")))
    flag = f'<span class="ch" style="background:#7a2f2f">{_esc(c.get("flags"))}</span>' if c.get("flags") else ""
    rej = f'<span class="ch" style="background:#5a3a1a">{_esc(c.get("reject"))}</span>' if (c.get("reject") and not c.get("accepted")) else ""
    cls = "card accepted" if c.get("accepted") else "card"
    return (f'<div class="{cls}">{media}<div class="m">'
            f'{_chip("fit", c.get("mood"))}{_chip("2nd", c.get("nonliteral"))}{place}{flag}{rej}'
            f'<div class="why">{_esc((c.get("why") or c.get("reject") or "")[:80])}</div>'
            f'<div class="src">{_esc(c.get("source"))}'
            + (' · <b style="color:#95d5b2">picked</b>' if c.get("accepted") and c.get("_picked") else '')
            + '</div></div></div>')


def render_gallery(review: dict) -> str:
    brains = review.get("brains", [])
    rows = []
    for b in review.get("beats", []):
        head = (f'<div class="beat-head"><div class="bt">{b["beat_idx"] + 1}. {_esc(b["title"])}'
                + (f' <span class="tc">[{_esc(b["timecode"])}]</span>' if b.get("timecode") else '')
                + '</div>'
                + (f'<div class="tempo">⚡ energy {b.get("energy")} · {_esc(b.get("pace"))} · '
                   f'✂ {_esc(b.get("transition"))} · ▶ {_esc(b.get("motion_speed"))}</div>' if b.get("energy") is not None else '')
                + f'<div class="narr">{_esc(b["narration"][:280])}</div></div>')
        cols = []
        for br in brains:
            r = (b.get("results") or {}).get(br)
            if not r:
                cols.append(f'<div class="brain"><div class="bh">{_esc(_BRAIN_LABEL.get(br, br))}</div><div class="empty">—</div></div>')
                continue
            picked = r.get("picked")
            cards = ""
            for c in r.get("top5", []):
                c = dict(c); c["_picked"] = (c.get("url") == picked)
                cards += _card(c)
            st = r.get("status", "?")
            meta = (f'<span class="st {"ok" if st == "MATCHED" else "no"}">{st}</span> '
                    f'via <b>{_esc(r.get("operator"))}</b>'
                    + (f' · judge {r.get("judge")}/10' if r.get("judge") is not None else '')
                    + (f'<div class="rw">{_esc((r.get("why") or "")[:90])}</div>' if r.get("why") else ''))
            cols.append(f'<div class="brain"><div class="bh">{_esc(_BRAIN_LABEL.get(br, br))} · {meta}</div>'
                        f'<div class="grid">{cards or "<div class=empty>no candidates</div>"}</div></div>')
        rows.append(f'<div class="beat">{head}<div class="brains">{"".join(cols)}</div></div>')

    return f'''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Asset Review · {_esc(review.get("project"))}</title>
<style>:root{{color-scheme:dark}}body{{margin:0;background:#0d0d10;color:#e8e8ea;font:14px/1.5 -apple-system,"Segoe UI",Roboto,sans-serif}}
.wrap{{max-width:1500px;margin:0 auto;padding:24px 18px 60px}}h1{{font-size:22px;margin:0 0 2px}}.sub{{color:#9a9aa2;font-size:13px;margin:0 0 20px}}
.beat{{border:1px solid #26262e;border-radius:12px;margin-bottom:20px;overflow:hidden;background:#131318}}
.beat-head{{padding:12px 14px;background:#181820;border-bottom:1px solid #26262e}}.bt{{font-weight:600;font-size:15px}}.tc{{color:#8a8a92;font-weight:400;font-size:12px}}
.tempo{{font-size:12px;color:#c9a94e;margin-top:3px}}.narr{{font-size:12px;color:#9a9aa2;margin-top:5px}}
.brains{{display:grid;grid-template-columns:repeat({max(1, len(brains))},1fr);gap:1px;background:#26262e}}
.brain{{background:#131318;padding:10px}}.bh{{font-size:12px;color:#c7c7d0;margin-bottom:8px;font-weight:600}}.rw{{font-weight:400;color:#8a8a92;margin-top:3px;font-size:11px}}
.st{{padding:1px 6px;border-radius:4px;font-size:11px}}.st.ok{{background:#1f7a4d}}.st.no{{background:#7a2f2f}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px}}
.card{{border:1px solid #26262e;border-radius:7px;overflow:hidden;background:#000}}.card.accepted{{border-color:#2d6a4f}}
.card img{{width:100%;height:78px;object-fit:cover;display:block}}.noimg{{height:78px;display:flex;align-items:center;justify-content:center;color:#555;font-size:11px}}
.m{{padding:5px 6px;background:#131318}}.ch{{display:inline-block;font-size:9px;padding:1px 5px;border-radius:4px;margin:1px 2px 0 0;color:#fff}}
.why{{font-size:10px;color:#aaa;margin-top:3px}}.src{{font-size:9px;color:#777;margin-top:2px}}.empty{{color:#555;font-size:12px;padding:8px}}
</style></head><body><div class="wrap"><h1>Asset Review · {_esc(review.get("project"))}</h1>
<div class="sub">Beat-by-beat asset acquisition with full project context. Top-5 candidates per beat (green = accepted). Brains: {_esc(", ".join(brains))}.</div>
{"".join(rows)}</div></body></html>'''


def write_gallery(project: str, review: dict) -> Path:
    out = Path("projects") / "_library" / "_broll_generated" / f"asset_review_{project}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_gallery(review), encoding="utf-8")
    return out


# ---- brain: agent (dispatched autonomous Claude agent, whole project in context) -----------
async def run_agent(project: str, *, agent: str = "nolan4", media: Optional[List[str]] = None,
                    beats: Optional[List[int]] = None, timeout_s: int = 2400,
                    progress: Callable[[float, str], None] = None) -> dict:
    """Autonomous brain: dispatch a NOLAN Claude agent that holds the WHOLE project and runs the
    `nolan broll` search per beat (choosing operators holistically). We poll for its per-beat JSON
    output files and assemble the review — so the structured top-5 comes from our code, not the agent."""
    import asyncio
    from .webui.operations import _dispatch_to_tmux
    progress = progress or (lambda f, m: None)
    ctx = ScriptContext.load(project)
    tempo = _tempo_map(ctx)
    idxs = beats if beats is not None else [b.idx for b in ctx.beats]
    outdir = Path("projects") / project / ".agent_broll"
    outdir.mkdir(parents=True, exist_ok=True)
    for i in idxs:
        (outdir / f"beat_{i}.json").unlink(missing_ok=True)
    mset = " ".join(f"--media {m}" for m in (media or ["image"]))
    beat_list = "\n".join(f'  beat {i}: "{ctx.beats[i].narration[:110]}…"' for i in idxs)
    prompt = (
        f"Acquire b-roll for the video-essay project '{project}' BEAT BY BEAT. First read the full "
        f"context: projects/{project}/script.md, projects/{project}/scriptgen/beatmap.md, "
        f"projects/{project}/scriptgen/facts.md, and projects/{project}/scene_plan.json (note each "
        f"scene's energy/transition/motion_speed — that's the intended rhythm). Reason across the "
        f"WHOLE arc: do NOT repeat imagery between beats, keep any recurring motif deliberate, and "
        f"match each beat's energy (drive→punchy/graphic, breathe→one lingering asset).\n\n"
        f"For EACH of these beats, pick the best operator and run the search:\n{beat_list}\n\n"
        f"Run (from the repo root) per beat:\n"
        f"  D:\\env\\nolan\\python.exe -X utf8 -m nolan broll \"<the beat's key line>\" -op <operator> "
        f"-p {project} --beat <idx> -m stock {mset} -o projects/{project}/.agent_broll/beat_<idx>.json\n"
        f"Operators: literal, tonal, conceptual, ironic, trait, relational, scale, knowledge, auto.\n"
        f"Do ALL {len(idxs)} beats (idx: {', '.join(map(str, idxs))}). Reply 'ASSET REVIEW DONE' when finished.")
    progress(0.02, f"dispatching to {agent}…")
    _dispatch_to_tmux(agent, prompt)
    import time
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        have = sum(1 for i in idxs if (outdir / f"beat_{i}.json").exists())
        progress(0.05 + 0.9 * have / max(1, len(idxs)), f"{agent}: {have}/{len(idxs)} beats done…")
        if have >= len(idxs):
            break
        await asyncio.sleep(10)
    rows = []
    for i in idxs:
        beat = ctx.beats[i]
        row = _beat_row(ctx, beat, tempo)
        f = outdir / f"beat_{i}.json"
        res = {}
        if f.exists():
            try:
                res = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                res = {}
        row["results"]["agent"] = {
            "status": res.get("status", "PENDING"), "operator": res.get("operator"),
            "why": (res.get("auto") or {}).get("why") or res.get("goal", ""),
            "picked": (res.get("picks") or [{}])[0].get("url") if res.get("picks") else None,
            "top5": top5(res) if res else []}
        rows.append(row)
    progress(1.0, "done")
    return {"project": project, "brains": ["agent"], "beats": rows}


# ---- driver: run chosen brains, merge, render the comparison gallery -------------------------
async def run_review(project: str, *, brains=("engine",), beats: Optional[List[int]] = None,
                     media: Optional[List[str]] = None, agent: str = "nolan4", fresh: bool = True,
                     progress: Callable[[float, str], None] = None) -> dict:
    """Run one or more brains over the plan, merge per beat, save + render the comparison gallery."""
    progress = progress or (lambda f, m: None)
    if fresh:
        (Path("projects") / project / "asset_review.json").unlink(missing_ok=True)
    runner = {"engine": run_engine, "plan": run_plan, "agent": run_agent}
    for bi, brain in enumerate(brains):
        fn = runner.get(brain)
        if not fn:
            continue
        kw = {"media": media, "beats": beats,
              "progress": lambda f, m, _b=brain: progress((bi + f) / len(brains), f"[{_b}] {m}")}
        if brain == "agent":
            kw["agent"] = agent
        r = await fn(project, **kw)
        merged = merge_review(project, r)
        save_review(project, merged)
    review = json.loads((Path("projects") / project / "asset_review.json").read_text(encoding="utf-8"))
    write_gallery(project, review)
    return review


def save_review(project: str, review: dict) -> Path:
    out = Path("projects") / project / "asset_review.json"
    out.write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def merge_review(project: str, review: dict) -> dict:
    """Merge a brain's results into an existing asset_review.json (for multi-brain compare)."""
    out = Path("projects") / project / "asset_review.json"
    if out.exists():
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
        except Exception:
            prev = None
        if prev and prev.get("project") == project:
            by_idx = {r["beat_idx"]: r for r in prev.get("beats", [])}
            for r in review.get("beats", []):
                dst = by_idx.get(r["beat_idx"])
                if dst:
                    dst.setdefault("results", {}).update(r.get("results", {}))
                else:
                    prev.setdefault("beats", []).append(r)
            prev["brains"] = sorted(set(prev.get("brains", [])) | set(review.get("brains", [])))
            return prev
    return review
