"""NOLAN -> HyperFrames asset bridge, Phase 1.5: EXPAND -> COLLECT -> GAP-FILL -> CAPTION -> INVENTORY.

"NOLAN is the camera." Fans out NOLAN's whole acquisition stack and freezes a candidate POOL into
a HyperFrames project's capture/assets/, then vision-captions each with OpenRouter qwen-VL and
writes capture/extracted/asset-descriptions.md — the SAME inventory shape the capture-based
workflows (product-launch / website) already select `asset_candidates` from. So HyperFrames keeps
its own selection judgment; NOLAN just fills (a deep) pool. Three recall/precision layers:

  1. EXPAND  — for `evocative` (abstract) needs, evoke_broll's operator bridge (tonal+conceptual)
               turns the subject into visual METAPHORS and merges them into the need's queries.
  2. COLLECT — multi-query retrieval across N stock providers (image + VIDEO): every phrasing is
               searched, candidates de-duped by source_url, gated (asset_gate, tier=stock) and
               validity-checked, then downloaded up to n per need.
  3. GAP-FILL— any need that stock leaves empty is GENERATED (krea2 / ComfyUI) from its gen_prompt.

  python pool.py --needs needs.json --project <dir> [--per 3] [--no-caption] [--no-expand] [--no-gen]

needs.json: [ { "id","query","queries":[...]?,"media_type":"image|video","sources":[...]?,
                "n":int?, "evocative":bool?, "gen_prompt":str? }, ... ]  (queries/evocative/gen_prompt
optional — a plain {"query"} still works; the bridge falls back to a single literal search.)
"""
import argparse, asyncio, json, os
from pathlib import Path

from nolan.source_registry import HYBRID_PROVIDER_TIERS as _PROVIDER_TIERS


def _client(cfg):
    """Canonical ImageSearchClient (whole provider registry, no hand-maintained subset) — delegates to
    the shared organ so the construction lives in ONE place (was copied 3×)."""
    from nolan.acquire.shared import build_search_client
    return build_search_client(cfg)


def _valid_image(path: Path) -> bool:
    """Reject non-decodable downloads (HTML error pages, truncated files) — shared organ."""
    from nolan.acquire.shared import valid_image
    return valid_image(path)


def _download_video(result, out_path: Path) -> bool:
    import urllib.request
    from nolan.asset_gate import check_candidate
    gate = check_candidate(result, tier="stock")
    if not gate.ok:
        print(f"      video gate-refused: {'; '.join(gate.reasons)}")
        return False
    req = urllib.request.Request(result.url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Referer": "https://www.google.com/"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(out_path, "wb") as f:
            f.write(r.read())
        return out_path.stat().st_size > 10000
    except Exception as e:
        print(f"      video download failed: {type(e).__name__}: {e}")
        return False


def _need_queries(need) -> list:
    """The distinct search phrasings for a need — variants from derive_asset_needs (+ any
    evoke_broll metaphors merged in by expand_needs), falling back to the plain query."""
    seen, out = set(), []
    for q in (need.get("queries") or [need.get("query", "")]):
        q = str(q).strip()
        k = q.lower()
        if q and k not in seen:
            seen.add(k)
            out.append(q)
    return out[:6]


# Curated QUALITY/PRIORITY tiers per content category. A need's `category` (from
# derive_asset_needs) picks the ordering; within source-diversity the provider buckets are
# visited in this order, so the BEST source for that KIND of asset gets first pick. Every
# provider is still queried (full fan-out) — this only ranks the PICK order. Providers not
# listed for a category fall to a default low rank (still included, just later). Names are
# validated against the live registry by tests/test_hf_pool_expand.py (can't go stale silently).
_DEFAULT_CATEGORY = "general"


def _source_rank(category, source):
    """Priority rank of a provider for a content category (lower = preferred). Unlisted providers
    sort after the curated ones but are still kept — the fan-out is never narrowed, only ordered."""
    order = _PROVIDER_TIERS.get(category) or _PROVIDER_TIERS[_DEFAULT_CATEGORY]
    try:
        return order.index(source)
    except ValueError:
        return len(order) + 50


def _diversify_by_source(cands, category=_DEFAULT_CATEGORY):
    """Round-robin candidates across their provider, visiting buckets in CURATED quality order for
    the need's category — so the pool spans sources AND the best source for that KIND of asset
    (artvee/wikicommons for art, archive.org for archival, pexels/pixabay for general stock) gets
    the first pick, instead of whichever provider merged first. Each provider's own relevance order
    is preserved. The gate + qwen-VL caption + compose-first selection stay the quality filter."""
    from collections import OrderedDict
    buckets = OrderedDict()
    for c in cands:
        buckets.setdefault(getattr(c, "source", "?"), []).append(c)
    ordered = OrderedDict(sorted(buckets.items(), key=lambda kv: _source_rank(category, kv[0])))
    out = []
    while any(ordered.values()):
        for lst in ordered.values():
            if lst:
                out.append(lst.pop(0))
    return out


def _gather_candidates(client, mt, queries, sources, want, category=_DEFAULT_CATEGORY):
    """Multi-query retrieval: search every phrasing, DEDUPE by source_url/url, stop once we have
    plenty to pick from, then DIVERSIFY across providers in curated quality order. This is the
    recall win — one phrasing sees one narrow slice of an inconsistently-tagged index; several
    phrasings across every provider surface assets a single query on a single source misses."""
    cands, seen = [], set()
    for q in queries:
        try:
            results = client.search_assets(q, media_type=mt, sources=sources, max_results=want * 3)
        except Exception as e:
            print(f"    search error ({q!r}): {type(e).__name__}: {e}"); continue
        for res in results:
            key = getattr(res, "source_url", None) or getattr(res, "url", None) or id(res)
            if key in seen:
                continue
            seen.add(key); cands.append(res)
        if len(cands) >= want * 4:       # enough of a bench; stop hitting providers (rate limits)
            break
    return _diversify_by_source(cands, category)


def collect(cfg, needs, assets_dir: Path, per: int):
    client = _client(cfg)
    avail = client.get_available_providers()          # honest roster — staleness shows as a missing name
    img = [n for n in avail if getattr(client.providers[n], "media_type", "image") != "video"]
    vid = [n for n in avail if getattr(client.providers[n], "media_type", "image") == "video"]
    print(f"  providers available — image ({len(img)}): {img}")
    print(f"  providers available — video ({len(vid)}): {vid}")
    pool = []
    for need in needs:
        mt = need.get("media_type", "image")
        n = int(need.get("n", per))
        queries = _need_queries(need)
        category = (need.get("category") or _DEFAULT_CATEGORY).lower()
        if category not in _PROVIDER_TIERS:
            category = _DEFAULT_CATEGORY
        tag = (" [evocative]" if need.get("evocative") else "") + f" [{category}]"
        print(f"  [{need['id']}] {mt} search ×{len(queries)}{tag}: {queries!r}")
        cands = _gather_candidates(client, mt, queries, need.get("sources"), n, category)
        got = 0
        for res in cands:
            if got >= n:
                break
            ext = ".mp4" if mt == "video" else ".jpg"
            base = f"{need['id']}_{got:02d}{ext}"
            out = assets_dir / ("videos/" + base if mt == "video" else base)
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                if mt == "video":
                    res = client.resolve_video(res) or res
                    if not res.url:
                        continue
                    ok = _download_video(res, out)
                else:
                    res = client.resolve_asset(res)
                    ok = client.download_image(res, out) is not None
                    if ok and not _valid_image(out):   # cull HTML/truncated downloads
                        out.unlink(missing_ok=True); ok = False
                        print(f"    x {base}: not a decodable image — rejected")
            except Exception as e:
                print(f"    dl error: {type(e).__name__}: {e}"); ok = False
            if ok:
                got += 1
                pool.append({"id": need["id"], "file": ("videos/" + base if mt == "video" else base),
                             "media_type": mt, "query": need["query"],
                             "source": res.source, "source_url": res.source_url,
                             "photographer": res.photographer, "license": res.license,
                             "width": res.width, "height": res.height,
                             "duration": res.duration, "caption": ""})
                print(f"    + {out.name}  ({res.source})")
        print(f"    → {got}/{n} for {need['id']} from {len(cands)} deduped candidate(s)"
              + ("" if got else "  (empty — will gap-fill if enabled)"))
    if pool:                                          # which providers actually contributed (coverage)
        from collections import Counter
        dist = Counter(p.get("source") or "?" for p in pool)
        print(f"  pool source distribution: {dict(dist.most_common())}")
    return pool


async def expand_needs(cfg, needs, max_metaphor: int = 4):
    """SUPER-SEARCH: for `evocative` needs, turn the subject into visual METAPHORS via the same
    operator bridge evoke_broll uses (tonal + conceptual), and merge those phrasings into the
    need's query set. This is what makes abstract narration lines findable — a literal search for
    "freedom" or "decline" returns stock noise; a metaphor ("open road at dawn") returns b-roll.
    Contained: a dead LLM just yields no extra queries."""
    evocative = [nd for nd in needs if nd.get("evocative")]
    if not evocative:
        return
    from nolan.llm import create_text_llm
    from nolan.evoke_broll import bridge_queries
    llm = create_text_llm(cfg)
    for nd in evocative:
        try:
            mets = await bridge_queries(llm, nd["query"], operators=("tonal", "conceptual"),
                                        max_queries=max_metaphor)
        except Exception as e:
            print(f"    metaphor expand failed {nd['id']}: {type(e).__name__}: {e}"); continue
        seen, merged = set(), []
        for q in list(nd.get("queries") or [nd["query"]]) + list(mets):
            q = str(q).strip()
            if q and q.lower() not in seen:
                seen.add(q.lower()); merged.append(q)
        nd["queries"] = merged
        if mets:
            print(f"    [{nd['id']}] +{len(mets)} metaphor quer{'y' if len(mets) == 1 else 'ies'}: {mets!r}")


def _essay_context(project: Path) -> tuple:
    """Best-effort domain context for gen-prompt grounding: the essay's title + opening from SOURCE.md
    (STORYBOARD.md doesn't exist yet at acquisition time) + the chosen theme. Terse; the LLM infers the rest."""
    src = ""
    for cand in ("SOURCE.md", "SCRIPT.md"):
        p = project / cand
        if p.exists():
            src = p.read_text(encoding="utf-8")
            break
    ctx = " ".join(src.split())[:400]
    theme = ""
    try:
        theme = json.loads((project / "hyperframes.json").read_text(encoding="utf-8")).get("theme", "")
    except Exception:
        pass
    return ctx, theme


async def art_direct(cfg, needs, *, essay_context: str = "", theme: str = "", style_default: str = "Cinematic",
                     project=None, llm=None):
    """ART DIRECTION: derive the essay's shared visual BRIEF once (the look book — it OWNS the style and
    locks the MEDIUM / REFERENCE / ERA the style tag can't express, so the generated set feels authored),
    then compose each need's gen prompt against it (a disambiguated subject for concrete beats, a visual
    METAPHOR for evocative ones, wrapped in the brief + composition rules). Persists the brief as a human-
    editable artifact (visual_brief.json); reuses a hand-edited one. Returns the brief — its `.style` IS the
    generation style (one decision, one place). A dead LLM degrades to a minimal brief + raw prompts (contained)."""
    import asyncio as _a
    from nolan.acquire.art_direction import derive_brief, compose_prompt, load_or_none, save
    if llm is None:
        from nolan.llm import create_text_llm
        llm = create_text_llm(cfg)
    proj = Path(project) if project else None
    brief = load_or_none(proj) if proj else None            # reuse a hand-edited / prior brief (idempotent)
    if brief is None:
        brief = await derive_brief(cfg, subject=(essay_context or theme), theme=theme,
                                   style_default=style_default, llm=llm)
        if proj:
            save(proj, brief)
    print(f"    visual brief: style={brief.style} · medium={brief.medium or '—'} · ref={brief.reference or '—'}", flush=True)
    gennable = [nd for nd in needs if (nd.get("gen_prompt") or nd.get("query"))]

    async def _one(nd):
        try:
            pos, neg = await compose_prompt(cfg, nd, brief, essay_context=essay_context, llm=llm)
            if pos:
                nd["gen_prompt"], nd["gen_negative"] = pos, neg
        except Exception as e:
            print(f"    compose failed {nd['id']}: {type(e).__name__}: {e}")

    await _a.gather(*[_one(nd) for nd in gennable])
    if gennable:
        print(f"    composed {len(gennable)} gen prompt(s) against the brief")
    return brief


def _empty_needs(needs, pool):
    """Needs with NO surviving asset in the pool — the gap the VLM cull leaves behind. A need can have
    candidates at retrieval time (so the engine's floor-gated gen never fires) yet be emptied by the
    later score_and_caption cull; those are what post-cull gap-fill must regenerate."""
    have = {p.get("id") for p in pool}
    return [nd for nd in needs if nd.get("id") not in have]


async def gen_fill(cfg, empties, assets_dir: Path, pool, gen_style: str = "Cinematic"):
    """GAP-FILL: when stock returns nothing for a need, GENERATE a still (krea2 / ComfyUI) from the
    need's gen_prompt so the pool is never empty. Contained: no ComfyUI -> logged, need stays empty."""
    if not empties:
        return
    try:
        from nolan.workflow_registry import get_registry
        client, _ = get_registry().build_client("krea2-style-select", cfg, style=f",{gen_style}")
    except Exception as e:
        print(f"  gap-fill gen unavailable: {type(e).__name__}: {e}"); return
    from nolan.acquire.art_direction import verify_generation
    gdir = assets_dir / "generated"; gdir.mkdir(parents=True, exist_ok=True)
    for nd in empties:
        prompt = nd.get('gen_prompt') or nd['query']            # art-directed → no generic suffix
        base = f"{nd['id']}_gen.png"
        out = gdir / base
        try:
            for attempt in range(2):                            # FIDELITY re-check (#5b): gen -> verify -> ONE retry
                if not out.exists() or attempt == 1:
                    await client.generate(prompt, out, timeout=200, negative=nd.get("gen_negative"))
                if not (out.exists() and _valid_image(out)):
                    break
                v = await verify_generation(cfg, out, nd)
                if v["matches"]:
                    break
                print(f"    ⚠ fidelity miss {nd['id']} (try {attempt + 1}): {v['reason']}"
                      + (" — regenerating" if attempt == 0 else " — keeping (flagged, don't empty the beat)"))
        except Exception as e:
            print(f"    gen failed {nd['id']}: {type(e).__name__}: {e}"); continue
        if out.exists() and _valid_image(out):
            pool.append({"id": nd["id"], "file": f"generated/{base}", "media_type": "image",
                         "query": nd["query"], "source": "krea2 (generated)", "source_url": "",
                         "photographer": "", "license": "generated", "width": 0, "height": 0,
                         "duration": None, "caption": "", "generated": True,
                         "gen_prompt": prompt,                  # the enhanced prompt we generated from — surfaced in the edit UI
                         **({"gen_negative": nd["gen_negative"]} if nd.get("gen_negative") else {})})
            print(f"    + {base}  (krea2 generated)")


def _probe_dims(path: Path):
    """(width, height) of a pooled clip. The clip sources (local library, transcript_lib) carry no
    dimensions, so the pool recorded 0x0 and the author's menu couldn't tell a 1080p pull from a 360p
    one — a silent quality cap.

    Reads it off `ffmpeg -i` stderr, the same way `hf_qa.probe` reads duration. NOT ffprobe: the bundled
    imageio_ffmpeg ships ONLY `ffmpeg-win-*.exe`, so deriving a probe binary by name-swap raises
    FileNotFoundError every time — which this function would have swallowed, leaving every clip at 0x0
    and the LOW-RES tag silently never firing. Returns (0, 0) only when the stream line is truly absent.
    """
    import re as _re
    import subprocess
    try:
        from nolan.hf_qa import _ffmpeg
        r = subprocess.run([_ffmpeg(), "-i", str(path)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        m = _re.search(r"Stream #\S+: Video:.*?, (\d{2,5})x(\d{2,5})", r.stderr or "")
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    except Exception:
        return 0, 0


def _video_still(clip: Path):
    """A 3-frame filmstrip of a clip for the VLM — the SHARED organ (nolan.acquire.vlm_floor)."""
    from nolan.acquire.vlm_floor import video_still
    return video_still(clip)


def _downscale_for_vision(path: Path, max_dim: int = 1024):
    """Downscale a still to <=max_dim before the VLM cull (big images error the API → junk survives the
    floor) — delegates to the shared organ."""
    from nolan.acquire.shared import downscale_for_vision
    return downscale_for_vision(path, max_dim)


async def score_and_caption(cfg, pool, assets_dir: Path, needs, acfg=None):
    """The VLM usability FLOOR. The implementation lives in `nolan.acquire.vlm_floor` — it used to live
    HERE, in a CLI script, which meant it was reachable only by running the whole-project pool build.
    Every other acquisition path (notably the edit loop's scene-scoped one) therefore shipped with no
    floor at all, and landed clips carrying burned-in subtitles and topically wrong stills. Same organ,
    two callers, no second copy: tests/test_acquire_vlm_floor.py pins that this stays a delegation."""
    from nolan.acquire.vlm_floor import score_and_caption as _floor
    return await _floor(cfg, pool, assets_dir, needs, acfg=acfg)


def merge_pool(existing, incoming):
    """Union of two pools keyed on `file`, incoming winning per key, EXISTING ORDER PRESERVED.

    `pool.json` is the project's asset catalogue, not one run's output. It accumulates: the b-roll build
    writes it, the key-assets stage adds heroes, `/pool` curation sets `selected`, `add_scene_asset`
    appends a hand-dropped file with scene provenance, and an edit-loop acquisition adds one asset for
    one beat. Whoever wrote it LAST used to own all of it.

    The trap that made this urgent: acquiring a single asset from the edit loop ran the whole bridge,
    which ended here and replaced a 150-entry catalogue with that run's handful. It was avoided only
    because an agent noticed and hand-placed everything instead.

    Merging on `file` (the asset's identity on disk) rather than `id` is deliberate: `id` is the NEED it
    was fetched for and repeats across runs, while two runs that fetch the same file mean the same
    asset. Curation flags the new row doesn't carry (`selected`, `caption`, `flags`) are carried over
    from the existing row, so a re-run cannot silently un-prune the pool.
    """
    _CARRY = ("selected", "caption", "flags", "scene_id", "frame_id", "cleanup", "copyright_free")
    by_file, order = {}, []
    for e in list(existing or []) + list(incoming or []):
        if not isinstance(e, dict) or not e.get("file"):
            continue
        k = str(e["file"]).replace("\\", "/")
        if k in by_file:
            prev = by_file[k]
            merged = {**prev, **e}
            for c in _CARRY:                       # a human/earlier decision survives a re-fetch
                if c in prev and e.get(c) in (None, "", []):
                    merged[c] = prev[c]
            by_file[k] = merged
        else:
            by_file[k] = e
            order.append(k)
    return [by_file[k] for k in order]


def write_inventory(pool, project: Path, merge: bool = True):
    """Write the pool + the author's inventory. MERGES into any existing `pool.json` by default —
    see `merge_pool` for why an overwrite here was a data-loss trap. `merge=False` is a deliberate
    full replacement (a cold rebuild), and says so in the log line."""
    from nolan.hyperframes.pool_select import render_inventory_lines   # ONE inventory format (shared)
    pool_f = project / "pool.json"
    before = 0
    if merge and pool_f.exists():
        try:
            prev = json.loads(pool_f.read_text(encoding="utf-8"))
            prev = prev if isinstance(prev, list) else []
        except (json.JSONDecodeError, OSError):
            prev = []
        before = len(prev)
        pool = merge_pool(prev, pool)
    ex = project / "capture" / "extracted"
    ex.mkdir(parents=True, exist_ok=True)
    (ex / "asset-descriptions.md").write_text("\n".join(render_inventory_lines(pool)) + "\n", encoding="utf-8")
    pool_f.write_text(json.dumps(pool, indent=2), encoding="utf-8")
    how = f"merged into {before} existing" if (merge and before) else ("replaced" if not merge else "new")
    print(f"  inventory: {len(pool)} assets ({how}) → capture/extracted/asset-descriptions.md + pool.json")


def _candidates_to_pool(kept, assets_dir: Path):
    """Place engine Candidates into capture/assets with clean per-need names + the inventory dict shape."""
    import shutil
    from collections import defaultdict
    idx, pool = defaultdict(int), []
    for c in kept:
        need = c.meta.get("need", "x")
        i = idx[need]; idx[need] += 1
        ext = ".mp4" if c.modality == "video" else (Path(c.path).suffix or ".jpg")
        rel = ("videos/" if c.modality == "video" else "") + f"{need}_{i:02d}{ext}"
        dest = assets_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(str(c.path), str(dest))   # copy (library files stay in the library; temp gets cleaned)
        except Exception:
            continue
        # library clips arrive pre-captioned from their stored vision description (cull cascade Lever A —
        # skips a redundant VLM re-caption; they already passed the engine's cheap CLIP gate)
        cap = (f"[video] {c.meta.get('description', '')}".strip()
               if c.source in ("clips_library", "transcript_lib") else "")
        w, h = c.meta.get("width", 0), c.meta.get("height", 0)
        if c.modality == "video" and not h:
            w, h = _probe_dims(dest)                  # clip sources report no dims — probe, don't record 0×0
        pool.append({"id": need, "file": rel, "media_type": c.modality, "query": c.meta.get("query", ""),
                     "source": c.meta.get("source", c.source), "source_url": c.meta.get("source_url", ""),
                     "photographer": c.meta.get("photographer", ""), "license": c.meta.get("license", ""),
                     "width": w, "height": h,
                     "duration": c.meta.get("duration"), "relevance": round(c.relevance, 3), "caption": cap,
                     # explicit copyright-free flag so the pool is queryable, not just a license string
                     **({"copyright_free": bool(c.meta["copyright_free"])} if "copyright_free" in c.meta else {}),
                     # PROVENANCE for a modification WE made: which burned-in elements were cropped out
                     # (logo/caption) and the resulting zoom. Without it the asset silently differs from
                     # its source and nobody can tell whether a tight crop was ours or the footage's.
                     **({"cleanup": c.meta["cleanup"]} if c.meta.get("cleanup", {}).get("changed") else {}),
                     **({"gen_prompt": c.meta["gen_prompt"]} if c.meta.get("gen_prompt") else {}),
                     **({"gen_negative": c.meta["gen_negative"]} if c.meta.get("gen_negative") else {})})
    return pool


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--needs", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--per", type=int, default=8, help="assets kept per need (depth)")
    ap.add_argument("--no-caption", action="store_true")
    ap.add_argument("--no-expand", action="store_true", help="skip evoke_broll metaphor expansion of evocative needs")
    ap.add_argument("--no-gen", action="store_true", help="skip generation of originals for thin/off-topic beats")
    ap.add_argument("--legacy", action="store_true", help="old stock-only collect + gap-fill (pre multi-source engine)")
    ap.add_argument("--no-vlm-cull", action="store_true", help="skip the VLM usability floor (caption only, cull nothing)")
    ap.add_argument("--replace-pool", action="store_true",
                    help="REPLACE pool.json with this run instead of merging into it (a cold rebuild). "
                         "Default is merge: the pool is the project's catalogue, not one run's output.")
    args = ap.parse_args()
    from nolan.config import load_config
    cfg = load_config()
    needs = json.load(open(args.needs, encoding="utf-8"))
    project = Path(args.project)
    assets_dir = project / "capture" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    from nolan.acquire import AcquireConfig, gen_style_for
    acfg = AcquireConfig(per_need=args.per, generate_evocative=not args.no_gen, vlm_cull=not args.no_vlm_cull)
    # generation style: explicit per-project override (hyperframes.json 'gen_style') else theme-derived
    _ectx, _theme = _essay_context(project)
    try:
        _gs_override = json.loads((project / "hyperframes.json").read_text(encoding="utf-8")).get("gen_style")
    except Exception:
        _gs_override = None
    gen_style = _gs_override or gen_style_for(_theme)
    if not args.no_expand and any(nd.get("evocative") for nd in needs):
        print("EXPAND (evoke_broll metaphors for evocative needs)")
        try:
            asyncio.run(expand_needs(cfg, needs))
        except Exception as e:
            print(f"  expand skipped: {type(e).__name__}: {e}")

    if not args.no_gen:                                 # art-direct: derive the visual brief + compose gen prompts
        print(f"ART-DIRECT (visual brief) + compose gen prompts · style default: {gen_style}")
        try:
            brief = asyncio.run(art_direct(cfg, needs, essay_context=_ectx, theme=_theme,
                                           style_default=gen_style, project=project))
            gen_style = brief.style                      # the brief OWNS the style (one place, not a parallel lever)
        except Exception as e:
            print(f"  art-direction skipped: {type(e).__name__}: {e}")

    if args.legacy:
        print("COLLECT (legacy stock-only)")
        pool = collect(cfg, needs, assets_dir, args.per)
        if not args.no_gen:
            empties = [nd for nd in needs if nd["id"] not in {p["id"] for p in pool}]
            if empties:
                print(f"GAP-FILL GEN ({len(empties)} empty need(s))")
                try:
                    asyncio.run(gen_fill(cfg, empties, assets_dir, pool, gen_style=gen_style))
                except Exception as e:
                    print(f"  gen skipped: {type(e).__name__}: {e}")
    else:
        from nolan.acquire import build_context, acquire_pool
        # Release THIS pool's previous clip claims BEFORE anything reads the ledger (hero claims stay).
        from nolan.acquire.shared import clear_claims
        _rel = clear_claims(project, "pool")
        if _rel:
            print(f"  released {_rel} clip claim(s) from the previous pool build")
        ctx = build_context(cfg, clip_seconds=acfg.clip_seconds, gen_style=gen_style,
                            clip_lib_max=acfg.clip_lib_max, clip_lib_min_sim=acfg.clip_lib_min_sim,
                            project_dir=project)      # → the clip-CLAIM ledger (dedup vs the hero pool)
        print(f"ACQUIRE — stock={bool(ctx.search_stock)} library={bool(ctx.search_library)} "
              f"clips_library={bool(ctx.search_clips)} "
              f"clip-relevance={bool(ctx.relevance)} "
              f"generate={bool(ctx.generate) and acfg.generate_evocative} | "   # organ AND --no-gen not set
              f"{len(needs)} needs × up to {acfg.per_need} kept (images over-fetch ×{acfg.over_fetch}, "
              f"video ×{acfg.over_fetch_video})")
        import shutil
        cand_dir = assets_dir / "_cand"                # temp: over-fetched candidates land here…
        kept = acquire_pool(needs, ctx, acfg, cand_dir=cand_dir, log=print)
        pool = _candidates_to_pool(kept, assets_dir)   # …only the KEPT are copied into assets…
        shutil.rmtree(cand_dir, ignore_errors=True)    # …and the rejects are dropped

    if pool and not args.no_caption:
        print("SCORE + CAPTION (VLM usability floor + inventory)" if acfg.vlm_cull else "CAPTION (VLM, no cull)")
        pool = asyncio.run(score_and_caption(cfg, pool, assets_dir, needs, acfg))

    # POST-CULL GAP-FILL: the VLM cull empties needs that HAD candidates at retrieval time (so the
    # engine's floor-gated generation never fired for them). Without this, an abstract essay — where
    # stock/library yield is genuinely poor — ships with a third of its beats unillustrated. Regenerate
    # a bespoke still for every need the cull left empty (generated art is exempt from the cull).
    if not args.no_gen:
        empties = _empty_needs(needs, pool)
        if empties:
            print(f"POST-CULL GAP-FILL — {len(empties)} need(s) emptied by the cull → generate")
            try:
                asyncio.run(gen_fill(cfg, empties, assets_dir, pool, gen_style=gen_style))
            except Exception as e:
                print(f"  post-cull gen skipped: {type(e).__name__}: {e}")

    write_inventory(pool, project, merge=not args.replace_pool)


if __name__ == "__main__":
    main()
