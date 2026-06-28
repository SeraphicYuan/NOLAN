# Extraction Notes — HUMAN 3.0

- **Input:** URL (thedankoe.com/letters/human-3-0-a-map-to-reach-the-top-1/), ~108 KB HTML.
- **Method:** `source-to-markdown.py` (bs4) + manual cleanup. Source language English; target English.
- **Confidence:** High for text; one visual not reproducible (see below).

## Cleanup applied
- **De-duplicated highlighted callouts.** The site renders key passages twice — once as a
  blockquote "highlight" and once as inline prose. The extractor captured both; I kept one
  flowing version each and preserved the most quotable ones as `>` blockquotes (candidates for
  PullQuote in the build).
- **Stripped non-article chrome:** top newsletter signup ("Not A Subscriber? Join 120,000+…"),
  inline "Subscribe for further…" CTAs, and the footer promo ("When You're Ready, Here's How I
  Can Help You" / The Art of Focus book / "Who Is Dan Koe?").

## Known gap
- The article references a **"Human 3.0 Graph"** image (a quadrant map with plotted development
  points / "the opaque white shape on the map"). The image itself wasn't extractable. The model
  is fully described in text, so the build will **represent** it with figures (a 2×2 quadrant
  CardGrid + Level/Phase StepFlows) rather than reproduce the exact graphic. Flag at planning.

## Genre / retention
- Genre: a personal **philosophy / self-development essay** that also lays out a structured
  framework (Quadrants / Levels / Phases / Traits / Channels; Archetypes / Metatypes).
- Suggested type `essay`, kept rich (~85%) because the framework's structure is the value —
  trim only the duplicated callouts + promo (already done), keep the model intact.
