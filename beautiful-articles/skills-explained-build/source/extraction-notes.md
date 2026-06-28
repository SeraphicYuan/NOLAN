# Extraction Notes

- **Input type:** URL (https://claude.com/blog/skills-explained), Next.js rendered HTML page (~545 KB raw).
- **Extraction method:** `scripts/source-to-markdown.py` (lightweight, BeautifulSoup) on saved `original.html`, then manual cleanup.
- **Source language:** English. Target language: English (user unspecified → follow source). No translation step.
- **Confidence:** High. Body text, headings (h1–h4), bullet lists, and all code blocks captured intact.

## Known gaps / reconstructions

1. **Comparison table ("Comparison: choosing the right tool"):** The original had a styled
   comparison table/component under "How they work together" that did NOT survive HTML extraction
   (only the heading remained). **Reconstructed** a 5-row table (Prompts / Skills / Projects /
   Subagents / MCP × what-it-is / persistence / when-to-use) directly from the article's own
   prose descriptions of each building block. This is faithful to the source content, not invented.
   Flag for user awareness at planning.

## Noise stripped (not part of article)

- Page nav / header / cookie UI.
- Footer: "Agent Skills" CTA, "Related posts" (4 links), "Transform how your organization
  operates with Claude", developer-newsletter signup form.
- Inline "Learn more about X" / "Check out our library" promotional links inside body were
  trimmed where they were pure navigation; substantive sentences kept.

## Carriers preserved

- Code blocks: security-review prompt, GDrive-navigation Skill example, market-researcher +
  technical-analyst subagent configs. All intact with indentation.
- Lists: all when-to-use bullet groups preserved.
