# Repair Log (Phase 7)

Applied after the three-reviewer Final Review (no blockers).

| # | Source | Change | File |
|---|--------|--------|------|
| 1 | Visual [FIX] + Editorial echo | Replaced the horizontally-clipped 4-column comparison `<Table>` with a `ComparisonGrid` card stack (one card per block; fields: persistence chip + "What it is" + "Reach for it when"). All content visible at `regular` width, on-theme. | 06-together.tsx |
| 2 | Editorial [FIX] | Added warm transition openers so they stop starting "cold". | 03-projects.tsx, 05-mcp.tsx |
| 3 | Editorial [NIT] | Added Hero meta row "Product: Claude apps · Claude Platform" (was dropped from source). | Article.tsx |
| 4 | Editorial [NIT] | Echoed the concrete token budgets (~100 tokens / under 5k) in body prose, not only the diagram. | 01-skills.tsx |
| 5 | Visual [NIT] | Added a subtle diagonal hatch to the RAG-headroom segment so it reads as "stretch", not an empty tile. | 03-projects.tsx |
| 6 | Visual [NIT] | Reduced track-card flex-basis 15rem→12rem so the three getting-started cards sit 3-up (was 2+1). | 08-getting-started.tsx |
| 7 | Editorial [NIT] | Removed the duplicate "takeaway" aside at end of §08 (the Conclusion right after says the same). | 08-getting-started.tsx |

Left intentionally: the deliberate per-section "when to use a Skill instead" motif; the illustrative extra subagents in §04's diagram; the soft-green result/takeaway asides (acceptable variety); §07's one immaterial dropped clause.
