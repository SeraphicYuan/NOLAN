#!/usr/bin/env python3
"""Theme selector — rank NOLAN video themes against a content brief.

Powers the Checkpoint-Plan 选主题 step: instead of eyeballing 23 theme.json
files, run this to get a deterministic, explainable top-N recommendation.

Scoring combines the reasoning table (themes/selector.json: English tags,
tone/energy/formality, anti-patterns) with each theme's own mood/bestFor
(themes/<id>/theme.json, the source of truth). Stdlib only.

Usage:
    python select_theme.py "brief text describing the video"
    python select_theme.py "LLM agent paper deep dive" --tone dark --top 3
    python select_theme.py "fintech investor pitch" --json

Output:
    Ranked themes with the signals that fired (why), so the recommendation
    is auditable. --json emits {"ranked": [...]} for programmatic use.
"""

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
THEMES_DIR = SKILL_DIR  # themes/ (scripts live in themes/scripts/)
SELECTOR = THEMES_DIR / "selector.json"


def tokenize(text):
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 1]


def load():
    sel = json.loads(SELECTOR.read_text(encoding="utf-8"))
    themes = {}
    for tj in sorted(THEMES_DIR.glob("*/theme.json")):
        d = json.loads(tj.read_text(encoding="utf-8"))
        themes[d["id"]] = d
    return sel, themes


def expand(tokens, synonyms):
    out = list(tokens)
    for t in tokens:
        out.extend(synonyms.get(t, []))
    return out


def score_theme(tid, meta, theme, tokens, raw_brief, w, tone):
    hits, score = [], 0.0
    mood = set(theme.get("mood", []))
    best = " ".join(theme.get("bestFor", []))  # Chinese — substring-matched on raw brief
    tags = set(meta.get("tags", []))
    avoid = set(meta.get("avoid", []))

    for t in set(tokens):
        if t in tags:
            score += w["tag"]; hits.append(f"+tag:{t}")
        if t in mood:
            score += w["mood"]; hits.append(f"+mood:{t}")
        if t in avoid:
            score += w["avoid"]; hits.append(f"-avoid:{t}")
    # Chinese bestFor: match brief substrings against the joined bestFor string
    for frag in re.findall(r"[一-鿿]{2,}", raw_brief):
        if frag in best:
            score += w["bestFor"]; hits.append(f"+bestFor:{frag}")

    if tone:
        if meta.get("tone") == tone:
            score += w["tone_match"]; hits.append(f"+tone:{tone}")
        else:
            score += w["tone_mismatch"]; hits.append(f"-tone:{meta.get('tone')}")

    return score, hits


def main():
    ap = argparse.ArgumentParser(description="Rank NOLAN themes for a content brief.")
    ap.add_argument("brief", help="content brief / topic / script summary")
    ap.add_argument("--tone", choices=["light", "dark"], help="force light or dark")
    ap.add_argument("--top", type=int, default=3, help="how many to show (default 3)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args()

    sel, themes = load()
    w, syn = sel["weights"], sel["synonyms"]

    missing = set(themes) - set(sel["themes"])
    if missing:
        print(f"[warn] themes with no selector entry: {sorted(missing)}", file=sys.stderr)

    tokens = expand(tokenize(args.brief), syn)
    ranked = []
    for tid, meta in sel["themes"].items():
        if tid not in themes:
            continue
        s, hits = score_theme(tid, meta, themes[tid], tokens, args.brief, w, args.tone)
        ranked.append({"id": tid, "name": themes[tid].get("name", tid),
                       "nameZh": themes[tid].get("nameZh", ""), "score": round(s, 1),
                       "tone": meta.get("tone"), "why": hits})
    ranked.sort(key=lambda r: r["score"], reverse=True)

    top = ranked[: args.top]
    fallback = top and top[0]["score"] <= 0
    if fallback:
        fb = sel["fallback"]
        top = [r for r in ranked if r["id"] in fb][: args.top]

    if args.json:
        print(json.dumps({"fallback": fallback, "ranked": top}, ensure_ascii=False, indent=2))
        return

    if fallback:
        print("No strong topic match — showing safe general-purpose defaults:\n")
    for i, r in enumerate(top, 1):
        why = ", ".join(r["why"]) if r["why"] else "(no signal)"
        print(f"★ {i}. {r['nameZh']} ({r['id']})  [{r['tone']}]  score={r['score']}")
        print(f"     因为: {why}\n")


if __name__ == "__main__":
    main()
