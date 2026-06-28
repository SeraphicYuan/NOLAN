# Clip Selector Report — Venezuela Documentary (Refine pass 1)

## What this pass did
Applied two explicit asks from `review_2.md`: (1) re-planned the 8 library-thin beats from `b-roll` to `generated-image`, (2) re-ran the matcher with `--min-similarity 0.4 --candidates 8 --skip-existing` to recover the unmatched-but-should-exist beats. Net: visual-type counts moved from b-roll 24 / gi 15 to b-roll 16 / gi 23; matched b-roll grew from 4 → 6; two more matcher overreach incidents into non-b-roll types were caught and cleared.

## Visual-type redirects (b-roll → generated-image)
| Scene | Beat | Notes |
|---|---|---|
| Hook/scene_001 | Angel Falls | matched_clip already null, no clear needed |
| Hook/scene_002 | Los Roques | matched_clip already null |
| Context/scene_003 | Spanish galleon | matched_clip already null |
| Context/scene_006 | 1900s coffee/cocoa farmers | matched_clip already null |
| Evidence 1/scene_003 | 1920s oil gusher / Gómez era | matched_clip already null |
| Evidence 1/scene_005 | Betancourt 1950s archival | matched_clip already null |
| Conclusion/scene_006 | Andes / Mérida contemplative | matched_clip already null |
| Conclusion/scene_008 | Diverse Venezuelan portraits | matched_clip already null |

## Matcher re-run results (`--min-similarity 0.4 --candidates 8 --skip-existing`)
- 4 prior approved matches preserved via `--skip-existing` (Hook/scene_004, Context/scene_008, Evidence 2/scene_006, Conclusion/scene_004) ✓
- 2 new b-roll matches accepted after style-guide re-evaluation:
  - **Evidence 3/scene_005** (Maduro speaking) — sim 0.714, podium speech footage. Matches style guide's named-figure rule (library footage for living political figures) and "intercut, do not park" — clip is 10s, fine
  - **Conclusion/scene_001** (Caracas wealth/poverty contrast) — sim 0.662, barrio/favela hillside drone shot. Neutral and on-topic
- 2 new matches **flagged and cleared** (matcher overreach into non-b-roll types):
  - **Evidence 3/scene_008** (visual_type=graphic, planned tearing-flag animation) — matcher offered an unrelated migration-routes infographic as metaphor; style guide reserves `graphic` for purpose-built infographics
  - **Conclusion/scene_007** (visual_type=text-overlay, fourth "here's the key insight" spine beat) — matcher re-surfaced an unrelated digital-interface clip; rejected for the same reason as iteration 0

## Style-guide neutrality check
With Evidence 3/scene_005 added, Chávez/Maduro coverage is now: Chávez rally (Evidence 2/scene_006) + Maduro podium (Evidence 3/scene_005) + opposition protest (Conclusion/scene_004). That's balanced across the arc, satisfying the "footage of Chávez rallies and opposition protests should be balanced" rule. The Conclusion/scene_004 "leader behind bars" banner remains the one borderline-partisan visual; carrying that flag forward.

## Pacing side-effect — flagged for awareness, not changed
The user-directed redirects create two stretches of 3 consecutive `generated-image` scenes (Hook/001-003 and Context/002-004), exceeding the style guide's "no more than 2 consecutive scenes of the same `visual_type`" rule. These follow directly from the explicit feedback so I did not undo them, but the planner / next pass may want to swap a `text-overlay` or `graphic` into one of those slots to break the run.

## Out of scope (noted, not attempted)
- **Re-indexing the *Hugo Chavez — Savior or Destroyer* documentary** — still missing from the vector DB (only 2 of the 3 source docs were processed). Confirmed by the user as admin work outside this refine. Most likely cause of the remaining unmatched Chávez/protest beats; running `nolan index` on that source would probably close several of them.

## Remaining unmatched b-roll (after this pass)
14 b-roll scenes still without a match: Thesis/scene_003 (protests), Thesis/scene_005 (oil pumpjack), Evidence 2/scene_001 (1970s Caracas), Evidence 2/scene_004 (1980s austerity), Evidence 2/scene_005 (Caracazo), Evidence 2/scene_008 (2002 coup), Evidence 3/scene_001 (Lake Maracaibo), Evidence 3/scene_003 (empty shelves), Evidence 3/scene_004 (migrant exodus), Conclusion/scene_003 (oil pumpjack). Most would likely match if the third documentary were indexed; the rest may need their `visual_description` tightened in a future scene-edit pass.
