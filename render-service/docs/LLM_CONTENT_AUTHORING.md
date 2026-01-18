# LLM Content Authoring Guide

This guide explains how to write content for the NOLAN render service so that styles and accents are applied correctly. Follow these rules to produce visually consistent video essays.

## Quick Reference

```
Style Selection:   { "style": "noir-essay" }
Accent Markup:     "The **$47 billion** deal shocked everyone"
Auto-Accent:       Numbers, dates, percentages, money are auto-detected
```

## 1. Style Selection

### Available Styles

| Style ID | Best For | Tone |
|----------|----------|------|
| `noir-essay` | Philosophy, history, analysis | Cinematic, serious |
| `cold-data` | Tech, finance, geopolitics | Clean, technical |
| `modern-creator` | YouTube, mixed topics | Contemporary, versatile |
| `academic-paper` | Research, education | Scholarly, formal |
| `documentary` | Journalism, investigations | Neutral, serious |
| `podcast-visual` | Interviews, discussions | Warm, conversational |
| `retro-synthwave` | Music, nostalgia, 80s content | Neon, energetic |
| `breaking-news` | Current events, news | Urgent, broadcast |
| `minimalist-white` | Products, tutorials | Clean, Apple-like |
| `true-crime` | Mystery, suspense | Dark, dramatic |
| `nature-documentary` | Environment, wildlife | Earthy, organic |

### Choosing a Style

Match the style to your content's tone:

```json
// Philosophy video about consciousness
{ "style": "noir-essay", "title": "What Is **Consciousness**?" }

// Tech explainer about AI
{ "style": "cold-data", "title": "How GPT-4 Works" }

// True crime documentary
{ "style": "true-crime", "title": "The **1987** Disappearance" }
```

## 2. Accent Markup Syntax

### Basic Syntax

Use double asterisks to mark words for accent coloring:

```
"The **$2.3 billion** acquisition changed everything"
"In **1969**, humanity reached the moon"
"Sales increased by **47%** in Q3"
```

### Rules

1. **Max words per title**: 1-2 words (style-dependent)
2. **Max words per body text**: 2-3 words (style-dependent)
3. **No full sentences**: Never accent an entire sentence
4. **No consecutive accents**: Space them out for impact

### Good Examples

```
GOOD: "The company lost **$4.7 billion** in a single quarter"
GOOD: "**73%** of respondents disagreed"
GOOD: "The **2008** financial crisis"
```

### Bad Examples

```
BAD: "**The company lost money**"           // Too many words
BAD: "**$4.7 billion** and **$2.1 billion**" // Too many accents
BAD: "The **amazing incredible** result"    // Adjectives, not data
```

## 3. Auto-Accent Targets

When a style is applied, certain patterns are automatically detected and may be accented:

| Target | Pattern | Example |
|--------|---------|---------|
| `numbers` | Standalone numbers | "over 500 million users" |
| `dates` | Years, date formats | "in 1969", "March 2024" |
| `percentages` | Percent values | "increased 47%" |
| `money` | Currency amounts | "$2.3 billion", "€500" |
| `caps` | ALL CAPS words | "the FBI investigation" |

### How Auto-Accent Works

If you don't use `**markup**`, the system will auto-accent based on the style's `allowedTargets`:

```json
// Input without markup
{ "text": "Revenue hit $4.7 billion in 2023" }

// With noir-essay style (allows numbers, dates, money)
// Output segments: "Revenue hit " + "$4.7 billion" (accented) + " in " + "2023" (accented)
```

### Explicit vs Auto

- **Explicit (`**word**`)**: Always accented, overrides auto-detection
- **Auto**: Only accents if the style allows that target type
- **Combine**: Use explicit for specific emphasis, let auto handle the rest

```json
// Explicit control over what gets accented
{ "text": "The **hidden** cost: $4.7 billion" }
// "hidden" is accented (explicit), "$4.7 billion" may or may not be (depends on style)
```

## 4. Content Structure for Effects

### Quote Effects

```json
{
  "effect": "quote-fade-center",
  "params": {
    "text": "The only way to do **great** work is to love what you do",
    "author": "Steve Jobs",
    "style": "minimalist-white"
  }
}
```

### Kinetic Typography

```json
{
  "effect": "quote-kinetic",
  "params": {
    "style": "modern-creator",
    "phrases": [
      { "text": "**$47 billion**", "hold": 0.8 },
      { "text": "vanished overnight", "hold": 0.6 },
      { "text": "No one saw it coming", "hold": 0.7 }
    ]
  }
}
```

### Statistics

```json
{
  "effect": "stat-counter-roll",
  "params": {
    "value": 47000000000,
    "prefix": "$",
    "suffix": "",
    "label": "Total Losses",
    "style": "cold-data"
  }
}
```

### Title Cards

```json
{
  "effect": "title-card",
  "params": {
    "title": "Chapter 1: The **Beginning**",
    "subtitle": "How it all started",
    "style": "noir-essay"
  }
}
```

## 5. Style-Specific Guidelines

### noir-essay
- Max 1 accent per title, 2 per body
- Accent numbers, dates, money
- Avoid emotional adjectives
- Use for serious, analytical content

### cold-data
- Max 2 accents per title, 3 per body
- Focus on data: numbers, percentages, money
- Keep language precise and neutral
- Avoid metaphors and emotional language

### modern-creator
- Max 2 accents per title and body
- More flexible with accent targets
- Can accent caps and explicit words
- Good for mixed-tone content

### breaking-news
- Use uppercase titles (auto-applied)
- Max 2 accents, focus on key facts
- Accent names (caps), dates, numbers
- Keep text short and punchy

### true-crime
- Slow, deliberate pacing
- Accent dates and key names
- Use dramatic pauses (longer holds)
- Avoid casual language

## 6. Common Patterns

### Data Reveals

```json
{
  "effect": "quote-kinetic",
  "style": "cold-data",
  "phrases": [
    { "text": "The real number?", "hold": 0.8 },
    { "text": "**$47 billion**", "hold": 1.2 },
    { "text": "Gone.", "hold": 0.6 }
  ]
}
```

### Historical Context

```json
{
  "effect": "title-chapter",
  "style": "noir-essay",
  "params": {
    "number": "1969",
    "title": "The **Moon** Landing"
  }
}
```

### Breaking News Ticker

```json
{
  "effect": "data-ticker",
  "params": {
    "essayStyle": "breaking-news",
    "items": [
      { "text": "DOW drops 500 points" },
      { "text": "Fed announces rate hike" },
      { "text": "Tech stocks tumble 3.2%" }
    ],
    "label": "BREAKING"
  }
}
```

## 7. Validation Errors

The system will throw errors for:

1. **Too many accents**: "Accent limit exceeded (max 2 words for titles)"
2. **Invalid patterns**: "Accent contains forbidden pattern: full sentence"
3. **Style not found**: Falls back to `noir-essay`

### Handling Errors

If you get an accent error, reduce the number of accented words:

```json
// Error: too many accents
{ "text": "**This** is **really** **important**" }

// Fixed: one accent
{ "text": "This is really **important**" }
```

## 8. Best Practices Checklist

- [ ] Choose style that matches content tone
- [ ] Use `**markup**` sparingly (1-2 words max)
- [ ] Accent data, not opinions
- [ ] Let auto-accent handle obvious patterns
- [ ] Test with the `/styles/:id/resolve-accent` endpoint
- [ ] Keep phrases short for kinetic effects
- [ ] Match style to your video's overall aesthetic

## 9. Testing Your Content

Use the styles API to test accent resolution:

```bash
curl -X POST http://localhost:3010/styles/noir-essay/resolve-accent \
  -H "Content-Type: application/json" \
  -d '{"text": "The **$47 billion** deal in 2023", "isTitle": false}'
```

Response shows how text will be segmented and colored:

```json
{
  "result": {
    "segments": [
      { "text": "The ", "accent": false },
      { "text": "$47 billion", "accent": true },
      { "text": " deal in ", "accent": false },
      { "text": "2023", "accent": true }
    ],
    "accentCount": 2
  }
}
```

## 10. Quick Decision Tree

```
Is it a number, date, percentage, or money?
├─ Yes → Usually auto-accented, markup optional
└─ No → Need explicit **markup** for accent

Is it more than 2 words?
├─ Yes → Don't accent it
└─ No → OK to accent if impactful

Is it an emotional adjective?
├─ Yes → Don't accent (except modern-creator)
└─ No → OK to accent

Is it a full sentence?
├─ Yes → Never accent
└─ No → Check word count
```

---

*This guide is for LLMs generating content for the NOLAN video essay render service.*
