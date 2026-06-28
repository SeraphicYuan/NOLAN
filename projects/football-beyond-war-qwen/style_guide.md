# Style Guide: Football Beyond War

A polished, accessible-but-rigorous video essay tracing how one instinct — putting a ball on the ground and moving it with the body — recurs across isolated ancient civilizations and then, across 112 years, lets sworn enemies share the same pitch. Explainer-documentary hybrid for a general audience that wants the history, the geopolitics, and the human weight without academic distance. Runtime is long-form (~23 minutes), so the guide is tuned for sustained narrative momentum, not a tight 10-minute explainer.

> **Adaptation note:** This guide descends from the Essay-Doc Explainer template. The structural moves (paradox-open, numbered thesis, recurring cadence, intercut imagery, visual section markers) are inherited. The surface — every example, the cadence phrase, the visual vocabulary, the pacing math — is specific to this project's subject and its 294-scene plan.

## Voice

Conversational essayist with a documentary narrator's gravity. Addresses the viewer directly and often pulls them into the reasoning ("To understand the true weight of this, consider...", "You may not realize it, but...", "So, you can imagine..."). Complex history and FIFA economics are made approachable through plain language, concrete numbers, and a steady accumulation of stories. Educational posture, not advocacy: the script analyzes *why* football defuses conflict — Jules Rimet's "channel the conflicts of the modern world into peaceful competition" — without taking sides on any of the wars it depicts (WWI, WWII, U.S.–Iran, Israel–Hamas). Preserve that neutrality.

Recurring rhetorical moves actually present in this script:
- **Open on a paradox or arresting fact.** The film opens on isolated ancient peoples "who would never meet" independently inventing the same pointless game; reuse that instinct-is-pre-programmed hook energy at section starts.
- **Rhetorical question → plain answer.** The script's dominant engine is "Why? Because..." (e.g., "Why was this considered a miracle?", "Is that why everyone scrambles to host the World Cup?", "Don't they know they're going to lose money? Of course they do."). Let visuals land on the answer beat, not the question.
- **Number the thesis explicitly.** The spine is literally counted: football has united warring parties "three times in the past 112 years — in 1914 through human nature, in 1942 through resistance, in 2026 through FIFA." Echo this three-act count whenever the structure resurfaces.
- **Recurring cadence phrase:** use **"It has only happened three times in 112 years"** and its companion refrain **"as long as the ball is still rolling / as long as the whistle still blows, we have not regressed into beasts."** These are the script's own load-bearing repetitions — do *not* substitute the template's "here's the key insight," which never appears here.
- **Quote named real people sparingly for human texture:** the Johns Hopkins sports historian Victoria Harms, FIFA president Gianni Infantino, Jules Rimet, the German soldier's "Merry Christmas, I have no gun," FC Start's "Long live sport!", the Londoner's wartime diary. One or two per section, no more.
- **End on reflection, not a verdict.** Close on the ancients who "would surely feel they had done a very fine thing indeed" — open-ended awe, never a partisan conclusion.

## Look

Cinematic, color-graded, premium documentary feel. The scene plan draws on five modes; ground every shot in what the library and generation pipeline can actually deliver (134 of 294 scenes already have a library match; 58 carry ComfyUI generation prompts).

- **Real footage from the indexed library (`b-roll`, 122 scenes, the backbone)** — archival war footage (WWI trenches, WWII bombing of London/Munich/Kyiv), historical and contemporary match footage, stadium crowds, World Cup ceremony, news imagery of the 2026 U.S.–Iran context. Prefer genuine archival material over stock-look b-roll wherever the library has it.
- **AI-generated conceptual imagery (`generated`, 57 scenes)** — for moments no archive exists: Episkyros on Greek sand, Roman Harpastum in the mud, Han-dynasty Cuju, the Maya Pok-A-Tok hoop, the 1914 football among shell craters, FC Start's defiant salute. Use generation when a symbolic, period-accurate composition lands harder than literal footage. Prompts lean cinematic and photorealistic, period-correct.
- **Information graphics (`graphics`, 83 scenes)** — the second pillar. Animated world maps (the three isolated inventions; the front lines), timelines (112 years, 1914 → 1942 → 2026), and data comparisons that carry the FIFA-economics back half: Qatar's $220B spend vs. <$4B return (55× loss), FIFA revenue 3.6B → 7.5B → projected 13B, the $440M player prize pool vs. FIFA's 17×, Saudi Arabia's $500B 2034 budget. Use existing infographic templates with the `docu-dark-minimal` dark theme already referenced in the scene plan.
- **Narrator-presenter scenes (`host`, 20 scenes / `a-roll`, 12 scenes)** — on-camera or driving-narration beats that anchor transitions between the three historical acts and the geopolitical present. Keep these short and always intercut; do not let them become sustained talking-heads.

There is no separate `text-overlay` visual type in this project — quotes, key-insight beats, and section labels are rendered as typographic layers *inside* `graphics` scenes (the scene plan attaches `infographic` blocks and `layers` rather than standalone text cards). Treat that as the convention.

## Pacing

Total runtime ~22:54 (1,374 s) across 294 scenes — average scene ~4.7 s, markedly faster and longer-form than the template's ~10-minute, 8–12 s baseline. Tune windows proportionally:

- **Hook (Sections 1–3, ~0:00–1:33)** — quick, montage-driven cuts (~4–5 s) across the five ancient games to dramatize simultaneous, disconnected invention.
- **The 2026 miracle (Sections 4–7)** — standard explanatory pacing; let the U.S.–Iran stakes and the Harms quote breathe slightly.
- **The three historical acts (Sections 8–20: 1914 Christmas Truce; 1942 FC Start)** — narrative pacing, slightly longer holds (~5–7 s) on the emotional peaks (the singing across the trenches, "Long live sport!", the 5–3 victory). These are the heart; don't rush them.
- **FIFA / geopolitics back half (Sections 21–40)** — graphics-forward, brisk on data reveals, with each statistic getting its own beat.
- **Synthesis (Sections 41–45)** — slowest holds (~7–8 s) so the closing reflection on writing, currency, and the ball lands.

Visual-type variety is enforced: no more than 2 consecutive scenes of the same `visual_type`. Each of the three historical acts and each major section break opens on a `graphics` marker (a timeline or map card) so the three-times-in-112-years spine stays legible.

## Editorial

- Quote named real people once or twice per section for human stakes (Harms, Infantino, Rimet, the FC Start cry, the Christmas-truce soldier, the Londoner's diary) — do not over-rely on them.
- Historical and economic sections lean on maps, timelines, and comparison graphics. The FIFA-finance stretch (Sections 33–40) is graphics-driven; give every figure ($15B Brazil, $220B Qatar, $500B Saudi, FIFA's 7.57B) its own clean data card.
- Mark key-insight moments (the three-times count; "a football match is a highly abstracted simulation of war"; "as long as the ball is still rolling") with dedicated typographic `graphics` beats, not narration alone.
- The thesis is explicitly three-part (1914 / 1942 / 2026). Echo it visually at each act's opening with a small section card naming the year and its mechanism (human nature / resistance / FIFA).
- Avoid sustained `host`/`a-roll` talking-heads — always intercut with archival or generated imagery.
- Match visual register to the narration's neutrality. The script depicts Nazis, the Christmas Truce, and the U.S.–Iran conflict without partisan framing — visuals should do the same. Symbolic and period-accurate compositions yes; political caricature no. Handle the FC Start / Nazi-salute and concentration-camp material with documentary restraint.

## Visual Type Vocabulary

Tuned to this project's actual scene plan (294 scenes). Distribution reflects what is planned, not the template defaults.

- `b-roll` — real footage from the indexed library (archival war, historical/contemporary matches, stadiums). **~42%** (122 scenes)
- `graphics` — information graphics and typographic cards (maps, 112-year timeline, FIFA data, quotes, section markers). **~28%** (83 scenes)
- `generated` — AI-generated period and symbolic imagery (ancient games, trench football, FC Start). **~19%** (57 scenes)
- `host` — on-camera presenter anchor beats. **~7%** (20 scenes)
- `a-roll` — narrator-driven framing beats. **~4%** (12 scenes)

Changes from the template vocabulary: the template's `generated-image` is named `generated` here; `text-overlay` is **dropped** as a standalone type (text lives in `graphics` infographic layers); `host` and `a-roll` are **added** to cover the presenter/narrator beats this project actually plans.

## Provenance

- **Descended from template:** `essay-doc-explainer-v1`, version 1 (match score 0.816 — exact genre match, strong text overlap).
- **Adaptation summary:** The template's structural skeleton stayed intact — paradox-open hook, explicitly numbered thesis, sparing named-quote texture, intercut-everything rule, visual section markers, and an open-ended reflective close. What changed is keyed to this specific film. The cadence phrase was replaced: the template's "here's the key insight" never occurs, so the script's own refrains — "three times in 112 years" and "as long as the ball is still rolling" — became the recurring cues. The visual vocabulary was rebuilt from the real 294-scene plan: `generated-image` → `generated`, the standalone `text-overlay` type dropped (text rendered inside `graphics` layers), and `host`/`a-roll` presenter types added; distributions were set from actual scene counts rather than template percentages. Pacing was re-tuned from the template's ~10-minute / 8–12 s baseline to this film's ~23-minute, ~4.7 s-average rhythm, with the longest holds reserved for the three historical acts and the closing synthesis. All examples — Episkyros and Pok-A-Tok, the 1914 truce, FC Start, the FIFA economics, the 2026 U.S.–Iran match — come from the script and scene plan; nothing was invented.
