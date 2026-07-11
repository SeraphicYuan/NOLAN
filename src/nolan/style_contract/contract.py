"""The Style Contract — the declarative editorial spec that dual-compiles to (a) the author's brief
and (b) the deterministic linter. One source of truth, so guidance and grading can never drift.

Generic engine: reads the dimension registry in `dimensions.py`. Humans pick a PRESET and nudge a
few DIALS; they never hand-write per-video numbers. To change what's judged, edit `dimensions.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from .dimensions import (ADVISORY, DEFAULT_PRESET, DIAL_ALIASES, DIMENSIONS, GATES, LEVELS,
                         PRESETS, PRINCIPLES, Dimension)


def fmt_target(dim: Dimension, tgt: Tuple[Optional[float], Optional[float]]) -> str:
    lo, hi = tgt
    def f(v):
        return f"{round(v * 100)}%" if dim.pct else f"{v:g}"
    if lo is not None and hi is not None:
        return f"{f(lo)}–{f(hi)}"
    if lo is not None:
        return f"≥ {f(lo)}"
    if hi is not None:
        return f"≤ {f(hi)}"
    return "any"


@dataclass
class StyleContract:
    preset: str
    targets: Dict[str, Tuple[Optional[float], Optional[float]]]   # gate key -> (lo, hi)
    dials: Dict[str, object] = field(default_factory=dict)

    @classmethod
    def resolve(cls, preset: str = DEFAULT_PRESET, **dials) -> "StyleContract":
        if preset not in PRESETS:
            raise ValueError(f"unknown preset {preset!r}; options: {sorted(PRESETS)}")
        targets = {d.key: d.target for d in GATES}
        targets.update(PRESETS[preset])                    # preset overrides the gate defaults
        applied = {}
        for name, val in dials.items():
            key = DIAL_ALIASES.get(name, name)
            if key not in targets:
                raise ValueError(f"unknown dial {name!r}; gated dims: {sorted(targets)}, aliases: {sorted(DIAL_ALIASES)}")
            if isinstance(val, (tuple, list)) and len(val) == 2:
                targets[key] = (val[0], val[1])
            elif isinstance(val, str) and key in LEVELS and val in LEVELS[key]:
                targets[key] = LEVELS[key][val]
            else:
                raise ValueError(f"bad value for dial {name!r}: {val!r} — expected a level "
                                 f"{sorted(LEVELS.get(key, {}))} or an (lo,hi) pair")
            applied[name] = val
        return cls(preset, targets, applied)

    def target(self, key: str):
        return self.targets.get(key)

    def compile_brief(self) -> str:
        """The agent-facing half — the same gate targets the linter enforces, plus advisory guidance."""
        head = f'STYLE CONTRACT — preset "{self.preset}"'
        if self.dials:
            head += " (dials: " + ", ".join(f"{k}={v}" for k, v in self.dials.items()) + ")"
        lines = [head, "MUST HIT (the linter gates these — draft → lint → revise the failing ones):"]
        for d in GATES:
            lines.append(f"- {d.label} — target {fmt_target(d, self.targets[d.key])}: {d.rubric}.")
        lines.append("ALSO WATCH (tracked, not gated):")
        for d in ADVISORY:
            lines.append(f"- {d.label}: {d.rubric}.")
        lines.append(f"Principles: {PRINCIPLES}")
        return "\n".join(lines)
