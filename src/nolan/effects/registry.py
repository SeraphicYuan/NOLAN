"""Effects umbrella — visual TREATMENTS (color grades, grain, film damage, and physical-element
overlays like fire/rain) applied to any media asset, as a declarative registry.

The module-contract home (CLAUDE.md) for asset visual-effects. Each effect is a registry entry
(purpose + when_to_use + constraints), AUTHORED as a STACKABLE `treatments: [...]` list on a scene
ground (and, later, per-block media), VALIDATED here (validate_treatments), and EXECUTED at render
time (HyperFrames CSS filter + blended overlay layers — see nolan.effects.render) or BAKED to a new
file (ffmpeg). Backend-agnostic by design: the same `fire`/`vintage` vocabulary drives the HF compose
executor now and a Remotion executor later, exactly like nolan/motion/registry.py spans backends.
Supersedes the bare compose.GRADES str->str map (kept in parity by tests/test_ground_effect.py).

Two orthogonal axes on every effect:
  - family: what KIND of look — color | grain | stylize | damage | element.
  - method: the render-time mechanism —
      css_filter    : a CSS `filter:` chain on the media layer (color family). Also bakeable (ffmpeg eq).
      blend_overlay : a full-inset layer — procedural CSS (css_bg) OR a library PLATE clip — composited
                      with a mix-blend-mode over the media (grain/stylize/damage/element). Bakeable
                      (ffmpeg overlay/blend).
      ffmpeg_bake   : bake-ONLY (a 3D LUT / effect the browser can't do); produces a new asset file.

INVARIANT (the legality gate for this umbrella, mirroring editing.duration_preserving): every effect
is `duration_preserving` and non-destructive at render time — the baked variant writes a COPY.
Narration owns duration; an effect never changes timing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

FAMILIES = ("color", "grain", "stylize", "damage", "element")
METHODS = ("css_filter", "blend_overlay", "ffmpeg_bake")
# mix-blend-mode values we allow on an overlay layer (a closed vocabulary the executor can trust)
BLEND_MODES = ("screen", "multiply", "overlay", "soft-light", "lighten", "color-dodge", "hard-light", "normal")

# a compact SVG fractal-noise data URI — a static film-grain plate that needs NO download (procedural)
_GRAIN_SVG = ("url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E"
              "%3Cfilter id='g'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' "
              "stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23g)'/%3E"
              "%3C/svg%3E\")")
# CRT/analogue scanlines — a repeating gradient, also procedural
_SCANLINES = "repeating-linear-gradient(0deg, rgba(0,0,0,0.28) 0px, rgba(0,0,0,0.28) 1px, transparent 2px, transparent 4px)"

_COMMON = {"opacity": "0..1 — strength of the effect (overlays only; css_filter ignores it in v1)"}

_FILTER_EXEC = "nolan.effects.render.filter_chain"
_OVERLAY_EXEC = "nolan.effects.render.overlay_layers"
_BAKE_EXEC = "nolan.effects.bake.apply_bake"   # Phase 4 — declared so ffmpeg_bake effects name a real target


@dataclass(frozen=True)
class Effect:
    id: str
    family: str                     # one of FAMILIES
    purpose: str                    # what it does (one line)
    when_to_use: str                # the craft guidance an agent needs to PICK it (vs its neighbours)
    method: str                     # one of METHODS
    css: str = ""                   # css_filter: the CSS `filter:` chain (like the old GRADES values)
    blend: str = ""                 # blend_overlay: the mix-blend-mode (one of BLEND_MODES)
    plate: str = ""                 # blend_overlay(element/damage): overlays.json `effect` tag; "" = procedural
    css_bg: str = ""                # blend_overlay(procedural): CSS `background` for the overlay layer
    lut: str = ""                   # ffmpeg_bake: .cube filename under projects/_library/luts/ (optional/param)
    params: Dict[str, str] = field(default_factory=lambda: dict(_COMMON))
    default_opacity: float = 1.0    # overlay opacity when the treatment doesn't override it
    duration_preserving: bool = True   # ALWAYS true — declared to make the invariant explicit + testable
    backends: tuple = ("hf",)       # render backends that IMPLEMENT it today: hf | remotion | ffmpeg
    executor: str = ""              # where it becomes pixels


def _color(id, purpose, when, css, **kw):
    return Effect(id, "color", purpose, when, "css_filter", css=css,
                  backends=("hf", "ffmpeg"), executor=_FILTER_EXEC, **kw)


def _proc(id, family, purpose, when, css_bg, blend, opac, **kw):
    return Effect(id, family, purpose, when, "blend_overlay", css_bg=css_bg, blend=blend,
                  default_opacity=opac, backends=("hf", "ffmpeg"), executor=_OVERLAY_EXEC, **kw)


def _plate(id, family, purpose, when, plate, blend, opac, **kw):
    return Effect(id, family, purpose, when, "blend_overlay", plate=plate, blend=blend,
                  default_opacity=opac, backends=("hf",), executor=_OVERLAY_EXEC, **kw)


# --- the registry -----------------------------------------------------------
REGISTRY: List[Effect] = [
    # ---- color (css_filter) — the ground.grade family, now first-class + extended ----
    _color("warm", "Warm the image (golden, inviting).",
           "Nostalgia, hearth, human warmth; a cold stock photo that should feel lived-in.",
           "sepia(0.32) saturate(1.18) brightness(1.02)"),
    _color("cool", "Cool the image (blue, clinical, distant).",
           "Detachment, technology, night, unease; warm footage that clashes with a somber beat.",
           "sepia(0.25) hue-rotate(155deg) saturate(1.15)"),
    _color("darken", "Drop the exposure.",
           "Push an over-bright asset back so overlaid text reads; night/foreboding register.",
           "brightness(0.68)"),
    _color("brighten", "Lift the exposure.",
           "Rescue an underexposed asset; airy/optimistic register.", "brightness(1.2)"),
    _color("contrast", "Punch the contrast.",
           "A flat, hazy image that needs snap; bold/graphic register.", "contrast(1.28)"),
    _color("desaturate", "Pull most of the colour out.",
           "Archival/serious tone without full B&W; unify a clashing palette.", "saturate(0.42)"),
    _color("mute", "Gently lower saturation + a touch darker.",
           "Take the edge off a garish stock image so it recedes behind text.",
           "saturate(0.72) brightness(0.95)"),
    _color("noir", "Full black-and-white with punch.",
           "Historical, funereal, or stark-editorial register; strip colour entirely.",
           "grayscale(1) contrast(1.2)"),
    _color("sepia", "Antique sepia-toned photograph.",
           "Old-photo / archival-document look; pairs into the `old-film` preset.",
           "sepia(0.68) contrast(1.04) brightness(1.02)"),
    _color("faded", "Washed, low-contrast matte fade.",
           "Faded-memory / bleached-film register; softens a harsh modern photo.",
           "contrast(0.82) brightness(1.08) saturate(0.82)"),
    _color("vivid", "Saturated, punchy pop.",
           "Energetic/upbeat register; make a dull product shot vibrant.",
           "saturate(1.35) contrast(1.08)"),

    # ---- grain (procedural blend_overlay — no download) ----
    _proc("film-grain", "grain", "Fine static film grain over the media.",
          "Kill the digital-clean 'AI look'; give a flat gen image analogue texture. Subtle by default.",
          _GRAIN_SVG, "overlay", 0.16),
    _proc("heavy-grain", "grain", "Coarse, heavy grain.",
          "Degraded / lo-fi / found-footage register; pairs into `old-film` and `super8`.",
          _GRAIN_SVG, "overlay", 0.34),

    # ---- stylize (procedural blend_overlay — no download) ----
    _proc("scanlines", "stylize", "CRT / analogue scanline overlay.",
          "Retro-tech, surveillance-monitor, or VHS register; pairs into the `vhs` preset.",
          _SCANLINES, "multiply", 0.5),

    # ---- damage (library PLATE — Phase 3) ----
    _plate("dust-scratches", "damage", "Film dust, hairs and vertical scratches drifting over the frame.",
           "Aged-celluloid / decaying-archive register; the core of the `old-film` preset.",
           "dust", "screen", 0.55),
    _plate("old-movie", "damage", "Super-8 / old-film frame: warm grain, gate vignette, dust & flicker.",
           "Vintage / archival / nostalgic register — make modern footage read as projected film. MULTIPLY "
           "so the light film gate tints + vignettes the image rather than washing it out.",
           "old-movie", "multiply", 0.8),
    _plate("old-film", "damage", "80s film dust, specks and scratches drifting over the frame.",
           "Retro / analogue-decay register — grittier and more coloured than the clean `dust-scratches`.",
           "old-film", "screen", 0.6),
    _plate("projector", "damage", "Warm film-projector flicker with drifting dust motes and specks.",
           "Cinema / archival-projection register — warmer and sparser than `old-film`.",
           "projector", "screen", 0.6),
    _plate("film-roll-h", "damage", "35mm film strip rolling horizontally — sprocket holes top & bottom, light leaks.",
           "Frame the shot as a strip of running film (letterbox-ish); pairs with sepia/old-movie.",
           "film-roll-h", "screen", 0.9),
    _plate("film-roll-v", "damage", "35mm film strip rolling vertically — sprocket holes left & right, light leaks.",
           "Frame the shot as a vertical filmstrip; portrait/scroll register.", "film-roll-v", "screen", 0.9),

    # ---- particles (library PLATE) ----
    _plate("particles", "element", "Fine dust motes / particles drifting through the frame.",
           "Atmosphere + depth — floating dust in a light beam; softer and cooler than `embers`.",
           "particles", "screen", 0.55),
    _plate("particles-center", "element", "Dust particles bursting from the centre of the frame.",
           "A soft particle burst anchored centre-frame (vs `particles` drifting from a corner).",
           "particles-center", "screen", 0.55),

    # ---- element (library PLATE — Phase 3; the physical-element overlays) ----
    _plate("fire", "element", "Real fire / flame licking up over the media.",
           "Destruction, war, passion, collapse; literal fire behind a subject shot on black.",
           "fire", "screen", 0.9),
    _plate("embers", "element", "Drifting embers / sparks rising.",
           "Aftermath, smouldering tension; subtler than `fire`.", "embers", "screen", 0.85),
    _plate("rain", "element", "Rain falling across the frame.",
           "Melancholy, hardship, film-noir mood over a street or portrait.", "rain", "screen", 0.7),
    _plate("snow", "element", "Falling snow.",
           "Winter, isolation, quiet; a cold beat over a landscape.", "snow", "screen", 0.75),
    _plate("smoke", "element", "Rolling smoke / haze drifting through.",
           "Mystery, war, industry; add atmosphere and depth to a flat plate.", "smoke", "screen", 0.6),
    _plate("light-smoke", "element", "Low, soft haze creeping up from the bottom of the frame.",
           "Subtle atmosphere — a gentle mood wash under a scene; lighter/wispier than `smoke`.",
           "light-smoke", "screen", 0.5),
    _plate("fog", "element", "Low fog / mist.",
           "Dread, dreaminess, the unknown; soften and recede a background.", "fog", "lighten", 0.5),
    _plate("light-leak", "element", "Analogue lens light-leak / flare wash.",
           "Warm organic imperfection between beats; a nostalgic film-camera register.",
           "light-leak", "screen", 0.55),
    _plate("film-burn", "element", "Warm film-burn / light-leak flares blooming in from the edge.",
           "A punchier warm-orange burst than `light-leak` — great as a beat / scene transition.",
           "film-burn", "screen", 0.7),
    _plate("bokeh", "element", "Soft defocused light-orbs drifting across the frame.",
           "Dreamy / romantic / premium register — warm out-of-focus lights; pairs under a title.",
           "bokeh", "screen", 0.65),

    # ---- ffmpeg_bake (bake-ONLY — a 3D LUT the browser can't do; Phase 4) ----
    Effect("film-lut", "color",
           "Apply a cinematic 3D LUT (.cube) the browser CSS filter can't reproduce.",
           "A specific film emulation / colour science (Kodak, teal-orange) beyond css_filter grades. "
           "Bake-only — produces a new derived asset via ffmpeg lut3d.",
           "ffmpeg_bake", lut="", params={**_COMMON, "lut": "filename under projects/_library/luts/ (e.g. kodak-2383.cube)"},
           backends=("ffmpeg",), executor=_BAKE_EXEC),
]

BY_ID: Dict[str, Effect] = {e.id: e for e in REGISTRY}


# ffmpeg `-vf` equivalents of the css_filter/grain LOOKS, for the BAKED per-asset "treat" op
# (nolan.hyperframes.quickedit). Approximations of the CSS filter — the same look, not pixel-identical.
# Element/damage effects bake by compositing their PLATE (screen blend), so they're resolved separately.
FFMPEG_VF: Dict[str, str] = {
    "warm": "colorbalance=rs=.12:gs=.02:bs=-.10,eq=saturation=1.12",
    "cool": "colorbalance=rs=-.10:bs=.14,eq=saturation=1.08",
    "darken": "eq=brightness=-0.16",
    "brighten": "eq=brightness=0.14",
    "contrast": "eq=contrast=1.28",
    "desaturate": "eq=saturation=0.42",
    "mute": "eq=saturation=0.72:brightness=-0.03",
    "noir": "hue=s=0,eq=contrast=1.2",
    "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
    "faded": "eq=contrast=0.82:brightness=0.06:saturation=0.82",
    "vivid": "eq=saturation=1.35:contrast=1.08",
    "film-grain": "noise=alls=10:allf=t",
    "heavy-grain": "noise=alls=26:allf=t",
}


def bakeable(effect: "Effect") -> bool:
    """True if the effect can be BAKED onto an asset file — a -vf colour/grain look, or a plate to
    composite (element/damage). Scanlines etc. have no simple -vf equivalent → render-time only."""
    return effect.id in FFMPEG_VF or bool(effect.plate)


# --- validation (the deterministic gate for authored `treatments`) --------------

def validate_treatments(treatments: Any, *, where: str = "ground") -> List[str]:
    """Structural problems with an authored `treatments` list. Loud where the executor is lenient
    (render.py silently skips an unknown/plate-missing effect so a render never crashes; this NAMES it
    so the author gate can reject it — mirrors editing.validate_scene_editing)."""
    problems: List[str] = []
    if treatments is None:
        return problems
    if not isinstance(treatments, list):
        return [f"{where}.treatments must be a list, got {type(treatments).__name__}"]
    for i, t in enumerate(treatments):
        # a treatment is either a bare effect id (string) or {id, opacity?}
        if isinstance(t, str):
            eid, op = t, None
        elif isinstance(t, dict):
            eid, op = t.get("id"), t.get("opacity")
        else:
            problems.append(f"{where}.treatments[{i}] must be an effect id or {{id, opacity?}}")
            continue
        if not eid or eid not in BY_ID:
            problems.append(f"{where}.treatments[{i}] unknown effect {eid!r} "
                            f"(valid: {', '.join(sorted(BY_ID))})")
            continue
        if op is not None and (not isinstance(op, (int, float)) or not (0.0 <= float(op) <= 1.0)):
            problems.append(f"{where}.treatments[{i}].opacity must be 0..1")
    return problems


def normalize_treatments(treatments: Any) -> List[Dict[str, Any]]:
    """Coerce the authored form (list of ids or {id,opacity?}) into a uniform list of
    {effect, opacity} for the executor. Silently drops malformed/unknown entries (the gate is the
    loud one); resolves each effect's default_opacity when the treatment doesn't override it."""
    out: List[Dict[str, Any]] = []
    if not isinstance(treatments, list):
        return out
    for t in treatments:
        eid = t if isinstance(t, str) else (t.get("id") if isinstance(t, dict) else None)
        eff = BY_ID.get(eid or "")
        if not eff:
            continue
        op = t.get("opacity") if isinstance(t, dict) else None
        try:
            op = float(op) if op is not None else eff.default_opacity
        except (TypeError, ValueError):
            op = eff.default_opacity
        out.append({"effect": eff, "opacity": max(0.0, min(1.0, op))})
    return out


def get_effect(effect_id: str) -> Optional[Effect]:
    return BY_ID.get(effect_id)
