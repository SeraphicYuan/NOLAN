"""Which retrieval channel actually finds usable FOOTAGE for an authored beat? — measured.

The transcript library is reached by two indexes over one corpus: SEGMENTS (what is said) and
FRAMES (what is shown, gemma-captioned). We have been choosing between them, and weighting them
against each other, from anecdotes — including a 1:1 interleave I shipped after looking at a single
beat. The image tier settled the same question with an eval and found that a near-equal blend was
the WORST configuration it tried. This is the instrument for the video path.

Why this is shaped differently from `eval_visuallib_recall.py`: that eval pins each golden need to
ONE right artwork by title. B-roll has no single right answer — many shots can serve "a 1960s
congress scene" — so an answer key cannot be written in advance. Instead we POOL the candidates
every channel returns, a human judges each one once, and every channel is then scored against that
shared judgement. Same labels, no channel advantaged by who proposed the candidate.

  needs     REAL authored needs from `capture/needs.json` across three projects (not paraphrases
            written by the retrieval author — this is the one bias the image eval could not avoid)
  channels  segments-only · frames-only · both (the shipped interleave), each run through the
            SHIPPED `build_context(...).search_clips` path, never a re-implementation of it
  metric    success@k — did ANY usable shot appear in the top k? That is the real question for a
            beat (you need one good clip, not all of them), and it is robust to a partial pool.

Honest about its own bias (read before quoting numbers):
  * Labels judge only what the channels PROPOSED. A shot no channel retrieved is invisible here, so
    these numbers bound relative performance, never absolute recall.
  * `pool.json` is NOT used as ground truth: it records what was acquired by today's retrieval, so
    scoring against it would just reproduce today's behaviour (survivorship bias). Hence hand labels.
  * The corpus is 253 rows / 179 captioned. Frames can only ever reach the captioned subset; the
    run prints that split so a thin frame tier is not mistaken for a weak one.
  * Needs whose beat the library genuinely cannot serve are KEPT, not dropped — the abstain case is
    half the point, and a channel that confidently returns junk there should be penalised for it.

Usage:
  # 1. pool the candidates and write a labelling sheet
  python -X utf8 scripts/eval_video_retrieval.py extract [--per-project 8] [--per-channel 5]
  # 2. a human marks `relevant` in the sheet (y/n), then
  python -X utf8 scripts/eval_video_retrieval.py score [--k 1,3,5]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"
OUT = REPO / "eval" / "video_retrieval"

# Three projects chosen for RETRIEVAL SPREAD, not for size:
#   diamond   — archival/documentary, the library's best-covered subject (the easy case)
#   homer     — art/literature, heavily evocative needs (the non-literal case)
#   openai    — contemporary tech, a subject the library barely holds (the ABSTAIN case)
PROJECTS = ("the-diamond-illusion-v2", "homer-hf", "the-openai-debate")

CHANNELS = {                      # name -> (want_transcript_lib, want_transcript_frames)
    "segments": (True, False),
    "frames": (False, True),
    "both": (True, True),
}


def _load_needs(project: str):
    f = VIDEOS / project / "capture" / "needs.json"
    if not f.exists():
        return []
    d = json.loads(f.read_text(encoding="utf-8"))
    rows = d if isinstance(d, list) else (d.get("needs") or [])
    return [r for r in rows if (r.get("query") or r.get("queries"))]


def _entities(project: str):
    """The project's authored KEY ASSETS — identity questions BY CONSTRUCTION, not by detection.

    These have to be goldens in their own right. `needs.json` is overwhelmingly descriptive (20 of
    24 sampled), so scoring only those would under-sample the named mode to the point of measuring
    nothing — and the named mode is the one this whole investigation is about.
    """
    f = VIDEOS / project / "key_assets.json"
    if not f.exists():
        return []
    d = json.loads(f.read_text(encoding="utf-8"))
    return [e for e in (d.get("entities") or []) if e.get("name")]


def _entity_names(project: str):
    return [str(e.get("name") or "") for e in _entities(project)]


_PROPER = re.compile(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})+|[A-Z]{2,})\b")


def _named_hint(query: str, entities) -> bool:
    """Is this an IDENTITY question rather than a description?

    Two signals, both cheap and corpus-independent (a cover-based detector would conflate 'is a
    named query' with 'we happen to hold a matching title'): the query names one of the project's
    own key-asset entities, or it carries a proper-noun / acronym signature.
    """
    q = query or ""
    low = q.lower()
    for e in entities:
        toks = [t for t in re.split(r"\W+", e.lower()) if len(t) > 3]
        # COVER >= 0.75, the same bar the image router uses (`_NAMED_MIN_COVER`) and for the same
        # reason: a looser bar answers "is this relevant" rather than "is this an identity question".
        # At half-cover, "diamond resale jewelry store" matched the entity "Lightbox Jewelry" on the
        # single token `jewelry` and was mis-tagged NAMED — which would have poisoned the very slice
        # this eval exists to measure.
        if toks and (sum(1 for t in toks if t in low) / len(toks)) >= 0.75:
            return True
    return bool(_PROPER.search(q))


def _title_of(cat, url: str) -> str:
    from nolan import archive_source as ar
    from nolan.youtube import extract_video_id as yid
    sid = ar.collection_ref(url) if "archive.org" in (url or "") else (yid(url or "") or "")
    return str((cat.get(sid) or {}).get("title") or sid or "?")


def cmd_extract(args) -> int:
    from nolan.config import load_config
    from nolan.acquire.context import build_context
    from nolan import transcript_lib as tl

    cfg = load_config()
    cat = tl.load_catalog()
    captioned = sum(1 for v in cat.values() if int(v.get("frames", 0) or 0) > 0)
    print(f"corpus: {len(cat)} library rows, {captioned} captioned "
          f"({100 * captioned / max(1, len(cat)):.0f}% reachable by the frame tier)")

    ctxs = {}
    for name, (seg, frm) in CHANNELS.items():
        ctxs[name] = build_context(cfg, want_stock=False, want_library=False, want_clip=False,
                                   want_gen=False, want_clips_library=False,
                                   want_transcript_lib=seg, want_transcript_frames=frm)

    goldens, sheet = [], []
    for project in PROJECTS:
        ents = _entity_names(project)
        needs = _load_needs(project)[: args.per_project]
        if not needs:
            print(f"  ! {project}: no needs.json — skipped LOUDLY (not scored as zero)")
            continue
        # descriptive beats + identity entities, as ONE golden list — the modes must be measured
        # against the same channels and the same labels or the comparison means nothing
        items = [("need", n) for n in needs]
        items += [("key_asset", e) for e in _entities(project)[: args.per_project]]
        print(f"  {project}: {len(needs)} needs + "
              f"{len(_entities(project)[: args.per_project])} key-asset entities")
        for origin, need in items:
            if origin == "key_asset":
                q = str(need.get("name"))
                need = {"query": q, "queries": (need.get("queries_locked") or [q]),
                        "id": f"ka:{need.get('id') or q}", "media_type": "video",
                        "category": "archival", "evocative": False, "_kind": need.get("kind")}
            q = str(need.get("query") or (need.get("queries") or [""])[0])
            gid = f"{project}:{need.get('id')}"
            goldens.append({"gid": gid, "project": project, "query": q,
                            "queries": need.get("queries") or [q], "origin": origin,
                            "entity_kind": need.get("_kind"),
                            "evocative": bool(need.get("evocative")),
                            "category": need.get("category"), "media_type": need.get("media_type"),
                            # an authored key asset IS an identity question; no detector needed
                            "named_hint": True if origin == "key_asset" else _named_hint(q, ents)})
            pooled = {}
            for cname, ctx in ctxs.items():
                try:
                    cands = ctx.search_clips(need, args.per_channel) or []
                except Exception as e:
                    print(f"    ! {gid} {cname}: {type(e).__name__}: {e}")
                    cands = []
                for rank, c in enumerate(cands[: args.per_channel]):
                    m = c.meta or {}
                    key = (str(m.get("source_url") or ""), round(float(m.get("clip_start", 0)), 1))
                    row = pooled.setdefault(key, {
                        "gid": gid, "url": key[0], "start": key[1],
                        "dur": round(float(m.get("clip_dur", 0)), 1),
                        "title": _title_of(cat, key[0]), "source": c.source,
                        "caption": str(m.get("description") or "")[:160].replace("\n", " "),
                        "ranks": {}, "relevant": ""})
                    row["ranks"][cname] = rank            # where each channel placed it
            sheet.extend(pooled.values())

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "goldens.json").write_text(json.dumps(goldens, indent=2, ensure_ascii=False), encoding="utf-8")
    with (OUT / "labels.jsonl").open("w", encoding="utf-8") as fh:
        for r in sheet:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    _write_sheet(goldens, sheet)
    print(f"\n{len(goldens)} needs, {len(sheet)} candidates pooled to label")
    print(f"  {OUT / 'labels.jsonl'}   <- set \"relevant\": \"y\" or \"n\"")
    print(f"  {OUT / 'SHEET.md'}       <- the same thing, readable")
    return 0


def _write_sheet(goldens, sheet):
    by_gid = {}
    for r in sheet:
        by_gid.setdefault(r["gid"], []).append(r)
    lines = ["# Labelling sheet — is this shot USABLE for this beat?",
             "",
             "Mark each row `y` (a competent editor would cut this into that beat) or `n`.",
             "Judge the SHOT, not the film. Era/subject mismatch = `n` even if the topic is close.",
             "Leave blank to skip — the scorer reports how much was labelled.", ""]
    for g in goldens:
        rows = by_gid.get(g["gid"], [])
        lines += [f"## {g['gid']} — {g['query']}",
                  f"*{g['category']} · {g['media_type']} · "
                  f"{'evocative' if g['evocative'] else 'concrete'} · "
                  f"{'NAMED' if g['named_hint'] else 'look'}"
                  f"{' · ' + str(g['entity_kind']) if g.get('entity_kind') else ''}"
                  f" · {len(rows)} candidates*", ""]
        if not rows:
            lines += ["> no channel returned anything (this is the ABSTAIN case — correct if the "
                      "library genuinely lacks it)", ""]
        for r in rows:
            lines.append(f"- [ ] `{r['url'].rsplit('/', 1)[-1][:28]}` @{r['start']:.0f}s "
                         f"+{r['dur']:.0f}s — **{r['title'][:46]}** — {r['caption'][:96]}")
        lines.append("")
    (OUT / "SHEET.md").write_text("\n".join(lines), encoding="utf-8")


def cmd_score(args) -> int:
    gf, lf = OUT / "goldens.json", OUT / "labels.jsonl"
    if not (gf.exists() and lf.exists()):
        print("No sheet yet — run `extract` first.")
        return 1
    goldens = {g["gid"]: g for g in json.loads(gf.read_text(encoding="utf-8"))}
    rows = [json.loads(l) for l in lf.read_text(encoding="utf-8").splitlines() if l.strip()]
    labelled = [r for r in rows if str(r.get("relevant") or "").lower().startswith(("y", "n"))]
    if not labelled:
        print(f"0 of {len(rows)} candidates labelled — nothing to score yet.")
        return 1
    done_gids = {r["gid"] for r in labelled}
    print(f"labelled {len(labelled)}/{len(rows)} candidates across {len(done_gids)}/{len(goldens)} needs")

    ks = [int(x) for x in str(args.k).split(",")]
    slices = {"ALL": lambda g: True,
              "look": lambda g: not g["named_hint"],
              "named": lambda g: g["named_hint"],
              "  from needs": lambda g: g.get("origin") == "need",
              "  key assets": lambda g: g.get("origin") == "key_asset",
              "evocative": lambda g: g["evocative"],
              "concrete": lambda g: not g["evocative"]}
    print(f"\n{'slice':<12}{'n':>4}  " + "  ".join(f"{c:>22}" for c in CHANNELS))
    print(f"{'':16}  " + "  ".join(f"{'  '.join(f's@{k}' for k in ks):>22}" for _ in CHANNELS))
    for sname, keep in slices.items():
        gids = [g for g in done_gids if keep(goldens[g])]
        if not gids:
            continue
        cells = []
        for cname in CHANNELS:
            hits = {k: 0 for k in ks}
            for gid in gids:
                rel = [r for r in labelled if r["gid"] == gid
                       and str(r["relevant"]).lower().startswith("y")
                       and cname in (r.get("ranks") or {})]
                for k in ks:
                    if any(int(r["ranks"][cname]) < k for r in rel):
                        hits[k] += 1
            cells.append("  ".join(f"{100 * hits[k] / len(gids):5.1f}" for k in ks))
        print(f"{sname:<12}{len(gids):>4}  " + "  ".join(f"{c:>22}" for c in cells))
    print("\nsuccess@k = % of needs where at least one USABLE shot appeared in that channel's top k")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="pool candidates and write the labelling sheet")
    e.add_argument("--per-project", type=int, default=8)
    e.add_argument("--per-channel", type=int, default=5)
    e.set_defaults(fn=cmd_extract)
    s = sub.add_parser("score", help="score the labelled sheet")
    s.add_argument("--k", default="1,3,5")
    s.set_defaults(fn=cmd_score)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
