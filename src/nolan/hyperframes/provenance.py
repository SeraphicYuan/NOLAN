"""Where every frame came from — the report, at the last gate before publish.

Measured on the-diamond-illusion-v3 the day this was written:

    91 assets on screen · 67 in pool.json · 24 never recorded at all
    2 scraped sources with no VLM origin check
    every `quick-edit` derivative with no link back to its original

So the honest state was not "clean", it was **unknown**: at the moment of publishing we could not say
where 24 on-screen assets came from, and no derivation chain existed at all.

A note on how this report was nearly born useless: the first version read `edit.asset_pool_meta`,
which is a narrow projection for the edit UI and drops `license` / `source_url` / `derived_from`. It
duly reported 65 of 91 assets as NO-LICENCE when `pool.json` held a Pexels licence and a source URL
for every one of them. Read `edit.pool_entries` (the raw rows) for anything provenance-shaped.

This REPORTS; it does not gate. A hard gate would have blocked every publish on day one and been
disabled within a week — `docs/WIRING_CHECKLIST.md` #11, a check whose failures are all false
positives takes its one true positive with it. The order is: record derivations at the source
(`edit._register_pool_asset(derived_from=…)`), shrink the unknown set, measure, and gate only once
the false-positive rate is near zero.

`UNKNOWN` is deliberately its own bucket, distinct from `unverified`. One means "we never recorded
this", the other means "we looked and the VLM could not confirm it". Collapsing them would let the
first hide inside the second.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .edit import _comp_dir, asset_scene_usage, pool_entries, pool_original

# Sources whose ORIGIN is unverified until the pixels are checked — a scraped upload's branding is
# invisible to every cheap gate. Mirrors `nolan.acquire.judge.is_scraped`; imported when available so
# the two cannot drift.
try:                                                       # pragma: no cover - trivial import guard
    from nolan.acquire.judge import is_scraped
except Exception:                                          # pragma: no cover
    def is_scraped(source: str) -> bool:
        return any(k in (source or "").lower() for k in ("youtube", "archive", "ddgs", "transcript"))


def audit(comp: str) -> Dict[str, Any]:
    """Every asset ON SCREEN, with what we know about where it came from."""
    meta = pool_entries(comp)          # the RAW rows — the UI projection drops license/source_url
    usage = asset_scene_usage(comp).get("by_file") or {}
    rows: List[Dict[str, Any]] = []
    for name in sorted(usage):
        e = meta.get(Path(name).name) or {}
        known = bool(e)
        src = e.get("source") or ""
        row = {
            "file": name,
            "scenes": sorted(usage[name]),
            "in_pool": known,
            "source": src or None,
            "license": e.get("license") or None,
            "source_url": e.get("source_url") or None,
            "photographer": e.get("photographer") or None,
            "derived_from": e.get("derived_from"),
            "original": pool_original(comp, name),
            "op": e.get("op"),
            "origin_verified": e.get("origin_verified"),
            "caption_verified": e.get("caption_verified"),
        }
        if not known:
            row["status"] = "UNKNOWN"            # never recorded — not the same as "checked and unsure"
        elif e.get("origin_verified") is False:
            row["status"] = "UNVERIFIED-ORIGIN"
        elif is_scraped(src) and e.get("origin_verified") is None:
            row["status"] = "UNCHECKED"          # a scraped source nobody has looked at
        elif not (e.get("license") or e.get("source_url")):
            row["status"] = "NO-LICENCE"
        else:
            row["status"] = "OK"
        rows.append(row)
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    derived = [r for r in rows if r["derived_from"]]
    return {"comp": comp, "rows": rows,
            "summary": {"on_screen": len(rows), "in_pool": sum(1 for r in rows if r["in_pool"]),
                        "derived": len(derived),
                        "derived_traced": sum(1 for r in derived if r["original"]),
                        "by_status": counts,
                        "clean": counts.get("OK", 0) == len(rows) and bool(rows)}}


def render_markdown(rep: Dict[str, Any]) -> str:
    s = rep["summary"]
    L = [f"# Asset provenance — `{rep['comp']}`", "",
         f"{s['on_screen']} asset(s) on screen · {s['in_pool']} in `pool.json` · "
         f"{s['derived_traced']}/{s['derived']} derivatives traced to an original", "",
         "| status | count |", "|---|---|"]
    for k in sorted(s["by_status"], key=lambda k: -s["by_status"][k]):
        L.append(f"| {k} | {s['by_status'][k]} |")
    L += ["", "**UNKNOWN** = never recorded in the pool (we cannot say where it came from). "
              "**UNCHECKED** = a scraped source no VLM pass has confirmed. These are different "
              "problems and are counted separately on purpose.", ""]
    bad = [r for r in rep["rows"] if r["status"] != "OK"]
    if bad:
        L += ["## Needs attention", "", "| file | status | scenes | source |", "|---|---|---|---|"]
        for r in bad:
            L.append(f"| `{r['file']}` | {r['status']} | {', '.join(r['scenes'][:3])} | "
                     f"{r['source'] or '—'} |")
        L.append("")
    L += ["## Full inventory", "", "| file | source | licence | derived from | scenes |", "|---|---|---|---|---|"]
    for r in rep["rows"]:
        L.append(f"| `{r['file']}` | {r['source'] or '—'} | {r['license'] or '—'} | "
                 f"{r['original'] or r['derived_from'] or '—'} | {len(r['scenes'])} |")
    return "\n".join(L) + "\n"


def write_report(comp: str, out: Path = None) -> Path:
    rep = audit(comp)
    out = Path(out) if out else (_comp_dir(comp) / "package" / "PROVENANCE.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(rep), encoding="utf-8")
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="nolan.hyperframes.provenance",
                                 description="Where every on-screen asset came from.")
    ap.add_argument("comp")
    ap.add_argument("--write", action="store_true", help="write package/PROVENANCE.md")
    a = ap.parse_args()
    rep = audit(a.comp)
    s = rep["summary"]
    print(f"{s['on_screen']} on screen · {s['in_pool']} in pool · "
          f"{s['derived_traced']}/{s['derived']} derivatives traced")
    for k in sorted(s["by_status"], key=lambda k: -s["by_status"][k]):
        print(f"  {k:18s} {s['by_status'][k]}")
    if a.write:
        print(f"wrote {write_report(a.comp)}")


if __name__ == "__main__":
    main()
