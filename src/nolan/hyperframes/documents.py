"""Pipeline integration for the DOCUMENT source (B-P1/B-P2/B-P3): resolve every document/split_view scene's
binding — `data.document`/`page`/`focus` + annotation `region`/`find` (and split_view's `data.paper`) → the
real page source + page_size + rects + provenance, from the ingested layout map — BEFORE recompose. Runs in
the finish DAG right after word-sync, alongside dataset resolution.

  data.document + page + annotations[].region/focus  →  data.source + page_size + rects + provenance
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BRIDGE = Path(__file__).resolve().parents[3] / "render-service" / "_lab_hyperframes" / "bridge"  # documents→hyperframes→nolan→src→REPO


def _needs_resolve(sc) -> bool:
    t = sc.get("type")
    d = sc.get("data", {}) or {}
    anns = [a for a in d.get("annotations", []) if isinstance(a, dict)]
    if t == "document":
        return bool(d.get("document") or d.get("focus")
                    or any(a.get("region") or a.get("find") for a in anns)
                    or str(d.get("source", "")).lower().endswith(".pdf"))
    if t == "split_view":
        return isinstance(d.get("paper"), dict) and bool(d["paper"].get("document"))
    return False


def resolve_documents(comp) -> int:
    """Resolve document/split_view bindings across a comp's frame specs, writing the resolved source/rects
    back (CRLF-preserving). Returns how many scenes were resolved. No-op if the bridge resolver is absent."""
    if str(_BRIDGE) not in sys.path:
        sys.path.insert(0, str(_BRIDGE))
    try:
        import resolve_doc_annotations as R
    except Exception as e:                                    # bare env without the bridge/PIL — skip, loudly
        print(f"  (document resolution skipped: {type(e).__name__}: {e})")
        return 0
    from nolan.hyperframes.edit import _project_dir
    pdir = Path(_project_dir(comp))
    frames = pdir / "compositions" / "frames"
    total = 0
    for sf in sorted(frames.glob("*.spec.json")):
        raw = sf.read_bytes()
        crlf = b"\r\n" in raw
        spec = json.loads(raw.decode("utf-8"))
        n = 0
        for fr in spec.get("frames", []):
            for sc in fr.get("scenes", []):
                if not _needs_resolve(sc):
                    continue
                d = sc.setdefault("data", {})
                if sc.get("type") == "document":
                    R.resolve_scene(d, pdir)                  # _bind_document (region/focus) + find resolution
                else:                                        # split_view: bind the paper side
                    R._bind_document(d["paper"], pdir)
                n += 1
        if n:
            out = (json.dumps(spec, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            if crlf:
                out = out.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            sf.write_bytes(out)
            total += n
    return total


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="nolan.hyperframes.documents")
    ap.add_argument("comp")
    a = ap.parse_args()
    n = resolve_documents(a.comp)
    print(f"resolved {n} document/split_view scene(s) → page source + region rects + provenance")


if __name__ == "__main__":
    main()
