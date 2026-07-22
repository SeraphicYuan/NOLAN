"""Shared SFX curation core — add / remove a sound in the curated bank.

Extracted from the `nolan sfx` CLI so the CLI, the /sfx webUI route, and the source-adapter registry
(nolan.sound.sources) all drive ONE implementation: fetch → license-gate → normalize to 48 kHz stereo
(mix-safe) → dedup-record in sfx.json + flag it in the catalog. No printing here — returns structured
results and a `notes` list; callers format. Loud on rejection (raises CurateError; never a silent skip).
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

_MANIFEST = "sfx.json"


class CurateError(RuntimeError):
    """A sound was rejected (bad license, silent file, or normalize failure)."""


def _load_manifest(lib: Path) -> List[Dict[str, Any]]:
    p = lib / _MANIFEST
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def add_sound(sound_id, kind: str, *, rating: int = 3, tags: str = "",
              desc: str = "", no_trim: bool = False) -> Dict[str, Any]:
    """Fetch Freesound SOUND_ID, gate its license, normalize to 48 kHz stereo, and curate it into the
    bank under a registry cue-`kind`. Returns {file, kind, duration, rating, title, attribution, notes}.
    Raises CurateError on any rejection (unknown kind, bad license, silent file, normalize failure)."""
    from nolan import asset_gate
    from nolan.sound import probe
    from nolan.sound.crawl import fetch_sound, library_dir
    from nolan.sound.registry import KINDS
    from nolan.sfx_search import FreesoundProvider, _get, _slug

    if kind not in KINDS:                                      # validated FIRST — fails before any network call
        raise CurateError(f"unknown cue-kind {kind!r} (registry: {sorted(KINDS)})")

    notes: List[str] = []
    meta = fetch_sound(str(sound_id))
    attribution = f'"{meta["name"]}" by {meta["username"]} — {meta["license"]} (Freesound)'
    record = {"source": "freesound", "license": meta["license"], "attribution": attribution}

    verdict = asset_gate.check_sound(record, source="freesound")   # the audio door
    if not verdict.ok:
        raise CurateError(f"license gate rejected {sound_id}: {'; '.join(verdict.reasons)}")
    notes += list(verdict.flags)

    lib = library_dir()
    lib.mkdir(parents=True, exist_ok=True)
    fname = f"freesound-{_slug(meta['name'] or kind)[:40]}-{sound_id}.wav"
    dest = lib / fname
    headers = FreesoundProvider().download_headers()
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
        tf.write(_get(meta["preview_hq_mp3"], headers=headers))
        tmp = tf.name
    try:
        pre = probe.analyze_silence(tmp)
        if pre["is_silent"]:
            raise CurateError(f"{sound_id}: file is silent")
        r = subprocess.run(probe.normalize_cmd(tmp, str(dest), trim_lead=not no_trim),
                           capture_output=True, text=True)
    finally:
        Path(tmp).unlink(missing_ok=True)
    if r.returncode != 0 or not dest.exists():
        raise CurateError(f"normalize failed: {(r.stderr or '')[:300]}")

    post = probe.analyze_silence(dest)                         # verify the onset is now ~0
    if pre["lead_silence_s"] >= 0.05:
        notes.append(f"lead silence {pre['lead_silence_s']:.2f}s "
                     + (f"trimmed → onset {post['lead_silence_s']:.2f}s" if not no_trim else "KEPT (--no-trim)"))
    if not no_trim and post["lead_silence_s"] >= 0.05:
        notes.append(f"⚠ onset still {post['lead_silence_s']:.2f}s after trim — check the source attack")

    manifest = [e for e in _load_manifest(lib)                # dedup by source+id
                if not (e.get("source") == "freesound" and str(e.get("id")) == str(sound_id))]
    entry = {
        "source": "freesound", "provider": "freesound", "id": str(sound_id),
        "file": fname, "kind": kind, "title": meta["name"],
        "description": desc or meta["description"],
        "tags": sorted(set(meta["tags"] + [t.strip() for t in tags.split(",") if t.strip()])),
        "duration": post["duration"], "rating": int(rating),
        "lead_silence_s": pre["lead_silence_s"], "onset_s": post["lead_silence_s"],
        "trimmed": not no_trim, "num_downloads": meta["num_downloads"],
        "license": meta["license"], "attribution": attribution,
        "page_url": meta["page_url"], "curated": True,
    }
    manifest.append(entry)
    (lib / _MANIFEST).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    from nolan.sound.catalog import SoundCatalog                # flag it in the catalog (upsert first so an
    cat = SoundCatalog()                                        # un-crawled id is catalogued too)
    try:
        cat.upsert_many([meta])
        cat.mark_in_library(str(sound_id), kind, fname, int(rating), lead_silence_s=pre["lead_silence_s"])
    finally:
        cat.close()

    return {"file": fname, "kind": kind, "duration": post["duration"], "rating": int(rating),
            "title": meta["name"], "attribution": attribution, "notes": notes}


def remove_sound(sound_id) -> Dict[str, Any]:
    """Remove a curated sound (wav file + sfx.json entry + catalog in-library flag). Returns
    {removed, id, file}. removed=False (not an error) when the id isn't in the bank."""
    from nolan.sound.crawl import library_dir

    lib = library_dir()
    manifest = _load_manifest(lib)
    removed = [e for e in manifest if str(e.get("id")) == str(sound_id)]
    if not removed:
        return {"removed": False, "id": str(sound_id)}
    for e in removed:
        f = lib / e.get("file", "")
        if f.exists():
            f.unlink()
    keep = [e for e in manifest if str(e.get("id")) != str(sound_id)]
    (lib / _MANIFEST).write_text(json.dumps(keep, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    from nolan.sound.catalog import SoundCatalog
    cat = SoundCatalog()
    try:
        cat.unmark(str(sound_id))
    finally:
        cat.close()
    return {"removed": True, "id": str(sound_id), "file": removed[0].get("file")}
