# Second test: "The Three Players" (asset managers), 4 sources (~57s)

**Date:** 2026-06-25
**Span:** 10:35–11:32 of the source ("BlackRock, Vanguard, State Street… → voting
against buybacks would be voting against their own revenue")
**Output:** `final.mp4` (1920×1080, 57.2s, original VO)
**Purpose:** deliberately *un*friendly segment (contemporary, brand/people/abstract,
data-driven) to test generalization and surface new gaps. Added the **Lottie motion
library** as a 4th source.

## What worked

- **ComfyUI fills the gap where search is empty** — b3 boardroom plate (z-image:
  execs voting at a glass table) + composite lower-third = the standout shot. For a
  modern/abstract topic with no archival b-roll, generation is the lead visual source.
- **Renderers carry the data** — `CounterRenderer` (88%), `LineChartRenderer` reused
  for "fee revenue follows the market up", `ComparisonRenderer` for the profit-vs-vote
  conflict. Compositing + fades reused cleanly from the first experiment.

## Improvement areas surfaced (the point of this test)

1. **Lottie source is the weakest — and currently broken.** To even run it required
   five fixes: render-service was down; its port is 3010 (not the 3000 a stray FastAPI
   app answers); its `node_modules` is Windows-built so it must run under **Windows
   node**, not WSL; pipeline and service must be on the same OS side (networking); and
   the documented `nolan render-templates` driver sends a malformed payload (use
   `InfographicClient` w/ `engine=remotion, data={lottie_path}` instead). Even then, the
   rasterized lower-third (b4) came out as a near-blank light-gray frame **with no text**
   — the `headline` customization didn't render. Net: not usable yet. Also the
   data-callout Lottie exposes only colors (no settable number), so Python counters
   remain better for arbitrary stats.
2. **Title renderer clips long text** — "BLACKROCK · VANGUARD · STATE STREET" overflowed
   both edges (b1). Needs auto-fit / shrink-to-width (and wrapping).
3. **Segment search misfires on contemporary topics** — the index returned host
   talking-head and an unrelated indoor clip for "finance b-roll" (b1, b2 backgrounds),
   and some descriptions didn't match their frames. For modern/abstract spans the pool is
   thin and search should be deprioritized in favor of generation.
4. **No brand/logo handling** — text name-cards are the honest fallback (can't generate
   real logos), but they need the title auto-fit fix to look right.
5. **No relationship/loop diagram renderer** — the core idea (firms profit when stocks
   rise *and* vote for the buybacks that raise stocks) is a feedback loop; best we have is
   a side-by-side `ComparisonRenderer`. A circular/arrow "loop" renderer is the clearest
   missing piece for systemic-argument essays.

## Lottie — proper diagnosis & verdict (2026-06-25)

Gave the Lottie source a full diagnosis after the broken b4:
- The render-service rasterizer is `@lottiefiles/dotlottie-react` (ThorVG). It **does
  not render Lottie text layers** (`ty:5`) — proven by rendering `lower-thirds/modern.json`
  natively: only the solid bar appears, the headline text never does. The number-counter
  rendered earlier only because its digits are **vector shapes** (`ty:4`), not text.
- Output is **opaque** (h264) on a near-white comp background, so a Lottie clip **can't be
  composited** over b-roll the way our Python overlays can.
- `modern.json` is also a 1080×90 strip, not full-frame.

**The real fix** = swap the service's Lottie component to `@remotion/lottie` (lottie-web,
text-capable) + handle fonts + transparent output. That's Node/Remotion surgery on a
currently-working, Windows-built service — to enable text/transition Lotties that our
**Python renderers already do better and that actually composite**.

**Verdict: Lottie is not worth being the 4th source as-is.** The renderer suite (title,
lower-third, counter, comparison, line chart, **loop diagram**) + compositor covers the
need and composes properly. Keep the catalog as design inspiration; the working sources are
**segment search + ComfyUI + Python renderers/compositor**. (Two fixes from this test were
shipped: TitleRenderer auto-fit and LoopDiagramRenderer.)

## Comparative insight (vs. the Roaring Twenties test)

The asset-first **process generalizes**, but the **source mix must adapt to segment type**:
- Archival/historical → segment search + ComfyUI strong; renderers fill data.
- Contemporary/abstract/brand → search weak (host/news/movie clips); **ComfyUI leads**;
  renderers carry data; Lottie + brand + diagram gaps appear.

This directly informs the eventual `nolan build-from-segment` command: it should pick the
source mix based on segment type, not assume archival b-roll exists.
