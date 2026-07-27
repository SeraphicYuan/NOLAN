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
  channels  segments-only · frames-only · lexical-only (BM25) · both (the shipped interleave) ·
            all3, each run through the SHIPPED `build_context(...).search_clips` path, never a
            re-implementation of it
  metrics   success@k    did ANY usable shot appear in the top k? The right question for a beat
                         (you need one good clip, not all of them) and robust to a partial pool.
            precision@1  was the FIRST pick usable? The one that matches what we actually ship.
            abstain      on beats the library cannot serve, did the channel return NOTHING?

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

CHANNELS = {                      # name -> the build_context tier switches it turns on
    "segments": {"want_transcript_lib": True},
    "frames": {"want_transcript_frames": True},
    "lexical": {"want_transcript_lexical": True},
    "both": {"want_transcript_lib": True, "want_transcript_frames": True},   # today's shipped path
    "all3": {"want_transcript_lib": True, "want_transcript_frames": True,
             "want_transcript_lexical": True},
}
_TIERS = ("want_transcript_lib", "want_transcript_frames", "want_transcript_lexical")

# NEGATIVE CONTROLS — beats this library cannot possibly serve.
#
# These are the only reason we know the scores are meaningless: measured against a
# diamond/Prelinger/finance corpus, "sushi preparation in a Tokyo restaurant" scored 0.649 and
# "penguins on Antarctic sea ice" 0.671, against 0.72 for genuine on-domain hits. A dense index is
# k-nearest — it returns k rows for ANY query — so the only honest question to ask a retrieval
# channel is whether it can say NOTHING. They need no labels: the ground truth is "nothing here is
# relevant", so the metric is simply whether the channel returned anything at all.
#
# They are a permanent fixture, not a one-off probe. As the library grows the expected maximum of
# N background draws rises while on-domain scores stay flat, so this is the number that tells us
# when a threshold has silently expired.
NEGATIVE_CONTROLS = (
    ("neg:sushi", "sushi preparation in a Tokyo restaurant"),
    ("neg:penguins", "penguins on Antarctic sea ice"),
    ("neg:knitting", "close-up of hands knitting a wool scarf"),
    ("neg:volcano", "lava flowing from an erupting volcano at night"),
)


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


def _pool_candidates(ctxs, cat, need, gid, per_channel):
    """Run ONE need through every channel and pool what they return, keyed by (url, start).

    Pooling — rather than scoring each channel against its own candidates — is what makes the
    comparison fair: a human judges each shot ONCE and every channel is scored against that shared
    judgement, so no channel gets credit merely for having proposed a candidate.
    """
    pooled = {}
    for cname, ctx in ctxs.items():
        try:
            cands = ctx.search_clips(need, per_channel) or []
        except Exception as e:
            print(f"    ! {gid} {cname}: {type(e).__name__}: {e}")
            cands = []
        for rank, c in enumerate(cands[:per_channel]):
            m = c.meta or {}
            key = (str(m.get("source_url") or ""), round(float(m.get("clip_start", 0)), 1))
            row = pooled.setdefault(key, {
                "gid": gid, "url": key[0], "start": key[1],
                "dur": round(float(m.get("clip_dur", 0)), 1),
                "title": _title_of(cat, key[0]), "source": c.source,
                "caption": str(m.get("description") or "")[:160].replace("\n", " "),
                "ranks": {}, "relevant": ""})
            row["ranks"][cname] = rank            # where each channel placed it
    return pooled


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
    for name, tiers in CHANNELS.items():
        ctxs[name] = build_context(cfg, want_stock=False, want_library=False, want_clip=False,
                                   want_gen=False, want_clips_library=False,
                                   **{t: tiers.get(t, False) for t in _TIERS})

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
            sheet.extend(_pool_candidates(ctxs, cat, need, gid, args.per_channel).values())

    # The negative controls, through the SAME channels and the same pooling. Auto-labelled `n`:
    # the ground truth is that the library cannot serve these, so a returned candidate is wrong by
    # construction. `auto` marks them so a human can flip any the corpus turns out to genuinely
    # hold (Prelinger is a general archive — this is a stated assumption, not a certainty).
    print(f"  negative controls: {len(NEGATIVE_CONTROLS)} beats the library cannot serve")
    for nid, q in NEGATIVE_CONTROLS:
        gid = f"_control:{nid}"
        goldens.append({"gid": gid, "project": "_control", "query": q, "queries": [q],
                        "origin": "negative", "entity_kind": None, "evocative": False,
                        "category": "control", "media_type": "video", "named_hint": False})
        need = {"query": q, "queries": [q], "id": nid, "media_type": "video",
                "category": "archival", "evocative": False}
        rows = list(_pool_candidates(ctxs, cat, need, gid, args.per_channel).values())
        for r in rows:
            r["relevant"], r["auto"] = "n", True
        sheet.extend(rows)

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
        if g.get("origin") == "negative":
            lines += ["> NEGATIVE CONTROL — the library cannot serve this beat, so every row below "
                      "is pre-labelled `n` and needs no work. An empty list is the CORRECT answer; "
                      "anything listed is a channel failing to abstain. Flip a row to `y` only if "
                      "the corpus genuinely holds it.", ""]
        elif not rows:
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
    # Negative controls are scored separately (abstain), never mixed into the relevance slices —
    # they have no relevant answer, so averaging them in would flatter every channel equally.
    neg_gids = [gid for gid, g in goldens.items() if g.get("origin") == "negative"]
    slices = {"ALL": lambda g: g.get("origin") != "negative",
              "look": lambda g: not g["named_hint"] and g.get("origin") != "negative",
              "named": lambda g: g["named_hint"],
              "  from needs": lambda g: g.get("origin") == "need",
              "  key assets": lambda g: g.get("origin") == "key_asset",
              "evocative": lambda g: g["evocative"] and g.get("origin") != "negative",
              "concrete": lambda g: not g["evocative"] and g.get("origin") != "negative"}
    print(f"\n{'slice':<12}{'n':>4}  " + " ".join(f"{c:>17}" for c in CHANNELS))
    print(f"{'':16}  " + " ".join(f"{'  '.join(f's@{k}' for k in ks):>17}" for _ in CHANNELS))
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
            cells.append(" ".join(f"{100 * hits[k] / len(gids):4.0f}" for k in ks))
        print(f"{sname:<12}{len(gids):>4}  " + " ".join(f"{c:>17}" for c in cells))
    print("\nsuccess@k = % of needs where at least one USABLE shot appeared in that channel's top k")

    # ---- precision@1 -------------------------------------------------------------------------
    # success@k asks "is there something good in the top k" — the right question for a beat, but it
    # is blind to what we actually ship: the FIRST pick. A channel that puts junk at rank 0 and a
    # hit at rank 4 scores identically at k=5 to one that gets it right first time. p@1 is the
    # metric this program optimises, because a wrong pick becomes a shot in the video.
    print(f"\n{'slice':<12}{'n':>4}  " + " ".join(f"{c + ' p@1':>13}" for c in CHANNELS))
    for sname, keep in slices.items():
        gids = [g for g in done_gids if keep(goldens[g])]
        if not gids:
            continue
        cells = []
        for cname in CHANNELS:
            top, hit = 0, 0
            for gid in gids:
                first = [r for r in labelled if r["gid"] == gid
                         and int((r.get("ranks") or {}).get(cname, -1)) == 0]
                if not first:
                    continue                      # channel returned nothing (or its top-1 is unlabelled)
                top += 1
                if str(first[0]["relevant"]).lower().startswith("y"):
                    hit += 1
            cells.append(f"{100 * hit / top:4.0f} (n={top})" if top else "   — (n=0)")
        print(f"{sname:<12}{len(gids):>4}  " + " ".join(f"{c:>13}" for c in cells))
    print("p@1 = % of needs whose TOP pick was usable; n = needs where that channel picked at all")

    # ---- abstain on the negative controls ----------------------------------------------------
    if neg_gids:
        by_gid = {}
        for r in rows:
            by_gid.setdefault(r["gid"], []).append(r)
        print(f"\n{'ABSTAIN':<12}{len(neg_gids):>4}  " + " ".join(f"{c:>13}" for c in CHANNELS))
        cells, mean = [], []
        for cname in CHANNELS:
            quiet, total = 0, 0
            for gid in neg_gids:
                got = [r for r in by_gid.get(gid, []) if cname in (r.get("ranks") or {})]
                total += len(got)
                if not got:
                    quiet += 1
            cells.append(f"{100 * quiet / len(neg_gids):5.1f}%")
            mean.append(f"{total / len(neg_gids):5.2f}")
        print(f"{'  silent':<12}{'':>4}  " + " ".join(f"{c:>13}" for c in cells))
        print(f"{'  junk/need':<12}{'':>4}  " + " ".join(f"{c:>13}" for c in mean))
        print("silent = % of impossible beats the channel correctly returned NOTHING for.\n"
              "junk/need = mean candidates returned for a beat with no true answer (each one is a\n"
              "download we would pay for). Both are the numbers that expire as the library grows.")
    else:
        print("\n! no negative controls in goldens.json — re-run `extract` to add them")
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
