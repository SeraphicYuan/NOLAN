"""THE TWEAK SURFACE.

Everything you'd adjust to change how essays are judged lives in this one file: which dimensions
exist, whether each is a hard GATE (pass/fail) or ADVISORY (reported only), its target range, and
its rubric. The engine (metrics.py measures, contract.py compiles, linter.py scores) reads this
registry generically — you never touch logic to add, drop, retune, or promote a dimension.

Design stance (deliberately lean): measure generously, gate sparingly. Five gates — the ones that
matched the eye and the render — everything else advisory until it proves it earns a gate. Targets
are starting points, not gospel; tune them here or reference-derive them.
"""
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class Dimension:
    key: str
    label: str
    metric: str                                   # which measure() output this reads
    mode: str                                     # "gate" (pass/fail) | "advisory" (reported only)
    target: Tuple[Optional[float], Optional[float]] = (None, None)   # (lo, hi); used only for gates
    rubric: str = ""
    pct: bool = False                             # format the value/target as a percentage


# ─────────────────────────── the registry — edit here ───────────────────────────
DIMENSIONS = [
    # ---- 4 GATES ----
    Dimension("coverage", "Evidence coverage", "coverage", "gate", (0.45, 0.95),
              "share of scenes visually grounded — open every section on an asset; earn text-only beats", True),
    Dimension("video_share", "Motion footage", "video_share", "gate", (0.08, 0.7),
              "share of scenes on real video — route pool clips through ground_motion / comparison video sides", True),
    Dimension("layout_max_share", "Block concentration", "layout_max_share", "gate", (None, 0.5),
              "max share of any single block — no one template should dominate", True),
    Dimension("layout_max_run", "Adjacent repeats", "layout_max_run", "gate", (None, 3),
              "longest run of the same block back-to-back — break up monotony"),
    # ---- ADVISORY (measured + reported, never fails; promote to a gate when it earns one) ----
    Dimension("pacing_cv", "Pacing variance", "pacing_cv", "advisory",
              rubric="scene-length variation — a DESCRIPTOR of the narration's own rhythm once durations come "
                     "from forced alignment (P0.1), not something the author forces (gating it amplified drift)"),
    Dimension("grounded_openers", "Grounded openers", "grounded_openers", "advisory",
              rubric="fraction of sections that open on an asset rather than a text card", pct=True),
    Dimension("cuts_per_min", "Cut rate", "cuts_per_min", "advisory",
              rubric="scenes per minute — pacing feel"),
    Dimension("dataviz_share", "Data-viz share", "dataviz_share", "advisory",
              rubric="chart what a sentence can't say better (Tufte), not everything", pct=True),
    Dimension("tone_max_run", "Tone rhythm", "tone_max_run", "advisory",
              rubric="longest run of the same light/dark register — alternate tone for cadence"),
    Dimension("overstuffed_stats", "Over-stuffed stats", "overstuffed_stats", "advisory",
              rubric="stat scenes carrying >3 numbers should escalate to a chart"),
    Dimension("long_holds", "Long ungrounded holds", "long_holds", "advisory",
              rubric="ungrounded scenes held >8s read like a static slide — split the beat or give it a moving ground"),
    Dimension("distinct_blocks", "Palette coverage", "distinct_blocks", "advisory",
              rubric="how many DISTINCT blocks used — reach past statement/stat/comparison into the tail"),
    Dimension("media_diversity", "Media diversity", "media_diversity", "advisory", pct=True,
              rubric="distinct assets ÷ grounded scenes — low means the same image is reused across beats"),
    Dimension("max_asset_reuse", "Max asset reuse", "max_asset_reuse", "advisory",
              rubric="most scenes any single asset appears in — >3 is the 'one photo everywhere' smell"),
]

GATES = [d for d in DIMENSIONS if d.mode == "gate"]
ADVISORY = [d for d in DIMENSIONS if d.mode == "advisory"]
BY_KEY: Dict[str, Dimension] = {d.key: d for d in DIMENSIONS}

# human-friendly dial names → dimension key
DIAL_ALIASES = {"asset_density": "coverage", "evidence_coverage": "coverage",
                "video": "video_share", "motion": "video_share"}

# named levels for the dial-able gates (density is a RANGE, never "maximize")
LEVELS: Dict[str, Dict[str, Tuple[float, float]]] = {
    "coverage": {"sparse": (0.2, 0.55), "balanced": (0.45, 0.8), "dense": (0.6, 0.95)},
    "video_share": {"none": (0.0, 1.0), "light": (0.05, 0.35), "heavy": (0.3, 0.85)},
}

# presets = named target-override maps over the gate defaults. One for now; add when earned.
PRESETS: Dict[str, Dict[str, Tuple[Optional[float], Optional[float]]]] = {"essay": {}}
DEFAULT_PRESET = "essay"

PRINCIPLES = ("Density is not monotonic — earn your sparse beats. Variety within a system — a motif "
              "plus enough variance, not chaos. Chart only what a sentence can't say better. "
              "Gates are starting points — tune them here or reference-derive them.")
