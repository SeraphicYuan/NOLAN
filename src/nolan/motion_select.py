"""Motion-selection layer — the "brain" that decides HOW to animate a chosen asset.

A found clip or still is only half the cut; the other half is the MOTION applied to it.
This layer maps (operator + the line's intent + the asset kind) → a motivated motion
treatment from a defined vocabulary, so a static photo reads as cinema (not a slideshow)
and a clip is left alone unless emphasis is wanted.

It attaches `pick["motion"] = {id, label, means, why, available}` to each accepted asset.
`available` marks whether the render effect exists yet (Ken Burns, hold, as-is) or is planned
(parallax, atmospheric, rack-focus, blur-in) — the selection recommends the right treatment
now; effects light up as they land in the motion library / ComfyUI.
"""
from __future__ import annotations

import json
import re
from typing import List, Optional


def _extract_json(txt: str):
    txt = (txt or "").strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()
    a, b = txt.find("{"), txt.rfind("}")
    return json.loads(txt[a:b + 1])


# kinds: "image" (stock photo), "stock" (stock video clip), "library" (indexed video segment)
MOTION_VOCAB = {
    # --- stills need real motion ---
    "ken-burns-in":  {"label": "Ken Burns — push in", "kinds": ["image", "stock", "library"],
                      "means": "intensify / draw closer / significance", "available": True},
    "ken-burns-out": {"label": "Ken Burns — pull out", "kinds": ["image", "stock", "library"],
                      "means": "reveal context, or isolation (subject small in frame)", "available": True},
    "ken-burns-pan": {"label": "Ken Burns — pan", "kinds": ["image", "stock", "library"],
                      "means": "drift along a leading line / reveal in reading order", "available": True},
    "parallax":      {"label": "2.5D parallax", "kinds": ["image"],
                      "means": "fake depth / immersion — 'you are there'", "available": True},
    "atmospheric":   {"label": "atmospheric overlay", "kinds": ["image", "stock", "library"],
                      "means": "drifting particles/fog/grain — mood; makes a flat frame feel shot", "available": False},
    "rack-focus":    {"label": "rack focus", "kinds": ["image"],
                      "means": "shift attention / a realization", "available": False},
    "blur-in":       {"label": "blur → sharp reveal", "kinds": ["image", "stock"],
                      "means": "coming into focus / a reveal", "available": False},
    "hold":          {"label": "hold (static)", "kinds": ["image", "stock", "library"],
                      "means": "restraint — let the words land", "available": True},
    # --- clips already move ---
    "as-is":         {"label": "play as-is", "kinds": ["stock", "library"],
                      "means": "the footage already moves; no added camera", "available": True},
    "subtle-push":   {"label": "subtle push on clip", "kinds": ["stock", "library"],
                      "means": "gentle emphasis on moving footage", "available": True},
}


def _fallback(kind: str) -> str:
    return "as-is" if kind in ("stock", "library") else "ken-burns-in"


_MOTION_SYS = (
    "You are a video-essay editor deciding HOW to animate each chosen asset so it reads as cinema, "
    "not a slideshow. Motion must be MOTIVATED by the line's meaning, not decoration. Reply STRICT JSON.")


def _motion_prompt(line: str, goal: str, operator: str, picks: List[dict]) -> str:
    vocab = "\n".join(f'- {mid} ({v["label"]}): {v["means"]} [kinds: {"/".join(v["kinds"])}]'
                      for mid, v in MOTION_VOCAB.items())
    items = "\n".join(f'[{i}] kind={p.get("kind", "image")} — {p.get("why", "") or p.get("desc", "")}'
                      for i, p in enumerate(picks))
    return (f'LINE: "{line}"\nTARGET: {goal}\nPAIRING OPERATOR: {operator}\n\n'
            f"MOTION VOCABULARY:\n{vocab}\n\n"
            f"CHOSEN ASSETS — animate EACH; pick one motion id VALID for its kind:\n{items}\n\n"
            "Motivate it: push-in=significance, pull-out=isolation/context, pan=leading line, "
            "parallax=immersion, rack-focus=realization, atmospheric=mood, hold=restraint. "
            "A video CLIP usually plays 'as-is' unless emphasis is wanted; a STILL always needs motion "
            "(never leave a photo static unless 'hold' is a deliberate beat).\n"
            'JSON: {"motions": [{"i": <index>, "id": "<motion id>", "why": "<=10 words"}]}')


async def recommend_motions(llm, line: str, goal: str, operator: str, picks: List[dict]) -> None:
    """Attach a motivated `motion` treatment to each pick (in place). LLM-driven, rules-fallback."""
    if not picks:
        return
    by_i = {}
    try:
        j = _extract_json(await llm.generate(_motion_prompt(line, goal, operator, picks), _MOTION_SYS))
        by_i = {m.get("i"): m for m in j.get("motions", [])}
    except Exception:
        by_i = {}
    for i, p in enumerate(picks):
        kind = p.get("kind", "image")
        m = by_i.get(i) or {}
        mid = m.get("id")
        if mid not in MOTION_VOCAB or kind not in MOTION_VOCAB[mid]["kinds"]:
            mid = _fallback(kind)                        # invalid/missing → sensible default
        v = MOTION_VOCAB[mid]
        p["motion"] = {"id": mid, "label": v["label"], "means": v["means"],
                       "available": v["available"], "why": m.get("why", "")}
