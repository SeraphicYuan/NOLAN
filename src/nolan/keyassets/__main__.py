"""CLI for the Key-Assets Anchored Pool (P1: decompose + consolidate → reviewable pull-list).

    python -X utf8 -m nolan.keyassets --script projects/the-diamond-illusion/scriptgen/drafts/draft-03.md
    python -X utf8 -m nolan.keyassets --comp <hf-slug>            # reads its SOURCE.md, writes into it
    [--out key_assets.proposal.json] [--k 30] [--review]

Writes `<comp|cwd>/key_assets.proposal.json` and prints the pull-list grouped by research direction
(hero-first) for human review before P2 spends any research/download time.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date
from pathlib import Path

from .schema import KeyAssetsProposal


def _load_script(comp: str, script: str) -> tuple:
    """Resolve (script_text, project_dir). --script wins; else --comp's SOURCE.md/SCRIPT.md."""
    if script:
        p = Path(script)
        if not p.exists():
            raise SystemExit(f"script not found: {p}")
        return p.read_text(encoding="utf-8"), p.parent
    if comp:
        try:
            from nolan.hyperframes.edit import _comp_dir
            cdir = _comp_dir(comp)
        except Exception:
            cdir = Path(comp)
        for cand in ("SOURCE.md", "SCRIPT.md", "STORYBOARD.md"):
            f = cdir / cand
            if f.exists():
                return f.read_text(encoding="utf-8"), cdir
        raise SystemExit(f"no SOURCE.md/SCRIPT.md under {cdir}")
    raise SystemExit("need --script <file> or --comp <slug>")


def _print_review(prop: KeyAssetsProposal) -> None:
    by_id = {e.id: e for e in prop.entities}
    n_hero = sum(1 for e in prop.entities if e.priority == "hero")
    print(f"\nKEY-ASSETS PULL-LIST — {len(prop.entities)} entities ({n_hero} hero) in "
          f"{len(prop.directions)} research direction(s)\n" + "=" * 72)
    for d in prop.directions:
        ents = [by_id[i] for i in d.entity_ids if i in by_id]
        ents.sort(key=lambda e: (e.priority != "hero", e.name.lower()))
        print(f"\n▸ {d.title}  [{d.id}]")
        if d.rationale:
            print(f"    ~ {d.rationale}")
        if d.queries:
            print(f"    queries: {d.queries}")
        for e in ents:
            star = "★" if e.priority == "hero" else "·"
            assets = ", ".join(a.type + ("✂" if a.collage_ready else "") + ("~" if a.relevance == "related" else "")
                               + (f'({a.note})' if a.note else "") for a in e.desired_assets)
            print(f"    {star} {e.name} ({e.kind}) — {e.narrative_role}")
            print(f"        assets: {assets}")
            if e.mentions:
                print(f"        anchors: {e.mentions}")
    n_clip = sum(1 for e in prop.entities for a in e.desired_assets if a.type == "footage")
    n_related = sum(1 for e in prop.entities for a in e.desired_assets if a.relevance == "related")
    print("\n" + "=" * 72)
    print(f"{n_clip} footage/clip asset(s), {n_related} directionally-related (~)")
    print("legend: ★=hero · ✂=collage cutout (bg-removed) · ~=related (not exact) · anchors=spoken phrases")


def main() -> None:
    ap = argparse.ArgumentParser(prog="nolan.keyassets",
                                 description="Key-Assets Anchored Pool — P1 decompose + consolidate")
    ap.add_argument("--comp", help="HF composition slug (reads its SOURCE.md; writes proposal into it)")
    ap.add_argument("--script", help="script file to decompose (overrides --comp)")
    ap.add_argument("--out", help="proposal path (default: <comp|script-dir>/key_assets.proposal.json)")
    ap.add_argument("--k", type=int, default=30, help="max hero entities (default 30)")
    ap.add_argument("--no-enrich", action="store_true", help="skip the archival/clip completeness pass")
    ap.add_argument("--review", action="store_true", help="just print the review (still writes the file)")
    a = ap.parse_args()

    script_text, proj_dir = _load_script(a.comp or "", a.script or "")
    out = Path(a.out) if a.out else (proj_dir / "key_assets.proposal.json")

    from nolan.config import load_config
    from nolan.llm import create_text_llm
    from nolan.keyassets import build_proposal

    client = create_text_llm(load_config())
    prop = asyncio.run(build_proposal(script_text, client, comp=(a.comp or proj_dir.name), k=a.k,
                                      enrich_pass=not a.no_enrich))
    prop.generated = date.today().isoformat()
    prop.save(out)
    _print_review(prop)
    print(f"\nproposal → {out}")
    print("review/edit it, then P2 will research + resolve + condition these into key_assets.json")


if __name__ == "__main__":
    main()
