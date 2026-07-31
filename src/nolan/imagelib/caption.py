"""The structured caption — the ONE thing a vision model is allowed to produce.

Everything else has a cheaper, more authoritative source: the catalog knows the title, artist,
date, medium and classification; the collection knows the rights; `nolan.imagelib.artists` knows
the movement and style; `nolan.pixels` measures every number. What is left — and it is
genuinely valuable — is **what the picture actually depicts**. Measured on the validation
sample: **93.2% of caption tokens appear nowhere in the catalog record** (minimum 79%). Row 47's
catalog says "Trumpet Player, hard-paste porcelain"; the caption says *a small porcelain figurine
of a monkey dressed in colourful human clothing playing a golden trumpet*. Nothing in the catalog
tells you it is a monkey.

## The schema is v1 because v0 was measured and half of it died

50 rows sampled round-robin across image KINDS (coins, textiles, vessels, sculpture, furniture,
prints, drawings, miniatures, arms, a daguerreotype) rather than the corpus's natural 60%-painting
skew. All 20 proposed fields, one call each. 50/50 returned valid JSON. Then the same 50 measured
with deterministic CV, plus a synthetic-watermark pass. What died:

| field | why |
|---|---|
| `focal_zone` | returned the centre cell on **50/50**. Constant fields carry no information. |
| `has_border` | agreed with pixel measurement **16/50** — worse than chance — and said "no border" on ten rows with >=15% dead margin. It was answering a different question (decorative borders *inside* the art). |
| `open_zones` | 7 distinct answers for 50 images; 38 were one of two templates. A template, not an observation. |
| `named_content` | **0/50 populated.** Row 01 *is* Frederick Douglass and it said "Black man" — correctly refusing to name, which means the field can never fire. |
| `weather` `vantage` `time_of_day` | 82% / 82% / 78% constant, and `time_of_day` self-flagged uncertain 43/50. |
| `frame_or_mount` `subject_bleed` | called a frameless oil sketch "painted-frame" and a full-bleed textile "object-on-backdrop". CV measures both exactly. |

The rule that survived, and that this module exists to enforce:

    **The model NAMES. A detector LOCALISES. Nothing numeric is ever asked of a model.**

## Two rules about what a caption may contain

**Observations, never policies.** No `usable_as`, no "good for a backdrop". Re-captioning 60k
rows is the expensive operation; if a policy is baked into the caption, changing your mind about
it costs a re-caption. Derive policy at read time and it is free to change.

**A caption is never an identity.** It lands in `caption_json` and `description`;
`identity_source` is untouched. A model naming an artwork is a hallucination that becomes a
factual error on screen — the Alamy/named-work lesson.

`caption_schema` is a version integer, and it is not decoration: it is what lets a v2 re-caption
target only the stale rows across a corpus too large to redo wholesale.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger(__name__)

CAPTION_SCHEMA = 1

# Closed vocabularies. Anything outside them is normalised to the fallback and COUNTED, never
# silently kept — exact-string matching on an open vocabulary is checklist class 3.
HUMAN_PRESENCE = ("none", "one", "few", "crowd")
PANEL_COUNT = ("single", "pair", "multi-panel", "grid")
TEXT_IN_IMAGE = ("none", "depicted", "overlay-caption", "overlay-watermark")
CONDITION = ("clean", "foxing", "craquelure", "faded", "damaged")

# The registry: every field, its consumer, and why it survived. A field with no consumer is the
# repo's most-repeated bug, so the consumer is recorded beside the field rather than in a doc
# that can drift away from it.
CAPTION_FIELDS: Dict[str, Dict[str, str]] = {
    "summary": {
        "type": "str", "consumer": "description + BGE description channel",
        "purpose": "one sentence, <=25 words, plain visual description — the embedded backbone"},
    "subjects": {
        "type": "list[str]", "consumer": "BGE description channel; retrieval filter",
        "purpose": "3-8 noun phrases ranked by prominence"},
    "action": {
        "type": "str", "consumer": "BGE description channel",
        "purpose": "short phrase or 'static' — 'figures hauling a net'"},
    "human_presence": {
        "type": "enum", "consumer": "retrieval filter",
        "purpose": "none/one/few/crowd — 'a lone figure' vs 'a crowd' is a real b-roll distinction"},
    "panel_count": {
        "type": "enum", "consumer": "compose/crop safety",
        "purpose": "single/pair/multi-panel/grid — NEW in v1: every coin in the sample was TWO "
                   "coins (obverse and reverse side by side), 5/50, plus a triptych and a "
                   "multi-compartment altarpiece. Cropping or panning those is meaningless."},
    "text_in_image": {
        "type": "enum", "consumer": "asset_gate; hyperframes/cleanup",
        "purpose": "none/depicted/overlay-caption/overlay-watermark. The v0 taxonomy conflated "
                   "lettering that is PART OF THE OBJECT with text stamped on afterwards, so a "
                   "coin's inscribed Latin scored the same as a caption strip. Split, it "
                   "correctly called van Dyck's signature 'depicted' and a Getty bar "
                   "'overlay-watermark' on the same image."},
    "condition": {
        "type": "enum", "consumer": "editorial selection",
        "purpose": "clean/foxing/craquelure/faded/damaged — pristine vs distressed is a choice"},
    "mood": {
        "type": "str", "consumer": "theme matching",
        "purpose": "2-3 adjectives"},
    "palette_words": {
        "type": "str", "consumer": "theme matching",
        "purpose": "'ochre and slate' — the words an author would write. Hex comes from CV."},
    "uncertain": {
        "type": "list[str]", "consumer": "this module's own field audit",
        "purpose": "fields the model could not judge. Earned its place: it flagged time_of_day "
                   "43 times in 50 and told us to cut the field. A per-field confidence NUMBER "
                   "from a VLM is worse than useless; a list of 'I could not tell' is actionable."},
}

PROMPT = """Describe what is DEPICTED in this image.

{context}
Return STRICT JSON, no prose, with exactly these keys:

{{
  "summary": "one sentence, at most 25 words, plain visual description",
  "subjects": ["3-8 noun phrases, most prominent first"],
  "action": "short phrase, or \\"static\\"",
  "human_presence": "none | one | few | crowd",
  "panel_count": "single | pair | multi-panel | grid",
  "text_in_image": "none | depicted | overlay-caption | overlay-watermark",
  "condition": "clean | foxing | craquelure | faded | damaged",
  "mood": "2-3 adjectives",
  "palette_words": "colour words an editor would write, e.g. \\"ochre and slate\\"",
  "uncertain": ["names of any fields above you could not judge"]
}}

Rules that matter:
- Describe ONLY what you can see. Do NOT name the artwork, the artist, the date or the
  institution — those are already known from the catalog, and guessing them is an error.
- "panel_count": a coin photographed showing both faces is "pair"; a triptych or a sheet of
  several images is "multi-panel" or "grid". Most artworks are "single".
- "text_in_image": lettering that is PART of the object (an inscription, a signature, a title
  printed on a poster) is "depicted". Only text stamped on top afterwards is an overlay —
  "overlay-watermark" for a stock/agency mark, "overlay-caption" for an added caption bar.
- Put a field name in "uncertain" instead of guessing at it."""


def build_context(*, collection: Optional[str] = None, artist: Optional[str] = None,
                  kind: Optional[str] = None) -> str:
    """Context makes captions materially better — the same trick that makes video-frame captions
    entity-aware by feeding them the transcript window.

    Deliberately does NOT include the title. Handing the model the answer invites it to describe
    the title rather than the picture, and the title is exactly what we do not need from it.
    """
    bits = []
    if collection:
        bits.append(f"This image is from: {collection.strip()}")
    if artist:
        bits.append(f"Its maker: {artist.strip()}")
    if kind:
        bits.append(f"The catalog classifies it as: {kind}")
    return ("\n".join(bits) + "\n") if bits else ""


def _one_of(value: Any, allowed, fallback: str) -> str:
    s = str(value or "").strip().lower().replace("_", "-")
    return s if s in allowed else fallback


def _flat_str(value: Any) -> str:
    """Accept a string OR a list for the free-text fields.

    Found by LOOKING at live output rather than by reasoning: asked for "2-3 adjectives", the
    same model returned `"quiet, rustic, simple"` for one image and `["historical", "austere"]`
    for the next. Coercing with `str()` would have written the literal `['historical',
    'austere']` — brackets, quotes and all — into `description`, which is the text BGE embeds.
    """
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip()


def _str_list(value: Any, cap: int = 12) -> List[str]:
    if isinstance(value, str):
        value = [v.strip() for v in value.split(",")]
    if not isinstance(value, list):
        return []
    out = []
    for v in value:
        s = str(v or "").strip()
        if s and s.lower() not in {"null", "none", "n/a"}:
            out.append(s)
    return out[:cap]


def parse_caption(raw: str) -> Optional[Dict[str, Any]]:
    """Parse and NORMALISE a model reply into the v1 schema, or None if it is not usable.

    Normalising rather than trusting is the point: the enums are closed vocabularies, and a value
    outside one is coerced to the safe default instead of being written through to a consumer
    that will silently never match it.
    """
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text.strip("`")
        if text.lower().startswith("json"):
            text = text.split("\n", 1)[-1]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    summary = _flat_str(data.get("summary"))
    if not summary:
        return None                     # a caption with no summary is not a caption

    return {
        "summary": summary,
        "subjects": _str_list(data.get("subjects"), cap=8),
        "action": _flat_str(data.get("action")) or "static",
        "human_presence": _one_of(data.get("human_presence"), HUMAN_PRESENCE, "none"),
        "panel_count": _one_of(data.get("panel_count"), PANEL_COUNT, "single"),
        "text_in_image": _one_of(data.get("text_in_image"), TEXT_IN_IMAGE, "none"),
        "condition": _one_of(data.get("condition"), CONDITION, "clean"),
        "mood": _flat_str(data.get("mood")),
        "palette_words": _flat_str(data.get("palette_words")),
        "uncertain": _str_list(data.get("uncertain"), cap=12),
        "schema": CAPTION_SCHEMA,
    }


def caption_text(cap: Dict[str, Any]) -> str:
    """The embeddable sentence. `description` keeps holding this, so the BGE channel the
    retrieval eval was measured through keeps working unchanged."""
    if not cap:
        return ""
    bits = [cap.get("summary", "")]
    if cap.get("subjects"):
        bits.append(", ".join(cap["subjects"]))
    for k in ("action", "mood", "palette_words"):
        v = (cap.get(k) or "").strip()
        if v and v != "static":
            bits.append(v)
    return ". ".join(b for b in bits if b)


def is_watermarked(cap: Optional[Dict[str, Any]]) -> bool:
    """A RIGHTS signal, not merely a pixel problem — the taxonomy split is what makes this
    answerable at all (a coin's inscribed Latin must not read as a watermark)."""
    return bool(cap) and cap.get("text_in_image") == "overlay-watermark"
