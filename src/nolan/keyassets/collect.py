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


def derive_domain(cfg, project_dir: Path) -> str:
    """The essay's core subject (e.g. 'diamond') from SOURCE.md — woven into ambiguous-name queries +
    verify so 'The Four Cs' searches 'four Cs diamond', not a four-stroke engine. Graceful → '' on failure."""
    text = ""
    for cand in ("SOURCE.md", "SCRIPT.md"):
        f = Path(project_dir) / cand
        if f.exists():
            text = f.read_text(encoding="utf-8")[:1500]
            break
    if not text.strip():
        return ""
    try:
        import asyncio
        from nolan.llm import create_text_llm
        raw = asyncio.run(create_text_llm(cfg).generate(
            text, system_prompt="In ONE or TWO words, name the core subject/domain of this essay "
                                "(e.g. 'diamonds', 'space travel', 'coffee'). Reply ONLY those words."))
        return " ".join((raw or "").strip().strip('".').split()[:2]).lower()
    except Exception:
        return ""


def collect(cfg, project_dir: Path, proposal: KeyAssetsProposal, *, limit: Optional[int] = None,
            per_entity: int = 2, do_cutout: bool = True, verify: bool = True, log: Callable = print) -> dict:
    """Resolve + condition the proposal's assets into capture/keyassets/, write key_assets.json."""
    project_dir = Path(project_dir)
    ka_dir = project_dir / "capture" / "keyassets"
    ka_dir.mkdir(parents=True, exist_ok=True)
    client = build_client(cfg)
    from nolan.cutout import cutout_file

    domain = derive_domain(cfg, project_dir)
    if domain:
        log(f"  domain: {domain!r} — woven into ambiguous-name queries + verify")
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from threading import Lock

    from .registry import CUTOUT_TYPES
    ents = sorted(proposal.entities, key=lambda e: e.priority != "hero")   # hero-first
    if limit:
        ents = ents[:limit]
    resolved: Dict[str, List[dict]] = {}
    cutout_lock = Lock()          # birefnet's ONNX session isn't thread-safe → serialize cutouts

    def _resolve_entity(e):
        """Resolve one entity's assets (thread-safe: unique out paths, no shared mutation). Returns
        (entity_id, records, log_lines) — logs grouped so a completed entity prints together."""
        recs: List[dict] = []
        logs = [f"  [{e.name}]"]
        type_n: Dict[str, int] = {}
        for d in e.desired_assets[:per_entity]:
            is_video = d.type == "footage"
            n = type_n.get(d.type, 0)                          # index same-type assets so they don't overwrite
            type_n[d.type] = n + 1
            stem = f"{e.id}_{d.type}" + (f"_{n}" if n else "")
            out = ka_dir / (stem + (".mp4" if is_video else ".jpg"))
            tag = "~" if d.relevance == "related" else ""
            if is_video:
                results = resolve_video(cfg, client, e, d, out, verify=verify, domain=domain)   # keep up to 2
            else:
                results = resolve_image(cfg, client, e, d, out, verify=verify, domain=domain)    # keep up to 4
            if not results:
                miss = "no confirmed match" if (verify and d.relevance == "exact") else "none found"
                logs.append(f"    ✗ {d.type}{tag}: {miss}")
                continue
            for idx, r in enumerate(results):                  # up to N kept per need — options for the author
                fpath = r["file"]
                primary = idx == 0
                vmark = " ✓verified" if r.get("verified") else ""
                recs.append({"file": _rel(fpath, project_dir), "type": d.type, "variant": "original",
                             "collage_ready": d.collage_ready, "relevance": d.relevance,
                             "verified": bool(r.get("verified")), "selected": primary,   # primary in the pool by default
                             "source": r.get("source", ""), "source_url": r.get("source_url", ""),
                             "license": r.get("license", ""), "query": r.get("query", "")})
                logs.append(f"    + {fpath.name}  ({r.get('source', '?')}){vmark}")
                # cutout only the PRIMARY (idx 0) collage still — alternates stay as raw options
                if primary and do_cutout and d.collage_ready and d.type in CUTOUT_TYPES and not is_video:
                    try:
                        cut = fpath.with_name(f"{fpath.stem}_cutout.png")
                        with cutout_lock:
                            cutout_file(fpath, dst=cut, trim=True)
                        if cut.exists():
                            recs.append({"file": _rel(cut, project_dir), "type": d.type, "variant": "cutout",
                                         "collage_ready": True, "relevance": d.relevance, "selected": True,
                                         "processing": ["bg_removed", "trim"], "source": r.get("source", "")})
                            logs.append(f"    ✂ {cut.name}  (cutout)")
                    except Exception as ex:
                        logs.append(f"    cutout failed: {type(ex).__name__}: {ex}")
        return e.id, recs, logs

    workers = min(10, max(1, len(ents)))                       # 10-way concurrent (I/O-bound: net + VLM waits)
    log(f"  resolving {len(ents)} entities · {workers}-way concurrent")
    got = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in as_completed([pool.submit(_resolve_entity, e) for e in ents]):
            eid, recs, logs = fut.result()
            resolved[eid] = recs
            got += len(recs)
            for line in logs:
                log(line)

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
