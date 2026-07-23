"""COLLECT — P2 orchestrator: the reviewed proposal → real downloaded + conditioned files + a
canonical `key_assets.json`.

For each entity (hero-first), resolve its top desired assets via the provider search, background-remove
the collage-ready stills, and write everything under `capture/keyassets/` named `{entity_id}_{type}[_cutout]`
so the /keyassets gallery attaches each file to its entity automatically. Best-effort + loud: a miss is
logged, never fatal. VLM identity-verify + the /faceless-explainer HERO wiring are P3.

    python -X utf8 -m nolan.keyassets.collect --project projects/the-diamond-illusion [--limit 4] [--per 2]
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .resolve import build_client, resolve_image, resolve_video
from .schema import KeyAssetsProposal


def _rel(p: Path, root: Path) -> str:
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return p.name


def collect(cfg, project_dir: Path, proposal: KeyAssetsProposal, *, limit: Optional[int] = None,
            per_entity: int = 2, do_cutout: bool = True, verify: bool = True, log: Callable = print) -> dict:
    """Resolve + condition the proposal's assets into capture/keyassets/, write key_assets.json."""
    project_dir = Path(project_dir)
    ka_dir = project_dir / "capture" / "keyassets"
    ka_dir.mkdir(parents=True, exist_ok=True)
    client = build_client(cfg)
    from nolan.cutout import cutout_file

    ents = sorted(proposal.entities, key=lambda e: e.priority != "hero")   # hero-first
    if limit:
        ents = ents[:limit]
    resolved: Dict[str, List[dict]] = {}
    got = 0

    for e in ents:
        recs = resolved.setdefault(e.id, [])
        for d in e.desired_assets[:per_entity]:
            is_video = d.type == "footage"
            stem = f"{e.id}_{d.type}"
            out = ka_dir / (stem + (".mp4" if is_video else ".jpg"))
            tag = "~" if d.relevance == "related" else ""
            log(f"  [{e.name}] {d.type}{tag} …")
            if is_video:
                r = resolve_video(cfg, client, e, d, out)
            else:
                r = resolve_image(cfg, client, e, d, out, verify=verify)
            if not r:
                miss = "no confirmed match" if (verify and d.type in {"portrait", "artwork"}) else "none found"
                log(f"    ✗ {miss}")
                continue
            got += 1
            vmark = "" if not r.get("verified") else " ✓verified"
            recs.append({"file": _rel(out, project_dir), "type": d.type, "variant": "original",
                         "collage_ready": d.collage_ready, "relevance": d.relevance,
                         "verified": bool(r.get("verified")),
                         "source": r.get("source", ""), "source_url": r.get("source_url", ""),
                         "license": r.get("license", ""), "query": r.get("query", "")})
            log(f"    + {out.name}  ({r.get('source', '?')}){vmark}")
            from .registry import CUTOUT_TYPES
            if do_cutout and d.collage_ready and d.type in CUTOUT_TYPES and not is_video:   # meaningful cutouts only
                try:
                    cut = ka_dir / f"{stem}_cutout.png"
                    cutout_file(out, dst=cut, trim=True)
                    if cut.exists():
                        recs.append({"file": _rel(cut, project_dir), "type": d.type, "variant": "cutout",
                                     "collage_ready": True, "relevance": d.relevance,
                                     "processing": ["bg_removed", "trim"], "source": r.get("source", "")})
                        got += 1
                        log(f"    ✂ {cut.name}  (cutout)")
                except Exception as ex:
                    log(f"    cutout failed: {type(ex).__name__}: {ex}")

    _write_manifest(project_dir, proposal, resolved)
    log(f"COLLECTED {got} file(s) → {ka_dir}  ·  key_assets.json written")
    return {"collected": got, "dir": str(ka_dir)}


def _write_manifest(project_dir: Path, proposal: KeyAssetsProposal, resolved: Dict[str, List[dict]]) -> Path:
    """Canonical key_assets.json = the proposal + each entity's `resolved` files (with provenance)."""
    d = proposal.to_dict()
    for ed in d["entities"]:
        ed["resolved"] = resolved.get(ed["id"], [])
    d["collected"] = sum(len(v) for v in resolved.values())
    out = project_dir / "key_assets.json"
    out.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="nolan.keyassets.collect",
                                 description="P2 — resolve + condition the key-assets proposal into files")
    ap.add_argument("--project", required=True, help="project dir holding key_assets.proposal.json")
    ap.add_argument("--limit", type=int, default=None, help="only the first N (hero-first) entities")
    ap.add_argument("--per", type=int, default=2, help="max desired assets resolved per entity (default 2)")
    ap.add_argument("--no-cutout", action="store_true", help="skip background-removal of collage stills")
    ap.add_argument("--no-verify", action="store_true", help="skip VLM identity-verify for portraits/artwork")
    a = ap.parse_args()

    project_dir = Path(a.project)
    prop = KeyAssetsProposal.load(project_dir / "key_assets.proposal.json")
    if prop is None:
        raise SystemExit(f"no key_assets.proposal.json under {project_dir} — run `python -m nolan.keyassets` first")

    from nolan.config import load_config
    collect(load_config(), project_dir, prop, limit=a.limit, per_entity=a.per,
            do_cutout=not a.no_cutout, verify=not a.no_verify)


if __name__ == "__main__":
    main()
