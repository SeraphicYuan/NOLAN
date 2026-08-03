"""Titles, description and thumbnail briefs — generated, judged, revised, or exported for a human.

Two modes over ONE artifact tree, which matters: they write the same `package/` directory and differ
only in whether the judge loop runs. If export mode wrote somewhere else we would have recreated the
`renders/` problem — two homes for one class of artifact — in a new place.

  AUTO    draft-01 -> review-01 -> draft-02 -> …   (`revise`, stopping on convergence or a budget)
  EXPORT  package/EXPORT.md — one paste-able file for iterating elsewhere

Versioning mirrors the script program's existing convention (`drafts/draft-NN` + `reviews/review-NN`)
rather than inventing a second dialect for the same idea.

TWO DESIGN POINTS decide whether the auto loop is worth having at all:

1. **The judge sees the SCRIPT, not just the title.** A title judged alone optimises for clickbait; a
   title judged against the opening 60 seconds optimises for RETENTION, because the question becomes
   "does the video pay this promise off?" — which is the thing that actually determines whether a
   click was worth buying.
2. **Part of the rubric is computable.** Length, a saturated-phrasing stoplist and "the promise's key
   words appear in the opening" are checked deterministically, so the LLM is asked only for taste.
   A rubric that asks a model to count characters is a rubric that will get it wrong.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .edit import _comp_dir

MAX_TITLE = 60          # mobile truncates around here

# Phrases that mark a title as belonging to the saturated lane rather than to this essay. Not a
# morality test — a differentiation one: a title indistinguishable from a hundred others cannot earn
# a click on its own terms.
STOPLIST = ("the truth about", "exposed", "you won't believe", "shocking", "gone wrong",
            "what they don't want", "the dark side of", "explained", "debunked")


def drafts_dir(comp: str) -> Path:
    d = _comp_dir(comp) / "package" / "drafts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def reviews_dir(comp: str) -> Path:
    d = _comp_dir(comp) / "package" / "reviews"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_draft(comp: str, draft: Dict[str, Any], n: int) -> Path:
    p = drafts_dir(comp) / f"draft-{n:02d}.json"
    p.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def load_draft(comp: str, n: Optional[int] = None) -> Optional[Dict[str, Any]]:
    ds = sorted(drafts_dir(comp).glob("draft-*.json"))
    if not ds:
        return None
    p = (drafts_dir(comp) / f"draft-{n:02d}.json") if n else ds[-1]
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def latest_n(comp: str) -> int:
    ds = sorted(drafts_dir(comp).glob("draft-*.json"))
    return int(ds[-1].stem.split("-")[1]) if ds else 0


# ------------------------------------------------------------------ the computable half of the rubric

def opening_text(comp: str, seconds: float = 75.0) -> str:
    """What is SPOKEN in the opening — the window a title's promise has to be paid off in."""
    from .subtitles import cues
    return " ".join(t for s, _e, t in cues(comp) if s <= seconds)


def check_title(title: str, opening: str) -> List[str]:
    """Deterministic faults. Taste is the LLM's job; counting is not."""
    out = []
    t = (title or "").strip()
    if not t:
        return ["empty"]
    if len(t) > MAX_TITLE:
        out.append(f"{len(t)} chars — over {MAX_TITLE}, mobile will truncate it")
    for phrase in STOPLIST:
        if phrase in t.lower():
            out.append(f"saturated phrasing: {phrase!r}")
    # Does the opening actually pay this promise off? Content words from the title should show up in
    # the first ~75 seconds; if none do, the title is promising something the video defers or lacks.
    stop = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "your", "you",
            "is", "was", "it", "that", "this", "how", "why", "what", "why", "can", "cant", "never"}
    words = [w for w in re.findall(r"[a-z']+", t.lower()) if w not in stop and len(w) > 2]
    if words and not any(w.rstrip("s") in opening.lower() for w in words):
        out.append("none of the title's key words appear in the first 75s — the hook does not pay it off")
    return out


# ------------------------------------------------------------------ generation

_DRAFT_SYSTEM = (
    "You are a successful YouTube video-essayist packaging your own video. You write titles that earn "
    "a click by promising something the video actually delivers in its first minute. You never use "
    "bait the essay does not pay off — a mismatched title costs you retention, which costs you more "
    "than the click was worth."
)

_DRAFT_PROMPT = """Package this video essay.

TITLE OPTIONS: 5, each <= {max_title} chars. Vary the ANGLE, not the wording: a testable dare, a
reframe of the central claim, a curiosity gap, a concrete receipt, an evergreen/search-friendly one.
Avoid saturated phrasing ({stoplist}).

DESCRIPTION: 3-4 sentences. The first two are all that show above the fold and are what search reads.

THUMBNAIL BRIEFS: 3. Each is {{"headline": "<=4 WORDS", "layout": "<one of: {layouts}>",
"subject": "what object/image carries it", "why": "one line"}}.

Reply STRICT JSON:
{{"titles": [...], "description": "...", "thumbnail_briefs": [...]}}

THEME/TONE: {theme}
DURATION: {duration}
CHAPTERS:
{chapters}

OPENING 75 SECONDS (a title must be paid off here):
{opening}

FULL SCRIPT (abridged):
{script}
"""


def _fallback_draft(comp: str, script: str) -> Dict[str, Any]:
    """Deterministic, never blocks. The hook sentence is the essay's own first claim."""
    from nolan.packaging import _hook_sentence
    from .subtitles import chapters_text
    hook = _hook_sentence(script) or comp.replace("-", " ")
    return {"titles": [hook[:MAX_TITLE].rstrip(" ,.")],
            "description": hook,
            "thumbnail_briefs": [{"headline": " ".join(hook.split()[:4]).upper(),
                                  "layout": "statement-card", "subject": "the essay's key object",
                                  "why": "deterministic fallback — no LLM was available"}],
            "chapters": chapters_text(comp), "generated_by": "fallback"}


def initial_draft(comp: str, script: str = "", llm=None) -> Dict[str, Any]:
    """draft-01. Falls back to a deterministic draft rather than blocking a package build."""
    from .subtitles import chapters_text
    from . import manifest as M
    if llm is None:
        try:
            from nolan.config import load_config
            from nolan.llm import create_text_llm
            llm = create_text_llm(load_config())
        except Exception:
            llm = None
    if llm is None:
        return _fallback_draft(comp, script)
    from .thumbnail import LAYOUTS
    dur = (M.load(_comp_dir(comp)) or {}).get("duration_s")
    prompt = _DRAFT_PROMPT.format(
        max_title=MAX_TITLE, stoplist=", ".join(STOPLIST[:5]), layouts=" | ".join(LAYOUTS),
        theme=_theme_of(comp), duration=f"{int((dur or 0) // 60)}:{int((dur or 0) % 60):02d}",
        chapters=chapters_text(comp), opening=opening_text(comp)[:1600], script=_abridge(script))
    try:
        import asyncio
        raw = asyncio.run(llm.generate(prompt, system_prompt=_DRAFT_SYSTEM))
        d = _extract_json(raw)
        if d.get("titles"):
            d["generated_by"] = "llm"
            d["chapters"] = chapters_text(comp)
            return d
    except Exception:
        pass
    return _fallback_draft(comp, script)


def _theme_of(comp: str) -> str:
    try:
        return json.loads((_comp_dir(comp) / "hyperframes.json").read_text(encoding="utf-8")).get("theme") or ""
    except Exception:
        return ""


def _extract_json(raw: str) -> Dict[str, Any]:
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def _abridge(script: str, keep: int = 5000) -> str:
    """Script plus a beat sheet, not 13 minutes of raw prose.

    A full essay burns the model's context on wording before it can reason about STRUCTURE, which is
    what a title has to be derived from. Sections are kept whole; their middles are elided."""
    if len(script) <= keep:
        return script
    parts = re.split(r"^##\s+", script, flags=re.M)
    per = max(400, keep // max(1, len(parts)))
    out = []
    for p in parts:
        p = p.strip()
        out.append(p if len(p) <= per else p[: per // 2] + "\n  […]\n" + p[-per // 2:])
    return "\n\n## ".join(out)


# ------------------------------------------------------------------ the judge

_JUDGE_SYSTEM = (
    "You are a blunt packaging editor. You have the script, so you can tell whether a title promises "
    "something the video delivers. Reject anything the opening does not pay off, anything "
    "indistinguishable from the ten other videos on this subject, and any description whose first two "
    "lines waste the only space that shows above the fold.\n"
    "EVIDENCE DISCIPLINE: you are shown the OPENING and the chapter list, not the whole script. Say "
    "'the opening does not set this up' — never 'this figure does not appear in the video'. A judge "
    "that asserts absence from evidence it was not given is worse than no judge: it dropped a correct "
    "title for citing a number the video states at 1:45."
)

_JUDGE_PROMPT = """Critique this packaging draft. Be specific and hard to please; say what to CHANGE.

Reply STRICT JSON:
{{"verdict": "ship" | "revise",
  "title_notes": [{{"title": "...", "keep": true|false, "note": "..."}}],
  "description_note": "...",
  "thumbnail_notes": ["..."],
  "must_fix": ["blocking problems — empty if verdict is ship"]}}

DETERMINISTIC FAULTS ALREADY FOUND (do not repeat these; judge the taste):
{faults}

DRAFT:
{draft}

OPENING 75 SECONDS (this is ALL of the script you are being shown):
{opening}

CHAPTERS (the rest of the video — you cannot see its wording, only these beats):
{chapters}
"""


def judge(comp: str, draft: Dict[str, Any], llm=None) -> Dict[str, Any]:
    """Review a draft. Always returns a verdict — the deterministic faults stand alone if no LLM."""
    opening = opening_text(comp)
    faults = {t: check_title(t, opening) for t in draft.get("titles") or []}
    hard = [f"{t}: {'; '.join(v)}" for t, v in faults.items() if v]
    if llm is None:
        try:
            from nolan.config import load_config
            from nolan.llm import create_text_llm
            llm = create_text_llm(load_config())
        except Exception:
            llm = None
    out: Dict[str, Any] = {"deterministic": faults,
                           "verdict": "revise" if len(hard) >= max(1, len(faults)) else "ship",
                           "must_fix": hard, "judged_by": "deterministic"}
    if llm is None:
        return out
    from .subtitles import chapters_text
    try:
        import asyncio
        raw = asyncio.run(llm.generate(
            _JUDGE_PROMPT.format(faults="\n".join(hard) or "(none)",
                                 draft=json.dumps(draft, ensure_ascii=False)[:3000],
                                 opening=opening[:1500], chapters=chapters_text(comp)),
            system_prompt=_JUDGE_SYSTEM))
        j = _extract_json(raw)
        if j:
            # WHAT BLOCKS vs WHAT ADVISES. The deterministic faults are blocking; the LLM's notes are
            # advisory. Observed live: the model returns taste notes in `must_fix` on every round
            # ("pick a single winner", "make the description hookier") and never says ship, so
            # treating its list as blocking meant the loop could only ever end by exhausting its
            # budget — which is not convergence, it is a timeout wearing convergence's clothes.
            # So: stop when the computable rubric is clean, and surface the taste notes to the human.
            j["deterministic"] = faults
            j["notes"] = [str(x) for x in (j.get("must_fix") or [])]
            j["must_fix"] = hard
            j["verdict"] = "revise" if hard else "ship"
            j["judged_by"] = "llm+deterministic"
            return j
    except Exception:
        pass
    return out


def review_headline(review: Dict[str, Any]) -> str:
    """What the top of a review must SAY.

    It used to print the bare verdict, which is computed from the deterministic faults alone — so a
    review whose body dropped four of five titles was headed **SHIP**. Someone skimming the file reads
    the header and stops; the whole point of writing reviews to disk is that a human can skim them.
    The header now carries the taste count too, and only says SHIP when there is nothing at all left
    to act on."""
    blocking = len(review.get("must_fix") or [])
    notes = len(review.get("notes") or [])
    dropped = sum(1 for t in (review.get("title_notes") or []) if not t.get("keep"))
    if blocking:
        return f"**REVISE** — {blocking} blocking fault(s)" + (f", {notes} editor's note(s)" if notes else "")
    if notes or dropped:
        bits = []
        if dropped:
            bits.append(f"{dropped} title(s) rejected")
        if notes:
            bits.append(f"{notes} editor's note(s)")
        return "**SHIP with notes** — no blocking faults, but " + " and ".join(bits)
    return "**SHIP** — nothing outstanding"


def render_review(n: int, review: Dict[str, Any]) -> str:
    L = [f"# Review {n:02d} — {review_headline(review)}", ""]
    if review.get("must_fix"):
        L += ["## Must fix (blocking — computable)", ""] + [f"- {m}" for m in review["must_fix"]] + [""]
    if review.get("notes"):
        L += ["## Editor's notes (advisory — taste)", ""] + [f"- {m}" for m in review["notes"]] + [""]
    tn_all = review.get("title_notes") or []
    if tn_all:
        L += ["## Titles", ""]
        for tn in tn_all:
            L.append(f"- {'KEEP' if tn.get('keep') else 'DROP'} — {tn.get('title')!r}: {tn.get('note', '')}")
        L.append("")
    if review.get("description_note"):
        L += ["## Description", "", str(review["description_note"]), ""]
    if review.get("thumbnail_notes"):
        L += ["## Thumbnails", ""] + [f"- {t}" for t in review["thumbnail_notes"]] + [""]
    return "\n".join(L) + "\n"


def revise(comp: str, rounds: int = 2, llm=None) -> Dict[str, Any]:
    """AUTO mode: judge the current draft, apply the notes, repeat until `ship` or the budget runs out."""
    n = latest_n(comp)
    if n == 0:
        from .package import _script_text
        write_draft(comp, initial_draft(comp, script=_script_text(comp), llm=llm), 1)
        n = 1
    history, applied_notes = [], False
    # OFF BY ONE. This judged draft-N, wrote review-N, and then broke — so the LAST review written was
    # never applied to anything: `--rounds 2` gave one round of improvement plus a critique nobody
    # acted on, and the newest review on disk disagreed with the newest draft. Observed live: review-02
    # rejected four of draft-02's five titles and draft-02 was the shipped answer.
    #
    # Now a round is judge -> apply. If the last round produced notes we apply them and re-judge, so
    # the final review on disk is always ABOUT the final draft.
    for i in range(max(1, rounds)):
        draft = load_draft(comp, n) or {}
        rev = judge(comp, draft, llm=llm)
        (reviews_dir(comp) / f"review-{n:02d}.md").write_text(render_review(n, rev), encoding="utf-8")
        history.append({"n": n, "verdict": rev.get("verdict"), "headline": review_headline(rev),
                        "must_fix": rev.get("must_fix"), "notes": rev.get("notes")})
        actionable = bool(rev.get("must_fix")) or bool(rev.get("notes")) or \
            any(not t.get("keep") for t in (rev.get("title_notes") or []))
        if not actionable:
            break                                   # nothing left to act on — this review IS final
        if i == rounds - 1:
            break                                   # budget spent; the review above stands as advice
        nxt = _apply_review(comp, draft, rev, llm=llm)
        applied_notes = True
        n += 1
        write_draft(comp, nxt, n)
    else:
        pass
    return {"current": n, "draft": load_draft(comp, n), "history": history,
            "final_review_applies_to_current": history[-1]["n"] == n if history else False}


_REVISE_PROMPT = """Revise this packaging draft against the review. Keep what the review kept, and
REPLACE what it rejected — do not re-submit a title the review flagged. Return {n} title options.
Reply STRICT JSON in the SAME shape as the draft.

REVIEW:
{review}

DRAFT:
{draft}

OPENING 75 SECONDS (a title must be paid off here):
{opening}
"""


def _apply_review(comp: str, draft: Dict[str, Any], rev: Dict[str, Any], llm=None) -> Dict[str, Any]:
    if llm is None:
        try:
            from nolan.config import load_config
            from nolan.llm import create_text_llm
            llm = create_text_llm(load_config())
        except Exception:
            llm = None
    opening = opening_text(comp)
    if llm is not None:
        try:
            import asyncio
            raw = asyncio.run(llm.generate(
                _REVISE_PROMPT.format(n=5, review=json.dumps(rev, ensure_ascii=False)[:2500],
                                      draft=json.dumps(draft, ensure_ascii=False)[:2500],
                                      opening=opening[:1500]),
                system_prompt=_DRAFT_SYSTEM))
            d = _extract_json(raw)
            if d.get("titles"):
                # ENFORCE the computable half on the OUTPUT, not just the input. Observed live: the
                # model kept re-submitting a title the deterministic check had already rejected
                # ("De Beers wrote the rule you still follow" — none of its key words appear in the
                # first 75s), so `must_fix` never emptied and the loop could not converge. Asking
                # nicely in the prompt is not a mechanism; filtering is.
                keep = [t for t in d["titles"] if not check_title(t, opening)]
                d["titles"] = keep or sorted(d["titles"], key=lambda t: len(check_title(t, opening)))[:1]
                d["generated_by"] = "llm-revision"
                d["chapters"] = draft.get("chapters")
                return d
        except Exception:
            pass
    # No LLM: still make progress deterministically by dropping the titles that failed hard checks.
    kept = [t for t in draft.get("titles") or [] if not check_title(t, opening)]
    return {**draft, "titles": kept or draft.get("titles") or [], "generated_by": "deterministic-revision"}


# ------------------------------------------------------------------ description + export

def render_description(comp: str, draft: Dict[str, Any]) -> str:
    from .subtitles import chapters_text
    parts = [str(draft.get("description") or "").strip(), "",
             "CHAPTERS", chapters_text(comp), ""]
    prov = _comp_dir(comp) / "package" / "PROVENANCE.md"
    parts.append("Sources & credits: see the pinned comment."
                 + ("  (asset provenance: package/PROVENANCE.md)" if prov.exists() else ""))
    return "\n".join(parts) + "\n"


def export(comp: str) -> Path:
    """EXPORT mode: one paste-able file with everything a fresh model needs and nothing it doesn't."""
    from . import manifest as M
    from .package import _script_text
    from .subtitles import chapters_text
    from .edit import pool_entries
    dur = (M.load(_comp_dir(comp)) or {}).get("duration_s") or 0
    theme = _theme_of(comp)
    tokens = ""
    tf = Path(__file__).resolve().parents[3] / "themes" / theme / "tokens.css"
    if tf.exists():
        tokens = "\n".join(l.strip() for l in tf.read_text(encoding="utf-8").splitlines()
                           if re.match(r"\s*--(surface|text|accent|font)", l))[:900]
    pool = pool_entries(comp)
    assets = [f"- `{k}` — {(v.get('caption') or v.get('query') or '')[:100]}"
              for k, v in list(pool.items())[:25] if v.get("caption") or v.get("query")]
    L = [f"# Packaging brief — {comp}", "",
         "I need YouTube packaging for the video essay below: **5 title options, a description, and "
         "3 thumbnail concepts**. Titles <=60 chars; each must be paid off in the first 60 seconds. "
         "Avoid saturated phrasing (\"the truth about\", \"exposed\", \"explained\").", "",
         f"- **Duration**: {int(dur // 60)}:{int(dur % 60):02d}",
         f"- **Visual theme**: {theme}", "",
         "## Chapters", "", "```", chapters_text(comp), "```", "",
         "## Opening 75 seconds (verbatim)", "", "> " + opening_text(comp)[:1200], "",
         "## Beat sheet + script", "", _abridge(_script_text(comp), keep=9000), ""]
    if tokens:
        L += ["## Theme palette / type (for thumbnail concepts)", "", "```css", tokens, "```", ""]
    if assets:
        L += ["## Imagery already in the essay (usable in a thumbnail)", ""] + assets + [""]
    out = _comp_dir(comp) / "package" / "EXPORT.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="nolan.hyperframes.ship",
                                 description="Package titles/description/thumbnails: auto or export.")
    ap.add_argument("comp")
    ap.add_argument("--rounds", type=int, default=2, help="AUTO mode: judge/revise rounds")
    ap.add_argument("--export", action="store_true", help="EXPORT mode: write package/EXPORT.md")
    a = ap.parse_args()
    if a.export:
        print(f"wrote {export(a.comp)}")
        return
    res = revise(a.comp, rounds=a.rounds)
    print(f"draft-{res['current']:02d}")
    for h in res["history"]:
        print(f"  round {h['n']:02d}: {h['verdict']}" + (f" — {'; '.join(h['must_fix'][:3])}" if h["must_fix"] else ""))
    for t in (res["draft"] or {}).get("titles") or []:
        print(f"  · {t}")


if __name__ == "__main__":
    main()
