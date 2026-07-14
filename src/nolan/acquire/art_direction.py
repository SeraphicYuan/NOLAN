"""Art direction for GENERATED b-roll — a shared visual BRIEF (look book) + per-shot prompt composition.

A video essay's generated grounds must feel AUTHORED: one medium, one reference, one era across every
shot, each composed for overlaid text + a slow camera move — not eight independently-improvised images.

Division of labour (the key insight): the Fooocus/krea2 STYLE tag is a curated prompt suffix that already
owns MOOD / LIGHTING / PALETTE / QUALITY, applied identically to every image. So the brief does NOT respecify
those — it owns the parts the style can't express and that otherwise VARY per shot:
  • the STYLE CHOICE itself (one place, not a parallel lever),
  • the MEDIUM (one consistent medium — oil painting vs archival photo vs sculpture),
  • a rendering REFERENCE (painter / film-stock / era anchor — the strongest consistency lever), + ERA.
The composer then assembles each prompt DETERMINISTICALLY from the shared brief + a subject the LLM writes
(disambiguated for concrete beats, a visual metaphor for evocative ones) + layout/motion composition rules.

Modular by construction: the brief SCHEMA is the contract; every value is DERIVED from theme + subject
(nothing hardcoded to one essay). The brief persists as a first-class, inspectable, HUMAN-EDITABLE artifact
(`<project>/visual_brief.json`) — an art director can edit it and re-run.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# Composed for the PLATE: these generated stills become full-bleed grounds under big overlaid text (kicker
# top-left, title/operative lower-left) and get a slow Ken-Burns push. So compose with room for both. This is
# the compose-first HF layout's default; a per-block layout override can replace it (layout_hint) later.
# TERSE image-descriptors only — NOT prose, and NEVER mention "title/text/caption/overlay": describing a
# place for text in a T2I prompt makes the model PAINT text there (the homer 'somewhere to go' leak). This
# still yields the plate the layout needs — subject off to one side, a calm empty area where the title will
# later sit, plus headroom for the Ken-Burns push.
DEFAULT_COMPOSITION = ("wide 16:9 framing, subject positioned off-centre toward the right, a large calm area "
                       "of empty space at the lower left, generous headroom above, cinematic depth of field")

# Model failure-modes every generated essay-still should avoid (negative prompt). Text-rendering is the big
# one for these grounds (they carry overlaid type), so name every flavour of it.
GENERIC_NEGATIVES = ["text", "words", "letters", "title", "caption", "heading", "label", "subtitle",
                     "typography", "lettering", "poster text", "watermark", "signature", "logo",
                     "cartoon", "anime", "low quality", "blurry", "deformed", "extra limbs"]


@dataclass
class VisualBrief:
    """The essay-level look book. Derived once; every generated prompt inherits it verbatim so the set
    coheres. Human-editable (persisted to visual_brief.json)."""
    style: str = "Cinematic"          # the Fooocus/krea2 style tag — OWNS mood/lighting/palette/quality
    medium: str = ""                  # ONE consistent medium, e.g. "neoclassical oil painting"
    reference: str = ""               # consistency anchor, e.g. "in the manner of a museum archival plate"
    era: str = ""                     # e.g. "classical antiquity"
    realism: str = ""                 # "painterly" | "photoreal" | "illustrative"
    texture: str = ""                 # optional finish, e.g. "aged, cracked, grainy film"
    negatives: List[str] = field(default_factory=list)  # subject/era-specific things to avoid

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "VisualBrief":
        f = {k: d.get(k) for k in cls.__dataclass_fields__ if k in d}
        f["negatives"] = [str(x) for x in (d.get("negatives") or [])]
        return cls(**{k: v for k, v in f.items() if v is not None})


def _parse_json(raw: str) -> dict:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    i, j = raw.find("{"), raw.rfind("}")
    if 0 <= i < j:
        try:
            return json.loads(raw[i:j + 1])
        except Exception:
            return {}
    return {}


async def derive_brief(cfg, *, subject: str, theme: str, style_default: str, llm=None) -> VisualBrief:
    """Define the essay's look ONCE. The LLM sets only what the style preset can't (medium/reference/era/
    realism/negatives); `style` is carried from the theme-derived default (one decision, one place). A dead
    LLM yields a minimal brief (style only) so generation still runs."""
    if llm is None:
        from nolan.llm import create_text_llm
        llm = create_text_llm(cfg)
    system = ("You are the ART DIRECTOR for a video essay. Given the subject + visual theme, define a SINGLE "
              "coherent look that EVERY generated image will share so the set feels authored (one film). A separate "
              "style preset already handles mood, lighting, palette and quality — do NOT specify those. Define only "
              "what the preset can't and what must stay CONSISTENT across shots: MEDIUM (one medium that fits the "
              "subject + theme and won't fight the preset — e.g. 'neoclassical oil painting', '35mm archival "
              "photograph', 'weathered marble sculpture'), a rendering REFERENCE phrased as a TECHNIQUE or MOVEMENT "
              "for consistency — NOT a bare artist name a model would render as a SIGNATURE (write 'in the engraving "
              "manner of 19th-century illustrated epics', not just 'Gustave Doré'), the ERA, the realism level, and "
              "3-6 NEGATIVE terms specific to this subject/era. TWO HARD RULES: (1) the medium must SUIT THE "
              "SUBJECT'S OWN ERA — a CONTEMPORARY subject (technology, modern events, present-day people) needs a "
              "contemporary medium (documentary / editorial photography, or modern illustration), NEVER an "
              "anachronistic period style (do not render modern AI data-centres as a 1930s woodcut). (2) the NEGATIVE "
              "terms must NOT exclude the essay's OWN subject matter — never negate the very things the essay is "
              "about. Return ONLY JSON: {\"medium\":\"\",\"reference\""
              ":\"\",\"era\":\"\",\"realism\":\"\",\"texture\":\"\",\"negatives\":[]}.")
    user = f"Subject / essay: {subject}\nVisual theme: {theme}\nStyle preset (mood, fixed): {style_default}"
    try:
        data = _parse_json(await llm.generate(user, system_prompt=system))
    except Exception:
        data = {}
    return VisualBrief(style=style_default, medium=str(data.get("medium", "")).strip(),
                       reference=str(data.get("reference", "")).strip(), era=str(data.get("era", "")).strip(),
                       realism=str(data.get("realism", "")).strip(), texture=str(data.get("texture", "")).strip(),
                       negatives=[str(x).strip() for x in (data.get("negatives") or []) if str(x).strip()])


_CONCRETE_SYS = ("You describe the SUBJECT of one image for a video essay, precisely and UNAMBIGUOUSLY. Depict "
                 "EXACTLY the given subject — if it names a specific person (e.g. the scholar Milman Parry), depict "
                 "THAT person; NEVER substitute a different, more famous entity from the essay. Disambiguate to "
                 "avoid wrong-entity collisions (e.g. 'Homer' = the blind ancient-Greek poet, NOT the cartoon). Give "
                 "ONLY the subject and its immediate setting — no medium, no style, no lighting (set elsewhere). One line.")
_EVOCATIVE_SYS = ("The subject is an ABSTRACT idea for a video essay. Do NOT illustrate it literally — give ONE "
                  "resonant, filmable visual METAPHOR that evokes it (e.g. 'the fingerprint of a crowd' -> a "
                  "thousand raised hands, or one face dissolving into many). A single concrete image. Give ONLY "
                  "the subject/scene — no medium, no style, no lighting. One line.")


async def compose_prompt(cfg, need: dict, brief: VisualBrief, *, essay_context: str = "",
                         layout_hint: str = "", llm=None) -> Tuple[str, str]:
    """Assemble one image's (positive, negative). The LLM writes only the SUBJECT — disambiguated for a
    concrete need, a visual metaphor for an evocative one — and the brief's medium/reference/era + the
    composition rules are wrapped DETERMINISTICALLY, so the medium/reference stay identical across shots
    (the coherence lock the style tag can't provide). Falls back to the raw prompt if the LLM is down."""
    if llm is None:
        from nolan.llm import create_text_llm
        llm = create_text_llm(cfg)
    raw = (need.get("gen_prompt") or need.get("query") or "").strip()
    system = _EVOCATIVE_SYS if need.get("evocative") else _CONCRETE_SYS
    subject = raw
    try:
        out = (await llm.generate(f"Subject: {raw}\nEssay: {essay_context or 'a video essay'}",
                                  system_prompt=system)).strip().strip('"').strip()
        if out:
            subject = out
    except Exception:
        pass
    import re as _re
    era = _re.sub(r"\([^)]*\)", "", brief.era).strip()      # drop parenthetical years — they render as text labels
    parts = [brief.medium, subject, layout_hint or DEFAULT_COMPOSITION, brief.reference, era, brief.texture]
    positive = ", ".join(p.strip() for p in parts if p and p.strip())[:600]
    negatives = list(dict.fromkeys([*GENERIC_NEGATIVES, *brief.negatives]))
    return positive, ", ".join(negatives)


def load_or_none(project: Path) -> Optional[VisualBrief]:
    """Reuse a persisted/hand-edited brief if present (idempotent + human-override)."""
    p = Path(project) / "visual_brief.json"
    if p.exists():
        try:
            return VisualBrief.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            return None
    return None


def save(project: Path, brief: VisualBrief) -> Path:
    p = Path(project) / "visual_brief.json"
    p.write_text(json.dumps(brief.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return p
