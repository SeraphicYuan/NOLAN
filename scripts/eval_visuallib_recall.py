"""Does the Visual Lib actually beat keyword search? — recall@k, measured, both directions.

The whole premise of the not-held tier is that a VLM/CLIP-enriched local index answers a video
author's need better than the provider's own keyword search does. That is a claim, and this is
the instrument that decides it. Without a number, the tier is a belief.

  corpus    the discovery rows harvested from the Art Institute (`nolan images harvest artic`)
  needs     GOLDEN, hand-written the way an author writes a beat need, in two kinds:
              look   — no names, pure description ("pedestrians with umbrellas on a wet street")
              named  — the entity ("Caillebotte, Paris Street; Rainy Day")
  answer    the artwork that need is FOR, pinned by title (verified present before it is scored)
  systems   visual-lib routed hybrid  ·  identity channel only  ·  CLIP channel only
            vs the BASELINE: `ArtInstituteProvider.search` — today's keyword path, same corpus.

Honest about its own bias (read this before quoting the numbers):
  * The needs are paraphrases written by the same author as the retrieval design. They are not
    copied from the catalog, but they are the friendly case for semantic search.
  * The corpus is the harvested subset, not the full 61,568 public-domain artworks; recall on a
    small corpus flatters everything.
  * The baseline queries the LIVE api over the FULL collection, so it is being asked a harder
    question (more distractors). Where the baseline wins, that gap is real; where it loses, some
    of the margin is corpus size. Both directions are printed.

Usage:
  python -X utf8 scripts/eval_visuallib_recall.py [--k 5] [--no-baseline] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

# (expected title fragment, look-query, named-query). The expected title is matched
# case-insensitively as a substring of the catalog title, so punctuation/subtitle drift is fine.
#
# Some entries can never appear in a CC0 harvest and are skipped LOUDLY rather than scored as
# misses: Nighthawks (1942) and American Gothic (1930) are still in copyright, so the Art
# Institute's API correctly reports `is_public_domain: false` and the harvester correctly refuses
# them. That is the rights tier working, not retrieval failing — the run prints every skip.
GOLDEN = [
    ("Paris Street; Rainy Day",
     "pedestrians under umbrellas on a wet cobbled boulevard, grey overcast city",
     "Caillebotte Paris Street Rainy Day"),
    ("A Sunday on La Grande Jatte",
     "crowd relaxing on a riverbank lawn in the afternoon, painted in tiny coloured dots",
     "Seurat A Sunday on La Grande Jatte"),
    ("Nighthawks",
     "late-night diner seen through plate glass, empty street outside",
     "Edward Hopper Nighthawks"),
    ("American Gothic",
     "a stern farmer holding a pitchfork beside a woman in front of a white farmhouse",
     "Grant Wood American Gothic"),
    ("The Bedroom",
     "a small simple bedroom with a wooden bed and two chairs, bright flat colour",
     "Van Gogh The Bedroom"),
    ("Water Lilies",
     "pond surface covered with floating lily pads, no horizon",
     "Monet Water Lilies"),
    ("Stacks of Wheat",
     "haystacks in a field at the end of summer, long shadows",
     "Monet Stacks of Wheat"),
    ("The Beach at Sainte-Adresse",
     "figures on a pebbled beach with sailboats and a wide sky",
     "Monet The Beach at Sainte-Adresse"),
    ("Two Sisters",
     "two girls on a terrace with a basket of yarn, garden behind",
     "Renoir Two Sisters On the Terrace"),
    ("At the Moulin Rouge",
     "nightclub interior with figures around a table under harsh artificial light",
     "Toulouse-Lautrec At the Moulin Rouge"),
    ("The Old Guitarist",
     "a gaunt blind man hunched over a guitar, blue monochrome",
     "Picasso The Old Guitarist"),
    ("The Child's Bath",
     "a woman washing a child's feet in a basin, seen from above",
     "Mary Cassatt The Child's Bath"),
    ("Woman at Her Toilette",
     "a woman at her dressing table in soft loose brushwork",
     "Berthe Morisot Woman at Her Toilette"),
    ("Distant View of Niagara Falls",
     "a vast waterfall seen from a wooded overlook, tiny figures for scale",
     "Thomas Cole Distant View of Niagara Falls"),
    ("Saint George and the Dragon",
     "an armoured knight on horseback spearing a dragon, gold ground",
     "Bernat Martorell Saint George and the Dragon"),
    ("The Herring Net",
     "fishermen hauling a full net into a small boat in heavy swell",
     "Winslow Homer The Herring Net"),
    ("Sky Above Clouds",
     "endless flat cloud tops seen from an aeroplane window",
     "Georgia O'Keeffe Sky Above Clouds"),
    ("The Assumption of the Virgin",
     "towering altarpiece of a figure rising to heaven surrounded by upturned faces",
     "El Greco The Assumption of the Virgin"),
    ("Coronation Stone of Moctezuma",
     "carved stone disc with Aztec relief glyphs",
     "Coronation Stone of Moctezuma II"),
    ("Buddha Shakyamuni Seated in Meditation",
     "seated meditating buddha sculpture, hands in lap",
     "Buddha Shakyamuni Seated in Meditation"),
    ("Bedcover",
     "an 18th-century quilted textile bedcover",
     "Bedcover 1778"),
    ("The Millinery Shop",
     "a woman examining a hat in a shop full of hats",
     "Degas The Millinery Shop"),
    ("Mother and Child",
     "a mother holding her small child close, tender domestic scene",
     "Mother and Child painting"),
    ("Self-Portrait",
     "a bearded man in a straw hat staring out of the frame in short jabbed strokes",
     "Van Gogh Self-Portrait"),

    # --- ADDED 2026-07-31, after the full crawl showed what the corpus actually IS ---------
    #
    # The set above was written against an 841-row sample and is almost entirely European and
    # American PAINTING. The completed harvest is 56,724 rows and **42.9% prints** (largely
    # Japanese ukiyo-e — Hiroshige alone has 1,509 works) against **7.5% paintings**. The old
    # skew was an artifact of the depth-capped `search` endpoint relevance-ranking toward famous
    # pictures; the uncapped bulk listing shows the real distribution.
    #
    # So the instrument was measuring one corner of the library. These needs cover the kinds that
    # actually dominate it. Every title below was verified present in the live corpus before
    # being added — a golden entry that is merely plausible measures nothing.
    ("Under the Wave off Kanagawa",
     "a towering breaking wave with claw-like foam curling over small boats, snow-capped peak "
     "far behind",
     "Hokusai Under the Wave off Kanagawa Great Wave"),
    ("Sudden Shower over Shin Ohashi Bridge",
     "figures hurrying across a wooden bridge under slanting lines of rain",
     "Hiroshige Sudden Shower over Shin-Ohashi Bridge and Atake"),
    ("Mitsuke",
     "travellers poling flat ferries across a wide shallow river in mist",
     "Hiroshige Mitsuke Ferries Crossing the Tenryu River"),
    ("Melencolia I",
     "a brooding winged figure seated among scattered geometric instruments and a sleeping dog",
     "Durer Melencolia I"),
    ("Knight, Death, and the Devil",
     "an armoured rider on horseback passing a skeletal figure in a dark ravine",
     "Durer Knight Death and the Devil"),
    ("Courthouse Steps",
     "a quilt built from concentric strips of fabric forming square blocks",
     "Log Cabin Quilt Courthouse Steps Variation"),
    ("Plum Vase",
     "a pale celadon vase inlaid with flying cranes among clouds",
     "Plum Vase Maebyeong with Clouds Cranes and Children"),
    ("Reliquary Monstrance in the form of a Church",
     "a gilded shrine built like a miniature gothic church with spires",
     "Reliquary Monstrance in the form of a Church"),
]


def _hit_rank(titles, expect: str):
    """1-based rank of the first title containing `expect` (case-insensitive), else None."""
    want = expect.lower()
    for i, t in enumerate(titles):
        if want in (t or "").lower():
            return i + 1
    return None


def _recall(ranks, k):
    scored = [r for r in ranks if r is not None]
    return round(100.0 * sum(1 for r in scored if r <= k) / len(ranks), 1) if ranks else 0.0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--scope", default="global")
    ap.add_argument("--project", default=None)
    ap.add_argument("--collection", type=int, default=None,
                    help="restrict retrieval to one collection id. Use it to keep runs COMPARABLE "
                         "as the library grows: the golden answers are pinned to a specific work, "
                         "and a second institution holding its own 'Water Lilies' or "
                         "'Self-Portrait' scores as a miss when it is really a correct answer "
                         "from the wrong museum.")
    ap.add_argument("--no-baseline", action="store_true",
                    help="skip the live provider search (offline runs)")
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args(argv)

    from nolan.imagelib import ImageLibrary
    lib = ImageLibrary(scope=args.scope, project=args.project)
    rows = lib.catalog.list(status="active", held=0, limit=100_000,
                            collection_id=args.collection)
    corpus = len(rows)
    if not corpus:
        print("No discovery rows. Harvest first:  nolan images harvest artic --limit 600")
        return 2
    titles = [(a.title or "").lower() for a in rows]

    present, missing = [], []
    for expect, look, named in GOLDEN:
        (present if any(expect.lower() in t for t in titles) else missing).append(
            (expect, look, named))

    print(f"corpus: {corpus} discovery rows | golden: {len(present)} present, "
          f"{len(missing)} not in this harvest (skipped, not counted)")
    for expect, _, _ in missing:                       # no silent caps — say what was dropped
        print(f"    skipped (absent from corpus): {expect}")
    if not present:
        print("None of the golden works are in this harvest — harvest more, or widen the set.")
        return 2

    cid = args.collection
    systems = {
        "visual-lib (routed)": lambda q: lib.search_discovery(q, k=20, collection_id=cid),
        "identity only":       lambda q: lib._search_discovery_identity(q, k=20, collection_id=cid),
        "clip only":           lambda q: lib._search_discovery_clip(q, k=20, collection_id=cid),
    }
    results = {}
    for kind_i, kind in enumerate(("look", "named")):
        for name, fn in systems.items():
            ranks = []
            for expect, look, named in present:
                q = (look, named)[kind_i]
                ranks.append(_hit_rank([h.asset.title for h in fn(q)], expect))
            results[(kind, name)] = ranks

    if not args.no_baseline:
        from nolan.image_search import ArtInstituteProvider
        prov = ArtInstituteProvider()
        for kind_i, kind in enumerate(("look", "named")):
            ranks = []
            for expect, look, named in present:
                q = (look, named)[kind_i]
                try:
                    res = prov.search(q, max_results=20)
                except Exception as e:
                    print(f"    baseline error on {q!r}: {e}")
                    res = []
                ranks.append(_hit_rank([r.title for r in res], expect))
            results[(kind, "BASELINE artic keyword")] = ranks

    print(f"\nrecall@1 / recall@{args.k} / recall@10   (n={len(present)} needs per row)")
    table = {}
    for (kind, name), ranks in results.items():
        row = (_recall(ranks, 1), _recall(ranks, args.k), _recall(ranks, 10))
        table[f"{kind}:{name}"] = {"recall@1": row[0], f"recall@{args.k}": row[1],
                                   "recall@10": row[2],
                                   "found": sum(1 for r in ranks if r is not None)}
        print(f"  {kind:<6} {name:<24} {row[0]:>5.1f}  {row[1]:>5.1f}  {row[2]:>5.1f}")

    print("\nper-need rank (visual-lib routed vs baseline), lower is better, '-' = not found:")
    for i, (expect, _, _) in enumerate(present):
        for kind in ("look", "named"):
            vl = results[(kind, "visual-lib (routed)")][i]
            bl = results.get((kind, "BASELINE artic keyword"), [None] * len(present))[i]
            print(f"  {kind:<6} {expect[:38]:<40} visual-lib={str(vl or '-'):>3}  baseline={str(bl or '-'):>3}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(
            {"corpus": corpus, "needs": len(present), "skipped": [m[0] for m in missing],
             "table": table}, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
