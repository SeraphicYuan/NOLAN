# Clip Selector Report — Venezuela Documentary

## Summary
- B-roll scenes total: **24**
- Matched (kept): **4**
- Flagged & cleared: **0** b-roll, **3** non-b-roll (matcher overreach)
- Unmatched: **20** b-roll

The vector index was empty on first attempt; ran `nolan sync-vectors --project venezuela` (172 segments / 118 clusters from 2 of the 3 source documentaries) and re-ran the matcher. Note: the *Hugo Chavez — Venezuela's Savior or Destroyer* documentary listed in the style guide does **not** appear in the synced index — only the *Why The US & Venezuela Are On The Brink of War* and *Venezuela's Dark Secret* docs were processed. This is the dominant cause of the low match rate.

## B-roll matches kept (sanity-checked vs style guide)
| Scene | Match | Notes |
|---|---|---|
| Hook/scene_004 (0:16, 6s) — poverty/unrest/brink | protest footage, sim 0.68 | OK; adjacent to text-overlay (Maria quote) so visual-type variety holds |
| Context/scene_008 (2:05, 13s) — oil defining the country | "VENEZUELA ES TUYA" sign with pumpjack icon, sim 0.69 | OK; reasonable closing beat for Context |
| Evidence 2/scene_006 (5:55, 15s) — Chávez rises 1998 | Chávez addressing crowd (blue suit, not red beret), sim 0.70 | OK; style guide requires library footage for living/named political figures, and this is rally footage not a sit-down talking-head. Two consecutive b-roll (with scene_005 Caracazo) is within the ≤2 rule |
| Conclusion/scene_004 (8:45, 7s) — political fragmentation recap | protest with flags + "leader behind bars" banner, sim 0.69 | Acceptable but borderline on neutrality — banner reads as opposition framing. Recommend balancing the surrounding Chávez/Maduro coverage in next pass |

## Flagged & removed (non-b-roll matches the matcher should not have made)
| Scene | Original visual_type | Reason |
|---|---|---|
| Hook/scene_003 (0:10, 6s) | generated-image | Library clip was an off-topic "digital screens" segment; visual_type reserves this for symbolic glitch transition |
| Thesis/scene_002 (2:24, 8s) | text-overlay | One of the four structural "here's the key insight" beats; style guide mandates dedicated typography, not library footage |
| Conclusion/scene_007 (9:15, 13s) | text-overlay | Fourth "here's the key insight" spine beat; same rule |

## Unmatched b-roll (20) — coverage gaps
Grouped by what the library should have supplied per style guide vs. what's actually missing:

**Style guide says library has coverage; matcher still failed (likely missing or below-threshold):**
- Caracas street life / skyline contrast — Conclusion/scene_001
- Oil infrastructure (Maracaibo, pumpjack, refineries) — Thesis/scene_005, Evidence 3/scene_001, Conclusion/scene_003
- Maduro speech footage — Evidence 3/scene_005
- Opposition protests / Caracazo — Thesis/scene_003, Evidence 2/scene_005, Evidence 2/scene_008
- Migration exodus — Evidence 3/scene_004
- Empty shelves / shortages — Evidence 3/scene_003
- 1980s austerity / barrios — Evidence 2/scene_004
- 1970s oil-boom Caracas — Evidence 2/scene_001

**Library genuinely thin (use generated-image fallback in next pass):**
- Angel Falls / Los Roques — Hook/scene_001, Hook/scene_002
- Spanish galleon / colonization — Context/scene_003
- Vintage 1900s coffee/cocoa farming — Context/scene_006
- 1920s oil gusher (Gómez era) — Evidence 1/scene_003
- Betancourt 1950s archival — Evidence 1/scene_005
- Andes / Mérida contemplative — Conclusion/scene_006
- Diverse Venezuelan portraits — Conclusion/scene_008

## Patterns / recommendations for next pass
1. **Re-index the Hugo Chavez "Savior or Destroyer" documentary** — it's named in the style guide but absent from the vector DB; would likely fix several of the Chávez/Maduro/protest gaps.
2. **Lower `--min-similarity`** (currently 0.5) or raise candidate count for the 1970s/1980s/Caracazo beats — those topics may exist in the library but score below threshold against the verbose visual_descriptions.
3. **Re-plan the truly thin beats as `generated-image`** (Angel Falls, galleon, 1920s gusher, Betancourt, llanos portraits) per the style guide's "lean heavier than template default on generated-image."
4. The Conclusion/scene_004 protest match should be balanced against a pro-government rally clip if available, to honor the style guide's neutrality rule.
