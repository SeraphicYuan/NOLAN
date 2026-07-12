"""VLM usability FLOOR for the acquisition pool — the semantic cull CLIP can't do.

CLIP cosine lives in a narrow 0.14–0.33 band, so it can't tell a sports car from a "permit" (both
score ~0.22), and Tesseract misses stylized/overlaid text + watermarks. This is a ONE-vision-call
floor, FUSED with the caption pass (so it costs ~one extra prompt, not an extra call): per kept image
it returns {usable, flags, caption}. Assets that are FLAGGED (watermark / overlaid text / stock-photo
graphic / logo) or below the usability floor are dropped. It is a FLOOR that removes junk — NOT a
re-ranker; the cheap CLIP/tier gates still order what survives. Video + generated stills are exempt.

Pure prompt/parse/decision (no I/O) so it is unit-testable without a VLM; `pool.py` does the vision
call and the file cull. Mirrors the evoke_broll b-roll screen's unusable-still vocabulary, kept local
so this organ doesn't import the /broll lab.
"""
from __future__ import annotations

import json
import re
from typing import Dict, Optional

# A still with ANY of these is out regardless of relevance (same vocabulary the evoke_broll b-roll
# screen uses to reject unusable stills).
UNUSABLE_FLAGS = ("watermark", "overlaid text", "heavy text", "text overlay", "stock-photo graphic", "logo")

SYS = ("You are a documentary photo editor triaging one stock/library image as b-roll for a single "
       "beat of a video essay. Reply STRICT JSON only.")


def judge_prompt(need: Dict, video: bool = False) -> str:
    """The fused score+caption prompt for one beat — focused on the CULL job (usable? junk?), and it
    returns a caption so it REPLACES the caption call rather than adding a second VLM round-trip.
    `video`: the image is a 3-frame filmstrip of a clip → judge the whole clip."""
    q = need.get("query", "")
    aim = ("This beat is EVOCATIVE (an abstract idea/mood, not a literal thing): judge whether the image "
           "works as a MOOD or METAPHOR for it — not whether it literally depicts it."
           if need.get("evocative") else
           "This beat is CONCRETE: judge whether the image clearly, literally depicts the subject.")
    subject = ("This image is a 3-frame FILMSTRIP (start · middle · end) of a VIDEO clip — judge the CLIP as a "
               "whole: is it consistently on-topic + usable as b-roll? (an early black frame or an end logo alone "
               "is fine; a wrong subject across the strip is not)."
               if video else "Judge this single image.")
    return (f'BEAT: "{q}"\n{aim}\n{subject} Reply STRICT JSON: {{'
            '"usable": <0-10, how well a professional editor could actually cut this image under the beat; '
            "an off-topic subject scores low>, "
            '"usable": <0-10, how well a professional editor could actually cut this image under the beat; '
            "an off-topic subject scores low>, "
            '"flags": "<any of: watermark / overlaid text / stock-photo graphic / logo; '
            "OR a short off-topic note e.g. 'a sports car, not a permit'; empty if clean>\", "
            '"caption": "<=24 words: concrete subject, setting, mood, dominant palette, and photoreal-or-illustration>", '
            '"why": "<=12 words>"}')


def extract_json(text: str) -> Dict:
    """Best-effort JSON out of a VLM reply (handles ```json fences / prose around the object)."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}


def parse_verdict(j: Optional[Dict]) -> Dict:
    """Normalise the VLM JSON into {usable, flags, caption, why}. A missing/garbled verdict yields a
    NEUTRAL result (usable=None) so the caller KEEPS the asset — a dead VLM must never empty the pool."""
    if not isinstance(j, dict):
        return {"usable": None, "flags": "", "caption": "", "why": ""}
    try:
        usable = None if j.get("usable") is None else max(0.0, min(10.0, float(j.get("usable"))))
    except (TypeError, ValueError):
        usable = None
    return {"usable": usable,
            "flags": str(j.get("flags") or "").strip(),
            "caption": str(j.get("caption") or "").strip().replace("\n", " "),
            "why": str(j.get("why") or "").strip()}


def is_junk(verdict: Dict, floor: float = 4.0) -> bool:
    """Floor decision: flagged-as-unusable OR below the usability floor. A NEUTRAL verdict (VLM
    unavailable, usable=None) is NOT junk — fall back to the cheap CLIP/fitness gates that already ran."""
    flags = (verdict.get("flags") or "").lower()
    if any(w in flags for w in UNUSABLE_FLAGS):
        return True
    u = verdict.get("usable")
    return u is not None and u < floor
