---
id: common.pairing-craft
name: Pairing craft
kind: craft
purpose: The narrative->asset pairing umbrella — every operator (literal, knowledge, tonal, conceptual, ironic, trait, relational, scale) with when-to-use guidance.
status: active
version: 1
documents:
  module: src/nolan/evoke_broll.py
handoffs: []
uses: []
evals: []
---

# Pairing craft — the narrative→asset umbrella

The registry of record is `OPERATORS` in `src/nolan/evoke_broll.py` — this
document is honesty-tested against it. Every operator follows the same arc:
bridge (turn the line into the right kind of query) -> retrieve (search +
library tiers) -> gate (vision judges against the operator's criterion) ->
accept. Operators marked *automated* are judgment-safe and run unattended in
the asset engine's bridge (`bridge_queries`); the rest are lab/human-review
operators on /broll and /scenes. Fuller design: docs/NARRATIVE_ASSET_PAIRING.md.

Picking rule of thumb: concrete subject -> literal (or knowledge when the
REAL named work exists); no concrete subject -> tonal for feeling,
conceptual for mechanism; the line sets up a contrast -> relational
(split-screen) or ironic (undercut); a big number -> scale (stat-over).

## literal

**What:** Plain depiction — the frame literally shows the thing named.

**When:** Default for concrete subjects (a ship, a map, a battle). No bridge; fails on abstractions.

## knowledge

**What:** Name the SPECIFIC real asset (a particular artwork/artifact/place) from model knowledge, then verify it.

**When:** History/art topics where the genuine named work beats generic stock — 'the Prima Porta Augustus', not 'a roman statue'. Pair with identity verification.

## tonal

**What:** Mood b-roll — atmosphere (color, light, composition) evokes the line's emotion, never illustrates it. *(automated bridge)*

**When:** Abstract or emotional lines with no concrete subject; interior states; breathing room between arguments.

## conceptual

**What:** Visual metaphor — a subject/action whose mechanic mirrors the concept's. *(automated bridge)*

**When:** Abstract mechanisms (inflation, feedback, decay). Must read at a glance; reject tired clichés (chess boards, handshakes).

## ironic

**What:** Counterpoint — footage that CONTRADICTS the line to expose the gap between what's said and what's real.

**When:** Editorial beats where undercutting lands the point harder than illustrating. Human-review the picks: irony misfires easily.

## trait

**What:** Embodiment — an exemplary activity that reads as the named character trait.

**When:** Character description (cunning, discipline, hubris) with no literal footage — show a person OF that quality doing the telling thing.

## relational

**What:** One side of a dialectical pair — retrieved per side, composed as a split-screen collision.

**When:** Then/now, rich/poor, promise/cost juxtapositions the narration sets up. Feeds the split-screen motion; both sides must read at half width.

## scale

**What:** Tangible referent for a big number — a countable mass or vast space with calm room for a count-up overlay.

**When:** Big abstract quantities the audience should FEEL. Feeds the stat-over motion; the frame needs quiet negative space for the number.
