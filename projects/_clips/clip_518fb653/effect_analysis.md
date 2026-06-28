# Effect Analysis — clip_518fb653

Source: `The Mystery Of The Samurai In Venice.mp4` @ 389.13s → 399.5s (10.37s)

## Effect

A documentary **"photos on a table" montage** (scrapbook / evidence-board style):

- **Setting plate:** several historical illustration cards laid on a textured dark-**burgundy
  velvet/felt** surface. Each card has a **Polaroid-style white border** with a soft **drop
  shadow**, placed at slight, varied **rotations** (≈ ±5–10°) and overlapping.
- **Camera move:** a slow, continuous **parallax glide** across the tabletop — a gentle
  **pan + slight zoom-in** (Ken Burns on the whole composite), drifting from the woodblock-print
  card toward the incoming card. No cut; one smooth move across the 10s.
- **Hero card animation:** a new Polaroid (the *Tokugawa Ieyasu* armored-samurai illustration)
  **slides/settles into frame** from the right and scales up to rest near center (frames 5→10),
  landing on top of the stack with its shadow.
- **Handwritten caption:** the name **"Tokugawa Ieyasu"** appears in a **handwriting/script font**
  in the white bottom border of the hero Polaroid (fades/writes in as the card settles, frames 7→10).
- Slightly warm, aged color grade on the cards; no other text or graphics.

Net: it's a *compound* effect — textured tabletop + multiple Polaroid stills + global Ken Burns
camera + one sliding labeled card.

## Dedup result

**Not covered by any single registered effect.** Checked the full `nolan.motion` REGISTRY (13
effects) and `src/nolan/renderer/scenes/`. The closest pieces only cover sub-parts:

| Existing | Backend | Covers | Gap vs. this clip |
|---|---|---|---|
| `ken-burns` (`KenBurnsRenderer`) | python | slow zoom/pan on **one** still | single image only — no multi-card composite |
| `portrait-reveal` (`portrait_reveal.py`) | python | portrait slides aside → text reveal | clean dark studio layout, 1 portrait + bullets; not a polaroid tabletop collage |
| `flashback` (`FlashbackRenderer`) | python | vintage/sepia/grain/vignette on a still | supplies the *aged look* only, not layout or motion |
| `lower-third` / `TypeWriter` | python | caption text | clean lower-third, not an in-frame handwritten polaroid label |
| effects.py primitives | python | `SlideRight`, `MoveTo`, `ScaleIn`, `RotateIn`, `ShadowIn`, `BlurIn` | the building blocks for the card slide-in + shadow exist, but nothing assembles them into the montage |

So the **individual ingredients exist** (global Ken Burns camera, Slide/Scale/Rotate/Shadow
primitives, Flashback texturing, BaseRenderer/Element compositing) but the **assembled
"Polaroid photo-table montage with a sliding labeled card" is NEW**.

## Replicable? — **Yes (high confidence). Backend: Python.**

This is fundamentally **still-image compositing on a textured plate** — exactly NOLAN's Python
renderer wheelhouse, and it reuses primitives already in the repo. Python is the pragmatic choice
because `KenBurnsRenderer`, `effects.py` (Slide/MoveTo/RotateIn/ShadowIn), `FlashbackRenderer`,
and `BaseRenderer`/`Element` compositing are all already Python and directly composable.

*Remotion is a viable premium alternative* (crisper polaroid drop-shadows, real handwriting webfont,
true per-layer parallax) — recommend it only if we later want a glossier version; not needed for a
faithful reproduction.

## Plan (Python)

1. **New scene renderer** `src/nolan/renderer/scenes/photo_montage.py` → `PhotoMontageRenderer`.
   - **Inputs:** `background` (texture path or burgundy color `(60,15,20)`), `cards: list[{image_path,
     x, y, rotation_deg, scale, polaroid: bool, caption: str|None}]`, `hero_index` (the card that
     slides in), `camera` (`zoom_start/zoom_end`, `pan_direction` — reuse Ken Burns params),
     `caption_font` (a handwriting TTF), `duration`.
   - **Polaroid frame:** pad each card with a white border + soft drop shadow via existing
     `ShadowIn` / a blurred-alpha plate; apply slight `rotation_deg`.
   - **Aged look (optional):** route card images through `FlashbackRenderer`'s grade for the warm
     vintage tone.
2. **Reuse, don't reinvent the camera:** composite the static stack (background + non-hero cards)
   onto one large RGBA canvas, then run **`KenBurnsRenderer` over that canvas** for the global
   pan+zoom. Composite the **hero card as a separate animated layer per frame**
   (`SlideRight` + `ScaleIn` + `ShadowIn`) on top, and the **handwritten caption** with
   `TypeWriter`/`FadeIn` in a script font. This maximizes reuse and keeps the math proven.
3. **Register** in `src/nolan/motion/registry.py`:
   `MotionEffect(id="photo-montage", backend="python", target="PhotoMontageRenderer",
   category="image", ...)` with shared params (duration/theme) + per-effect params (cards,
   hero_index, camera, background, caption). The executor (`nolan.motion.executor.render`)
   dispatches on `backend="python"`, so the new row makes it spec-renderable immediately.
4. **Verify:** `scripts/test_photo_montage.py` rendering 2–3 sample cards → assert 1920×1080,
   expected duration, non-empty motion (frame diff > threshold across the camera move).
5. **Document (Promoting Techniques convention):** update `IMPLEMENTATION_STATUS.md` template
   count and add a row:

   | Technique | Template/Effect | File | Date |
   |-----------|-----------------|------|------|
   | Polaroid photo-table montage + sliding labeled card | `photo-montage` (`PhotoMontageRenderer`) | `scenes/photo_montage.py` | 2026-06-26 |

**Effort:** moderate — ~1 renderer (~150–200 lines) that mostly orchestrates existing primitives,
plus a registry row and a test. No new backend or infra.

## Promoted to NOLAN

Implemented 2026-06-26. Spec id `photo-montage` (python) renders end-to-end via
`nolan.motion` (validate → executor), no validation errors. Test passes (1920×1080,
correct duration, motion verified). The hero card slides in and the handwritten caption
types on as designed.

| Technique | Template/Effect | File | Date |
|-----------|-----------------|------|------|
| Polaroid photo-table montage + sliding labeled card | `photo-montage` (`PhotoMontageRenderer`) | `src/nolan/renderer/scenes/photo_montage.py` | 2026-06-26 |
| (registry row) | `photo-montage` python row | `src/nolan/motion/registry.py` | 2026-06-26 |
| (test) | `test_photo_montage.py` | `scripts/test_photo_montage.py` | 2026-06-26 |
| Irregular cutout mode (transparent PNG silhouette + shadow) | `frame:"cutout"` on `PhotoMontageRenderer` | `src/nolan/renderer/scenes/photo_montage.py` | 2026-06-26 |
| **Flexible per-card motion montage** (each card: rest pos + entrance edge/timing/easing; polaroid/plain/cutout; Ken Burns) | `photo-montage-pro` → `PhotoMontage` (Remotion) | `render-service/remotion-lib/src/PhotoMontage.tsx` | 2026-06-26 |
| (registry rows) | remotion row + `registry.json` entry | `src/nolan/motion/registry.py`, `render-service/remotion-lib/registry.json` | 2026-06-26 |
| (multi-image staging) | stage `cards[].src` + `background` | `render-service/remotion-lib/render.mjs`, `src/nolan/remotion_source.py`, `src/nolan/motion/executor.py` | 2026-06-26 |
| (demo/test) | `test_photo_montage_remotion.py` | `scripts/test_photo_montage_remotion.py` | 2026-06-26 |

**Per-card motion schema** (the "well-defined system"): each card sets where it *rests*
(`x, y, scale, rotation`) and how it *arrives* (`from`: left/right/top/bottom/center/none,
`enterAt`, `enterDur`, `distance`, `ease`: out/inOut/spring, `fromScale`) independently —
so "from the bottom to the middle", "from the left to the left", "from the right to the
right" are all just data. Extensible: add `from` modes, exit tracks, motion paths, blend
modes as more sample clips define them.
