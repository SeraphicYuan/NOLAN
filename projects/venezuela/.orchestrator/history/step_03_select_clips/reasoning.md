# Step 3: select_clips

Claude CLI elapsed: 834.2s, events: 2403

## Report

# Clip Selector Report — Venezuela Documentary

## Tally

- **B-roll scenes total:** 25 (of 72 scenes)
- **Matched (kept):** 8
- **Flagged & cleared:** 2
- **Unmatched:** 15

Matcher ran across all 72 scenes (planner left `library_match: true` on every scene); 26 scenes including non-b-roll types received clips. Out of scope for this pass — left untouched. Note for downstream: text-overlay / generated-image / graphic scenes carry stray `matched_clip` values that should be ignored by the renderer based on `visual_type`.

## Flags applied

| Scene | Time | Reason |
|-------|------|--------|
| scene_046 | 5:43 | Anachronism — matched clip features Hugo Chavez framing, but scene narrates 1980s pre-Chavez austerity. Conflicts with style guide's chronology and non-partisan posture. |
| scene_057 | 7:17 | Duplicate-source — pulled the same original segment (1050.93-1068.33 of "Brink of War") already assigned to scene_002 in the Hook; reusing the same "shuttered businesses" shot for two different narrative beats. Matcher itself admitted no actual supermarket-shelf footage. |

## Unmatched b-roll (library coverage gaps)

Three clusters of missing footage stand out:

**Pristine landscape / closing aerials (4 scenes)**
- scene_001 (0:00) — Angel Falls / Gran Sabana / coastline aerial
- scene_064 (8:19) — landscape echo for Conclusion open
- scene_071 (9:30) — civic life: community meeting, market, classroom
- scene_072 (9:38) — final landscape aerial at dusk

**Pre-1990s archival (7 scenes)** — the indexed library skews modern.
- scene_038 (4:30) — 1950s/60s Betancourt-era civic life
- scene_040 (4:48) — 1976 oil nationalization ceremony
- scene_042 (5:03) — 1970s Caracas construction boom
- scene_043 (5:13) — 1970s schools / hospitals / families
- scene_046 (5:43) — 1980s austerity bread lines (flagged above)
- scene_047 (5:53) — 1989 Caracazo riots
- scene_051 (6:31) — 2002 coup attempt, opposition vs pro-Chavez rallies

**Specific contemporary shots (6 scenes)**
- scene_004 (0:19) — Caracas market street, woman walking from behind
- scene_008 (0:45) — montage: rally → empty supermarket → skyline
- scene_021 (2:25) — Caracas neighborhood inequality tracking
- scene_027 (3:04) — Venezuelan flag, neutral, low-light, no crowd
- scene_057 (7:17) — empty-shelves / pharmacy queues (flagged above)
- scene_062 (8:03) — government motorcade through struggling barrio

## Patterns

- **Library is strongest for 1998–present political coverage**: Chávez 1998 (scene_049), 2014 oil crash (055), Maduro era (059), Guaidó 2019 (060) all matched cleanly with confidence ≥0.85.
- **Library is weak for**: pristine Venezuelan nature, pre-1990s archival of any kind, neutral/symbolic single shots (flag-still, motorcade, civic quiet). Style guide already anticipates this for pre-1900 (calls for generated-image fallback) but the 1950s–1989 gap is wider than the guide acknowledged.
- **Source-clip concentration risk**: the 18 b-roll matches that the matcher proposed across all visual_types lean heavily on a small handful of segments inside "Why The US & Venezuela Are On The Brink of War" (notably 1050.93–1068.33 and 920–1000). Future passes should diversify or downstream cuts will feel repetitive.

## Recommendation for next pass

The 7 pre-1990s and 4 closing-landscape gaps are the highest-impact unmatched set. Style guide already authorizes generated-image fallback for pre-photographic eras; extending that to 1950s–1989 (where library is empty) and to closing landscape beats (scene_001, 064, 072) would close most of the gap without re-indexing.

