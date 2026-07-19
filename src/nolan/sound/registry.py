"""Sound umbrella registry — the vocabulary of SFX cue-kinds.

Each entry is a *kind* of cue (not an individual file): purpose + when_to_use
(the authoring trigger) + the family/timing/gain defaults the curated files
inherit. The curated bank (projects/_library/sfx/sfx.json) binds each sound
FILE to one of these `id`s via a `kind` field; the SFX pairing operator reads
scene events off the spec, maps them to a `kind` here (the `when_to_use`
rulebook), and the mix executor resolves `kind -> best-rated file`.

Legality gate for THIS umbrella (the sound analogue of editing's
duration_preserving): sound is *additive over the finished mix* — every cue is
duration_preserving=True by construction (it never alters video timing and must
never touch the pre-concat clips). The real gates are (a) it ducks under / lands
in the gaps of narration, and (b) it MEASURES audible (audio_mix.measure_sfx_
audibility) — see docs/WIRING_CHECKLIST.md pitfall #6.

Shared authored shape (both fields validate against KINDS below):
  standard pipeline  scene.sfx      : str(query) | {cue|query, at, gain|volume} | list
  HyperFrames spec   scene.data.sfx : [{cue, at, gain}]  (at = scene-LOCAL seconds)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

# Cue families — how a file behaves in the mix.
FAMILIES = ("transition", "one-shot", "loop", "bed")


@dataclass(frozen=True)
class SoundCue:
    id: str
    purpose: str                 # what it does (one line)
    when_to_use: str             # the authoring TRIGGER — the pairing rulebook
    family: str                  # one of FAMILIES
    dur_s: float                 # typical file length (seconds)
    gain: float                  # default mix gain 0..1 (curated file may override)
    authored_by: str             # which field carries the decision
    params: Dict[str, str] = field(default_factory=dict)   # name -> doc
    duration_preserving: bool = True   # sound is additive → always True
    executor: str = "nolan.audio_mix._source_scene_sfx"
    aka: str = ""                # alias in the legacy audio_mix vocab, if any


# The authored per-cue params are shared by nearly every kind:
_AT = "at: scene-local seconds to fire (number), or 'start'|'end' (default 'start')"
_GAIN = "gain: mix level 0..1 (overrides the kind default)"
_COMMON = {"at": _AT, "gain": _GAIN}


REGISTRY: List[SoundCue] = [
    # ── Motion & tension ─────────────────────────────────────────────────────
    SoundCue(
        "whoosh", family="transition", dur_s=0.4, gain=0.30,
        purpose="A short swish that sells motion across a cut / slide-in / camera move.",
        when_to_use="Fire on a scene ENTER or a hard frame transition. Pre-roll ~0.4s "
                    "so the sweep peaks ON the cut, not after it. The workhorse cue — "
                    "but one family per video; don't whoosh every internal beat.",
        authored_by="scene.sfx / scene.data.sfx (cue='whoosh')", params=_COMMON,
        aka="whoosh (audio_mix.ensure_whoosh)"),
    SoundCue(
        "riser", family="one-shot", dur_s=2.0, gain=0.25,
        purpose="A rising swell that builds tension into a reveal or reversal.",
        when_to_use="Lead INTO the turn/'Wrong.' beat or a major reveal; the swell "
                    "must END on the beat (author `at` = the reveal minus the riser "
                    "length). Sparingly — it's a promise; pay it off with an impact.",
        authored_by="scene.sfx / scene.data.sfx (cue='riser')", params=_COMMON,
        aka="riser (audio_mix.ensure_riser)"),

    # ── Impact & punctuation ─────────────────────────────────────────────────
    SoundCue(
        "impact-soft", family="one-shot", dur_s=0.3, gain=0.30,
        purpose="A gentle thud when a word or element lands.",
        when_to_use="On a statement's operative-word reveal (scene.data.cue) or a "
                    "2-4 word beat-sentence. Lands in the VO gap, never over a clause.",
        authored_by="scene.sfx / scene.data.sfx (cue='impact-soft')", params=_COMMON),
    SoundCue(
        "impact-hard", family="one-shot", dur_s=0.6, gain=0.40,
        purpose="A cinematic hit for a major reveal or detonation.",
        when_to_use="The section climax, the myth-bust 'Wrong.', the biggest number. "
                    "At most a few per video — overuse cheapens every one.",
        authored_by="scene.sfx / scene.data.sfx (cue='impact-hard')", params=_COMMON),
    SoundCue(
        "sub-drop", family="one-shot", dur_s=0.8, gain=0.40,
        purpose="A deep sub-bass drop for weight and dread.",
        when_to_use="A dark/heavy beat (dark theme polarity — e.g. 'the future is "
                    "broke'). Pairs well under a room-tone bed; keep it rare.",
        authored_by="scene.sfx / scene.data.sfx (cue='sub-drop')", params=_COMMON),
    SoundCue(
        "stinger", family="one-shot", dur_s=0.5, gain=0.30,
        purpose="A short tonal accent marking a boundary or title.",
        when_to_use="A chapter/frame boundary or a title card — an audible section "
                    "break. Optional; skip if the whoosh already carries the cut.",
        authored_by="scene.sfx / scene.data.sfx (cue='stinger')", params=_COMMON),

    # ── Digital / UI (on-screen mechanisms) ──────────────────────────────────
    SoundCue(
        "click", family="one-shot", dur_s=0.15, gain=0.25,
        purpose="A UI click / tick / select.",
        when_to_use="A button, checkbox, cursor, or list item appearing/selected. "
                    "Great to articulate staccato list reveals one item at a time.",
        authored_by="scene.sfx / scene.data.sfx (cue='click')", params=_COMMON),
    SoundCue(
        "type", family="loop", dur_s=1.0, gain=0.22,
        purpose="Keyboard typing / typewriter clatter.",
        when_to_use="A code block or a typewriter/char-reveal text animation — "
                    "loop under the reveal window, stop when the text settles.",
        authored_by="scene.sfx / scene.data.sfx (cue='type')", params=_COMMON),
    SoundCue(
        "notification", family="one-shot", dur_s=0.5, gain=0.28,
        purpose="A message/alert pop or ding.",
        when_to_use="A social_card, chat bubble, phone, or alert appearing. Match the "
                    "platform feel; don't stack multiples in one beat.",
        authored_by="scene.sfx / scene.data.sfx (cue='notification')", params=_COMMON),
    SoundCue(
        "error-buzz", family="one-shot", dur_s=0.5, gain=0.30,
        purpose="A negative buzzer / denial tone.",
        when_to_use="A failure, a 'no', a red-X, a rejected/void moment. Ironic-beat "
                    "friendly ('approve, approve — denied').",
        authored_by="scene.sfx / scene.data.sfx (cue='error-buzz')", params=_COMMON),
    SoundCue(
        "glitch", family="one-shot", dur_s=0.4, gain=0.30,
        purpose="Digital corruption / distortion artifact.",
        when_to_use="A decode/scramble/glitch reveal style, or an AI/tech/corruption "
                    "motif. Reinforces a digital-unease register; keep it purposeful.",
        authored_by="scene.sfx / scene.data.sfx (cue='glitch')", params=_COMMON),

    # ── Foley / object (diegetic — the most tasteful use) ────────────────────
    SoundCue(
        "camera-shutter", family="one-shot", dur_s=0.3, gain=0.28,
        purpose="A camera shutter snap.",
        when_to_use="A photo / headshot / evidence image sliding in (newshead photo). "
                    "One snap per image; don't machine-gun a gallery.",
        authored_by="scene.sfx / scene.data.sfx (cue='camera-shutter')", params=_COMMON),
    SoundCue(
        "paper", family="one-shot", dur_s=0.5, gain=0.25,
        purpose="Page-turn / paper slide / rustle.",
        when_to_use="A document, newspaper, receipt, or newshead headline landing. "
                    "The signature foley for 'the story broke' / filing beats.",
        authored_by="scene.sfx / scene.data.sfx (cue='paper')", params=_COMMON),
    SoundCue(
        "stamp", family="one-shot", dur_s=0.4, gain=0.32,
        purpose="A stamp / gavel thud.",
        when_to_use="Approval, a verdict, 'sealed', a label slammed on (a villain-"
                    "concept label, an APPROVED/DENIED mark).",
        authored_by="scene.sfx / scene.data.sfx (cue='stamp')", params=_COMMON),
    SoundCue(
        "cash", family="one-shot", dur_s=0.6, gain=0.30,
        purpose="Coin / cash-register / ka-ching.",
        when_to_use="A money stat, a dollar figure, a transaction. Land it ON the "
                    "number, not the sentence around it.",
        authored_by="scene.sfx / scene.data.sfx (cue='cash')", params=_COMMON),

    # ── Data sonification (stat-heavy essays) ────────────────────────────────
    SoundCue(
        "data-tick", family="loop", dur_s=0.05, gain=0.18,
        purpose="A per-increment tick during a number count-up.",
        when_to_use="A stat block counting from A→B — one tick per increment across "
                    "the count window, resolving into a data-punch on the final value.",
        authored_by="scene.sfx / scene.data.sfx (cue='data-tick')", params=_COMMON),
    SoundCue(
        "data-punch", family="one-shot", dur_s=0.3, gain=0.30,
        purpose="A soft impact when a stat / bar / chart lands.",
        when_to_use="The instant a number, bar, or chart settles on a driving beat. "
                    "Already auto-authored by audio_mix for stat/chart treatments.",
        authored_by="scene.sfx / scene.data.sfx (cue='data-punch')", params=_COMMON,
        aka="hit (audio_mix.ensure_hit / _data_punch_events)"),

    # ── Ambience beds (loopable, low, ducked — use sparingly) ────────────────
    SoundCue(
        "room-tone", family="bed", dur_s=8.0, gain=0.10,
        purpose="A low interior bed to fill dead air and set place.",
        when_to_use="A long hold / talking-head-ish stretch (see nolan.hyperframes."
                    "relieve) so silence doesn't feel broken; or to place an interior "
                    "(office, room). Always ducks under VO.",
        authored_by="scene.sfx / scene.data.sfx (cue='room-tone')", params=_COMMON),
    SoundCue(
        "crowd-murmur", family="bed", dur_s=8.0, gain=0.12,
        purpose="A muffled crowd / voices bed.",
        when_to_use="A public / market / courtroom / hype context. Low and wide, "
                    "under the read; never intelligible enough to distract.",
        authored_by="scene.sfx / scene.data.sfx (cue='crowd-murmur')", params=_COMMON),
    SoundCue(
        "tension-drone", family="bed", dur_s=8.0, gain=0.10,
        purpose="A low, sustained suspense drone.",
        when_to_use="Under a dread / slow-build stretch where room-tone reads too "
                    "neutral — abstract and electronic, not a place. Pairs with a "
                    "sub-drop on the peak; pull it out the moment the tension breaks.",
        authored_by="scene.sfx / scene.data.sfx (cue='tension-drone')", params=_COMMON),
    SoundCue(
        "nature-bed", family="bed", dur_s=8.0, gain=0.12,
        purpose="An outdoor natural ambience that sets place and mood.",
        when_to_use="When the narration/visual evokes an outdoor setting or a "
                    "natural-force metaphor. Pick the ambience by intent: rain="
                    "melancholy, sea=vast/calm, fire=tension/warmth, wind=desolation, "
                    "birds=dawn/pastoral, storm=dread. (A thunderclap is an "
                    "impact-hard; the rolling storm is this bed.)",
        authored_by="scene.sfx / scene.data.sfx (cue='nature-bed')", params=_COMMON),
    SoundCue(
        "machine-hum", family="bed", dur_s=8.0, gain=0.10,
        purpose="A mechanical / electronic environment hum.",
        when_to_use="A server room, data center, engine, or factory setting — the "
                    "industrial underlayer (apt for data-center / infrastructure "
                    "beats). Low and constant under the read.",
        authored_by="scene.sfx / scene.data.sfx (cue='machine-hum')", params=_COMMON),
]

BY_ID: Dict[str, SoundCue] = {c.id: c for c in REGISTRY}
KINDS = tuple(c.id for c in REGISTRY)   # THE closed vocabulary — consumers import this


# --- validation (the deterministic gate for authored sound fields) -------------

def _validate_cue_list(sid: str, cues: Any, where: str) -> List[str]:
    """Validate a scene's sfx cue value: str(query) | dict | list-of-those.

    Loud where the executor is lenient: audio_mix._scene_sfx_cues silently
    accepts any shape; this names a bad `cue`, `at`, or `gain` at authoring time.
    A free-text `query` (no `cue`) stays legal for backward compatibility — the
    resolver falls back to a live search — but a `cue` MUST be a known KIND.
    """
    problems: List[str] = []
    items = cues if isinstance(cues, list) else [cues]
    for i, it in enumerate(items):
        tag = f"{sid}: {where}[{i}]"
        if isinstance(it, str):
            continue  # a bare query string is allowed
        if not isinstance(it, dict):
            problems.append(f"{tag} must be a string or an object, got "
                            f"{type(it).__name__}")
            continue
        cue, query = it.get("cue"), it.get("query")
        if cue is None and not query:
            problems.append(f"{tag} needs a `cue` (a known kind) or a `query`")
        if cue is not None and cue not in BY_ID:
            problems.append(f"{tag} cue {cue!r} not a known kind "
                            f"(see nolan.sound.KINDS)")
        at = it.get("at")
        if at is not None and not (isinstance(at, (int, float))
                                   or at in ("start", "end")):
            problems.append(f"{tag} `at` must be a number or 'start'|'end'")
        for gk in ("gain", "volume"):
            g = it.get(gk)
            if g is not None and not (isinstance(g, (int, float)) and 0.0 <= g <= 1.0):
                problems.append(f"{tag} `{gk}` must be a number in 0..1")
    return problems


def validate_scene_sound(scene: Dict[str, Any]) -> List[str]:
    """Structural problems with a scene's authored sound cues (both field shapes)."""
    problems: List[str] = []
    sid = scene.get("id", "?")
    if scene.get("sfx") is not None:                       # standard pipeline
        problems.extend(_validate_cue_list(sid, scene["sfx"], "sfx"))
    data = scene.get("data")                               # HyperFrames spec
    if isinstance(data, dict) and data.get("sfx") is not None:
        problems.extend(_validate_cue_list(sid, data["sfx"], "data.sfx"))
    return problems


def validate_plan_sound(plan: Dict[str, Any]) -> List[str]:
    """validate_scene_sound over every scene of a raw plan dict."""
    problems: List[str] = []
    for scenes in (plan.get("sections") or {}).values():
        if isinstance(scenes, list):
            for s in scenes:
                if isinstance(s, dict):
                    problems.extend(validate_scene_sound(s))
    return problems
