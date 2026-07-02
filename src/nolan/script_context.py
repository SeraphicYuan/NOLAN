"""ScriptContext — the whole-script context object shared by the rhythm/tempo pass,
the knowledge-driven asset-query bridge, and (later) motion selection.

Every asset/motion/tempo decision in NOLAN today is made from ONE line in isolation. That is
the root cause of generic queries, anachronistic picks, and flat pacing. This module assembles,
ONCE per project, the context those decisions actually need:

  - the full script (`script.md`)           — the narration + beat order + timecodes
  - the pacing plan (`beatmap.md`)           — per-beat `pace:a|d|a→d`, source coverage, spine
  - the grounded facts (`facts.md`)          — per-beat fact clusters
  - the meta (`meta.json`) + spine/angle     — subject, style, target length

It is pipeline-agnostic: it reads the `scriptgen/` workspace (produced by the scriptwriter),
so it works whether the render side is the FLOW or the orchestrator pipeline.

The two prompt helpers — `brief()` (whole-script digest) and `beat_context(i)` (one beat +
its neighbours + arc position) — are what get injected into LLM prompts downstream.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

PROJECTS_ROOT = Path("projects")

# pace tag (beatmap) → normalized energy intent
_PACE_NORM = {"a": "accelerate", "d": "decelerate", "a→d": "accelerate→decelerate",
              "d→a": "decelerate→accelerate", "": ""}

# pace → rough energy 0..1 (a cheap, LLM-free rhythm signal for the pairing/query prompts;
# the render-time TempoPlan computes the full arc-shaped curve — this is just enough context)
_PACE_ENERGY = {"accelerate": 0.78, "decelerate": 0.3, "accelerate→decelerate": 0.6,
                "decelerate→accelerate": 0.5, "": 0.5}


def _rhythm_hint(energy: float) -> str:
    if energy >= 0.62:
        return "DRIVE — fast cuts, punchy/graphic assets, energetic motion; avoid slow lingering shots"
    if energy <= 0.4:
        return "BREATHE — long holds, a single strong evocative/lingering asset, slow motion"
    return "STEADY — moderate pace, balanced asset weight"


def _norm_title(s: str) -> str:
    """Lowercase alnum tokens for fuzzy title matching across the three docs."""
    return " ".join(re.findall(r"[a-z0-9]+", (s or "").lower()))


@dataclass
class ScriptBeat:
    idx: int
    title: str                       # from script.md heading (canonical)
    timecode: str = ""               # "0:55" from script.md
    narration: str = ""              # prose for this beat
    pace: str = ""                   # normalized: accelerate | decelerate | accelerate→decelerate | ""
    pace_raw: str = ""               # the beatmap tag as written ("a", "d", "a→d")
    covers: List[str] = field(default_factory=list)   # source ids ["S1","S4"]
    serves: str = ""                 # beatmap "serves-spine" rationale
    facts: List[str] = field(default_factory=list)    # facts.md lines mapped to this beat

    def one_line(self) -> str:
        p = f" · pace:{self.pace}" if self.pace else ""
        tc = f" [{self.timecode}]" if self.timecode else ""
        return f"[{self.idx}] {self.title}{tc}{p}"


@dataclass
class ScriptContext:
    slug: str
    subject: str = ""
    angle: str = ""                  # the spine (from beatmap header, else meta)
    style_id: str = ""
    target_minutes: float = 0.0
    theme: str = ""                  # optional; caller may override from the plan
    period: str = ""                 # optional; era hint for the anachronism gate
    locale: str = ""                 # optional; culture hint
    script_md: str = ""
    beatmap_md: str = ""
    facts_md: str = ""
    beats: List[ScriptBeat] = field(default_factory=list)

    # ---- loading -------------------------------------------------------------
    @classmethod
    def load(cls, slug_or_dir, *, theme: str = "", period: str = "", locale: str = "") -> "ScriptContext":
        """Load from a project slug or a project directory. Missing artifacts degrade gracefully
        (e.g. no beatmap → beats carry no pace; no facts → empty fact clusters)."""
        pdir = Path(slug_or_dir)
        if not pdir.exists():
            pdir = PROJECTS_ROOT / str(slug_or_dir)
        if not pdir.exists():
            raise FileNotFoundError(f"project not found: {slug_or_dir}")
        sg = pdir / "scriptgen"

        meta = {}
        mp = sg / "meta.json"
        if mp.exists():
            try:
                meta = json.loads(mp.read_text(encoding="utf-8"))
            except Exception:
                meta = {}

        script_md = _read(pdir / "script.md")
        beatmap_md = _read(sg / "beatmap.md")
        facts_md = _read(sg / "facts.md")

        beats = _parse_script_beats(script_md)
        _attach_beatmap(beats, beatmap_md)
        _attach_facts(beats, facts_md)

        angle = (meta.get("chosen_angle") or meta.get("angle") or "").strip()
        if not angle and beatmap_md:
            m = re.search(r"\*\*Angle \(spine\):\*\*\s*(.+)", beatmap_md)
            if m:
                angle = m.group(1).strip()

        return cls(
            slug=str(meta.get("slug") or pdir.name),
            subject=(meta.get("subject") or "").strip(),
            angle=angle,
            style_id=(meta.get("style_id") or "").strip(),
            target_minutes=float(meta.get("target_minutes") or 0.0),
            theme=theme, period=period, locale=locale,
            script_md=script_md, beatmap_md=beatmap_md, facts_md=facts_md, beats=beats,
        )

    # ---- prompt helpers ------------------------------------------------------
    def brief(self, *, max_chars: int = 2600) -> str:
        """A compact whole-script digest for injecting into any downstream LLM prompt:
        subject + spine + the ordered beat list with pace tags. Kept short on purpose."""
        lines = []
        if self.subject:
            lines.append(f"SUBJECT: {self.subject}")
        if self.style_id:
            lines.append(f"STYLE: {self.style_id}")
        if self.angle:
            lines.append(f"SPINE/ANGLE: {self.angle}")
        if self.beats:
            lines.append("BEAT ARC (in order, with the writer's pace intent):")
            for b in self.beats:
                serves = f" — {b.serves}" if b.serves else ""
                lines.append(f"  {b.one_line()}{serves}"[:240])
        out = "\n".join(lines)
        return out[:max_chars]

    def beat_context(self, idx: int, *, neighbors: int = 1) -> str:
        """One beat + its immediate neighbours + where it sits in the arc — for a decision
        (asset query / tempo / motion) that needs to know what comes before and after."""
        if not self.beats:
            return ""
        n = len(self.beats)
        idx = max(0, min(idx, n - 1))
        b = self.beats[idx]
        pos = "opening" if idx == 0 else "closing" if idx == n - 1 else \
              "early" if idx < n / 3 else "late" if idx > 2 * n / 3 else "middle"
        parts = [f"ARC POSITION: beat {idx + 1} of {n} ({pos})"]
        lo, hi = max(0, idx - neighbors), min(n, idx + neighbors + 1)
        for j in range(lo, hi):
            tag = "→ THIS BEAT" if j == idx else "  context"
            nb = self.beats[j]
            parts.append(f"{tag}: {nb.one_line()}")
            if j == idx:
                if nb.serves:
                    parts.append(f"    intent: {nb.serves}")
                # rhythm/tempo signal so operator choice + query generation match the pacing
                energy = _PACE_ENERGY.get(nb.pace, 0.5)
                pace_txt = f"{nb.pace} " if nb.pace else ""
                parts.append(f"    pacing: {pace_txt}energy≈{energy:.2f} → {_rhythm_hint(energy)}")
                if nb.covers:
                    parts.append(f"    sources: {', '.join(nb.covers)}")
                if nb.narration:
                    parts.append(f"    narration: {nb.narration[:400]}")
                if nb.facts:
                    parts.append("    facts: " + " | ".join(f[:120] for f in nb.facts[:4]))
        return "\n".join(parts)

    def find_beat(self, narration_or_title: str) -> Optional[ScriptBeat]:
        """Best-effort map a scene's narration excerpt or title back to a script beat
        (token overlap). Used to look up a beat's pace/context from a plan scene."""
        key = _norm_title(narration_or_title)
        if not key:
            return None
        ktoks = set(key.split())
        best, best_score = None, 0.0
        for b in self.beats:
            btoks = set((_norm_title(b.title) + " " + _norm_title(b.narration[:200])).split())
            if not btoks:
                continue
            score = len(ktoks & btoks) / max(1, len(ktoks))
            if score > best_score:
                best, best_score = b, score
        return best if best_score >= 0.3 else None


# ---- parsers ----------------------------------------------------------------
def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8") if p.exists() else ""
    except Exception:
        return ""


def _parse_script_beats(script_md: str) -> List[ScriptBeat]:
    """script.md: `## <title> [<timecode>]` headings + prose until the next heading."""
    if not script_md:
        return []
    beats: List[ScriptBeat] = []
    # split on level-2 headings, keep the heading text
    parts = re.split(r"(?m)^##\s+(.+?)\s*$", script_md)
    # parts = [preamble, head1, body1, head2, body2, ...]
    for i in range(1, len(parts), 2):
        head = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        tc = ""
        # matches "[0:55]" and range forms "[0:00 - 0:35]" / "[0:00–0:35]"
        m = re.search(r"\[(\d{1,2}:\d{2})(?:\s*[-–—]\s*\d{1,2}:\d{2})?\]", head)
        if m:
            tc = m.group(1)
            head = head[:m.start()].strip(" -—·")
        beats.append(ScriptBeat(idx=len(beats), title=head.strip(), timecode=tc,
                                narration=body.strip()))
    return beats


def _parse_beatmap(beatmap_md: str) -> List[dict]:
    """beatmap.md: `## <title> · pace:<x> · covers:[..] · serves-spine: <..>`."""
    out = []
    if not beatmap_md:
        return out
    for line in beatmap_md.splitlines():
        if not line.startswith("## "):
            continue
        head = line[3:].strip()
        title = re.split(r"\s+·\s+", head)[0].strip()
        pace = ""
        mp = re.search(r"pace:\s*([^\s·]+)", head)
        if mp:
            pace = mp.group(1).strip()
        covers = []
        mc = re.search(r"covers:\s*\[([^\]]*)\]", head)
        if mc:
            covers = [c.strip() for c in mc.group(1).split(",") if c.strip()]
        serves = ""
        ms = re.search(r"serves-spine:\s*(.+)$", head)
        if ms:
            serves = ms.group(1).strip()
        out.append({"title": title, "pace_raw": pace, "covers": covers, "serves": serves})
    return out


def _attach_beatmap(beats: List[ScriptBeat], beatmap_md: str) -> None:
    """Align beatmap entries onto script beats — by title token-overlap, else positionally."""
    bm = _parse_beatmap(beatmap_md)
    if not beats or not bm:
        return
    used = set()
    for b in beats:
        btok = set(_norm_title(b.title).split())
        best_j, best_score = -1, 0.0
        for j, e in enumerate(bm):
            if j in used:
                continue
            etok = set(_norm_title(e["title"]).split())
            if not etok:
                continue
            score = len(btok & etok) / max(1, len(btok | etok))
            if score > best_score:
                best_j, best_score = j, score
        if best_j >= 0 and best_score >= 0.25:
            _apply_beatmap(b, bm[best_j])
            used.add(best_j)
    # positional fallback for any script beat that stayed unmatched (equal counts, order-aligned)
    if len(beats) == len(bm):
        for i, b in enumerate(beats):
            if not b.pace_raw and i not in ():
                if i < len(bm) and i not in used:
                    _apply_beatmap(b, bm[i])
                    used.add(i)


def _apply_beatmap(b: ScriptBeat, e: dict) -> None:
    b.pace_raw = e["pace_raw"]
    b.pace = _PACE_NORM.get(e["pace_raw"], e["pace_raw"])
    b.covers = e["covers"]
    b.serves = e["serves"]


def _attach_facts(beats: List[ScriptBeat], facts_md: str) -> None:
    """facts.md: `## Beat: <NAME>` clusters of `- ` fact lines → mapped onto beats by title."""
    if not beats or not facts_md:
        return
    clusters: Dict[str, List[str]] = {}
    cur = None
    for line in facts_md.splitlines():
        m = re.match(r"^##\s+Beat:\s*(.+?)\s*$", line)
        if m:
            cur = m.group(1).strip()
            # strip a trailing parenthetical gloss "NAME  (blah)"
            cur = re.sub(r"\s*\(.*\)\s*$", "", cur)
            clusters[cur] = []
        elif cur and line.strip().startswith("- "):
            clusters[cur].append(line.strip()[2:].strip())
    if not clusters:
        return
    keys = list(clusters.keys())
    for b in beats:
        btok = set(_norm_title(b.title).split())
        best_k, best_score = None, 0.0
        for k in keys:
            ktok = set(_norm_title(k).split())
            if not ktok:
                continue
            score = len(btok & ktok) / max(1, len(ktok))
            if score > best_score:
                best_k, best_score = k, score
        if best_k and best_score >= 0.3:
            b.facts = clusters[best_k]
