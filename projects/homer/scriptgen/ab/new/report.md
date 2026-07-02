# Run Report — Homer scriptgen (v2 AUTO, ab/new)

## Configuration
- **Mode:** auto (writer chose the angle — brief left `angle` and `pivot` empty)
- **Subject:** Homer / The Odyssey
- **Style:** `channel-great-books-explained` ("Great Books Explained") — its **How to Apply** block used as the drafting system prompt. Style governs voice/structure only; sources govern facts.
- **Target:** ~8.0 min / ~1,200 words
- **Process:** single-pass v2 — ground facts -> propose & choose angle -> draft -> fact-check -> report.

## Sources used (all fetched)
| ID | Title | Words | Notes |
|----|-------|-------|-------|
| S1 | THE ODYSSEY - The Entire Story (Deep Dive History) | 22,175 | **Large — chunk-read** via offset/limit windows (never read whole). |
| S2 | The Odyssey Explained in 25 Minutes | 5,437 | Plot spine. |
| S3 | 荷马史诗是伪作？起底西方伪史论 (Chinese) | 564 | **Counter-source.** Presents the forgery ("伪史论") charge and rebuts it (Wolf, Troy, Linear B, oral-formulaic theory). |
| S4 | What Is the Real Meaning Behind The Odyssey? | 4,282 | Interpretation & craft. |

Total source corpus: **32,458 words** ground -> **31 checked claims** in the draft.

## Angle
**Chosen — Angle 1: "The Odyssey has no author, and that absence is the key that unlocks it."**
Why it won: it is the only candidate whose spine *is* the strongest scholarly evidence we hold (S3's Homeric Question + S4's oral-composition account), so the mandated counter-source becomes the argument's engine rather than an obstacle. It also does something unique to this subject — it takes the channel's signature "biographical determinism" move, shows it breaking (there may be no single Homer), and redirects it: the "life" that determines the poem is the *oral tradition*, mirrored in Odysseus, a hero of many disguises and borrowed names.

**Rejected (one line each):**
- *Angle 2* — "One reckless boast doomed Odysseus to ten years at sea": tight and tragic, but narrower; doesn't need the S3 material.
- *Angle 3* — "The famous monsters are a story Odysseus tells about himself": strong hidden-detail, but a device more than a thesis — folded into the draft as one beat instead.
- *Angle 4* — "Coming home beats being a hero": warm and true, but the most conventional reading — used as the closing turn, not the spine.
- *Angle 5* — "Odysseus's real equal is Penelope": excellent, but sidelines the author/authenticity question that the counter-source demands — woven into the close.

## Draft
- **Narration word count:** ~1,315 words (~9.6% over the ~1,200 target).
- **Runtime:** **7:58** at the narration rate implied by the 8:00 slate (~165 wpm); ~8:46 at a slower 150 wpm.
- **Beats:** 7 — Hook · Thesis · The Homeric Question · The Man of Many Turns · The Monsters He Alone Reports · The Forgery Charge & Answer · Close.
- **Format:** Director-ready — `# Video Script`, `**Total Duration:**`, `## <Beat> [t]` sections.

## Fact-check tally
- Verified: **24**
- Claimed (single-source / interpretive): **4**
- Disputed (used as contested): **1**
- **Source-backed total: 29 / 31** checked claims
- needs-check (flagged, non-load-bearing): **2** (*polytropos*; Wolf's first name)
- **Challenges facts woven in:** the full "Forgery Charge" beat + the Homeric-Question setup — the forgery argument is stated fairly, then answered with Troy, Linear B, and oral-formulaic evidence.

## Use of the S3 counter-source
S3 is not a footnote here — it is a **structural pillar**. It supplies the whole "Homeric Question" spine (Wolf 1795, the writing problem) and the entire "Forgery Charge & Answer" beat: the pseudo-history claim, its rhetorical trick, and the rebuttal evidence (Schliemann/Calvert/Troy, Linear B / Ventris 1952, the composite epic dialect, the Dream-of-the-Red-Chamber analogy, "between myth, literature and remembered history"). The draft states the forgery charge honestly ("if we cannot even prove Homer existed...") before answering it.

## Notes / caveats
- Style vs. length: the style guide's native length is 15-25 min; the brief caps this at ~8 min, so the braided structure is compressed into 7 beats. Voice and the biographical-mirroring move are preserved (redirected onto the tradition).
- The channel's non-negotiable "author's life -> the text" move is deliberately foregrounded *as broken*, then transformed — a knowing, style-aware choice rather than a violation.
- Minor source discrepancy (composition date: ~700 BC in S4 vs "2,800 years ago" in S1/S2) avoided by not pinning a single date in narration.
- The opening proem line is a paraphrase, not attributed to a specific translator (no translation was in the sources).
- Nothing outside `ab/new/` was touched; `ab/old/` left untouched.
