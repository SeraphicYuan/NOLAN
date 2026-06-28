# Step 2: select_clips

Claude CLI elapsed: 698.7s, events: 851

## Report

# Clip Selector Report — Football Beyond War

Run: `nolan match-clips ./scene_plan.json -p football-beyond-war-qwen --candidates 5 --skip-existing`
Matcher result: 3 new matches, 164 no-match, 127 skipped (existing). Only 0 of the 3 new
matches landed on b-roll scenes — all b-roll matching was done in prior passes.

## Counts (b-roll only)
- Total b-roll scenes: **122**
- Matched: **61**
- Flagged (match removed): **1**
- Unmatched: **61**

## Flags (1)
- **Section_38_scene_004** — duplicate of Section_38_scene_006. Both pulled the identical source
  segment 1172.7–1177.6s (the US/Iran "split-screen deadlock / communication bridge" shot), only
  two scenes apart. scene_006 is a near-perfect fit (0.95) for that segment; scene_004 reused it for
  a weaker, generic "mediator / Israel–Hamas news montage" beat (0.8). Removed scene_004's match,
  kept scene_006. Needs distinct coverage for the "mediator" beat.

## Editorial review — no other conflicts found
- **Talking-head / intercut rule:** clean. Several matches' reasoning *mentions* narrator/host
  candidates (S26, S27, S36), but in every case the matcher **rejected** the talking-head shot and
  chose proper archival b-roll (e.g. S26 chose the Helmut Schön archival photo over a narrator
  studio shot). The "host" hits are about *hosting* the World Cup, not on-camera hosts.
- **Neutrality / restraint:** the Nazi/FC-Start material (S16, S25, S42) uses documentary archival
  footage (Death-Match ceremony, German officers in the stands, 1944 season) — period-accurate, no
  partisan caricature. Consistent with the style guide. Left as-is.
- **Cross-section clip reuse:** the same source segments recur across the film — e.g. 745–749s used
  4×, 458–463s and 524–527s 3× each. All are minutes apart in runtime (different sections/beats), so
  acceptable; not flagged. Only the within-section S38 pair was close enough to repeat visibly.

## Unmatched (61) — what library footage would have helped
- Ancient/origins **17** (Episkyros, Cuju, Pok-A-Tok, Mayan reliefs, stickball) — no archive exists;
  these belong on the `generated` pipeline, not b-roll.
- FIFA/economics **13** (stadiums, Qatar/Saudi spend, prize pool) — better served by `graphics`
  data cards per the style guide; library has thin stadium coverage.
- WWI / 1914 truce **11** (trenches, no-man's-land, gift exchange) — genuine archival gap.
- WWII / FC Start **4**, generic crowds/match **7**, 2026 US–Iran **1**, other **7**.

## Patterns
- **Single-source library.** All 61 b-roll matches come from one indexed video — the original essay
  `為什麼足球，能超越戰爭？.mp4`. There is no external archival footage indexed, so coverage for WWI/WWII
  archival, ancient games, and FIFA stadiums is structurally weak and reuse of the same segments is
  unavoidable. Recommend indexing dedicated archival/stadium sources, or routing the ancient-origins
  and FIFA-finance unmatched scenes to `generated` / `graphics` rather than chasing b-roll matches.

