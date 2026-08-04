# Test D — a ten-second collage, from a real script

The stress test for Claude Design as a **bespoke block engine**. Unlike tests A–C it has a
BENCHMARK: the same script and the same assets through the shipped `collage` block. So the question
is not "did it produce a collage" but "did it beat the craft already in the repo".

## The brief

> **Script (9.04s, real cloned VO):**
> *"A data centre never arrives alone. It brings a power meter, a water line, a zoning fight — and
> a bet the chips will earn it all back."*

Five subjects, each landing on its own spoken noun. Aligner-measured times:

| subject | noun | spoken at |
|---|---|---|
| `smart_meter` | meter | 3.40s |
| `water_glass` | water | 4.18s |
| `gavel` | zoning | 5.36s |
| `gpu_card` | chips | 7.26s |
| `cash_stack` | back | 8.40s |

The spacing is deliberately uneven and partly brutal — **meter→water is 0.78s apart**, zoning→chips
is 1.90s. There is no comfortable uniform stagger that satisfies this; each entry must be
word-anchored or it reads as random.

Theme `highlighter-editorial`, then re-rendered in a dark theme with **no source change**.
Own assets/animation may be mixed in with the pool cutouts where they earn their place.

## Assets

Pool JPGs cut to transparent PNGs by `prep_assets.py` (rembg). The prep carries a matte-quality
gate because rembg **fails silently**:

| asset | cover | blobs | largest blob | |
|---|---|---|---|---|
| cash_stack | 55.0% | 1 | 100% | clean |
| gavel | 27.1% | 1 | 100% | clean — low cover is honest for a thin diagonal object |
| gpu_card | 85.5% | 1 | 100% | clean |
| water_glass | 84.6% | 1 | 100% | clean |
| smart_meter | 56.8% | 3 | 41% | **multi-object** — five meters in a row; cropped to the largest |
| electric_bill | 12.7% | 10 | 24% | **BROKEN** — white paper on a light ground; rembg kept only the blue header bars and loose text. Dropped. |

Coverage alone does not discriminate (gavel 27% is fine, electric_bill 12.7% is not) —
**fragmentation** does, but it cannot auto-reject, because `smart_meter` is legitimately fragmented.
So a low largest-blob fraction FLAGS for review and a human decides.

## The verdict — six measurable checks

`verdict.mjs` seeks the paused timeline every 40ms and reads each subject's computed opacity and
bounding rect from the DOM. DOM-based, not pixel-based: exact where a pixel diff guesses, and it
names WHICH subject was late.

| check | rule |
|---|---|
| `anchor` | each subject's first visible frame within ±150ms of its noun |
| `no_exit` | visible ink monotonically non-decreasing — nothing animates out |
| `keep_out` | no non-ground content below 83% of frame height |
| `never_blank` | ink above a floor from the first entry onward |
| `all_present_at_end` | every subject visible at the end |
| `seek_safe` | two independent passes over the same times agree exactly |

## Baseline: the shipped `collage` block — 6/6

```
  ok   smart_meter  meter   3.40 -> 3.44  (+0.04)
  ok   water_glass  water   4.18 -> 4.20  (+0.02)
  ok   gavel        zoning  5.36 -> 5.40  (+0.04)
  ok   gpu_card     chips   7.26 -> 7.28  (+0.02)
  ok   cash_stack   back    8.40 -> 8.44  (+0.04)
```

**And it is visibly poor design** — five objects floating in a loose horizontal line, 10.4% image
area, dead space everywhere, no scale hierarchy, no overlap, no ground.

That is the useful shape of a benchmark: **the checks are necessary, not sufficient.** A submission
must hold 6/6 *and* beat this on composition. Passing the harness is the entry fee.

## Four harness defects found while calibrating — all mine, none the block's

Recorded because a stress test that is wrong about its own measurements is worse than no test.

1. **Sampling coarser than the tolerance.** 40 samples over 9.04s = 232ms resolution against a
   ±150ms bar — every anchor failed by +0.16..0.31s and the check could not have passed. Fixed to a
   40ms step.
2. **"Visible" measured at the midpoint.** Waiting for opacity > 0.5 reads the middle of a ~0.4s
   entry tween, so every subject looked systematically late. Now opacity > 0.02 = the entry has
   begun.
3. **Keep-out flagged the grounds.** The collage's own `clgbg`/`clgworld` are full-frame by
   definition. Keep-out governs content; anything covering ≥98% of the frame is a ground.
4. **The emptiness guard could not see a collage.** It counted `innerText`, and a collage is
   entirely images — it declared a perfectly good tableau empty. Now counts visible image area too.

Defects 1–3 would each have produced a FALSE FAILURE against any submission. Defect 4 would have
blocked publishing a correct one.
