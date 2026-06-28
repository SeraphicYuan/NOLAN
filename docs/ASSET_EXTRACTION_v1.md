# Asset Extraction — v1 (link → assets)

Date: 2026-06-25. A new acquisition channel: given a **page URL**, extract the
highest-definition image assets it embeds/links. Complements the API-provider
search (`image_search.py`) and the indexed-video path — those answer "find me
images *about X*"; this answers "*grab the images on this page*".

## What it does

A registry of parsers. Site-specific extractors run first; a universal HTML
extractor is the fallback. Each returns
[`ImageSearchResult`](../src/nolan/image_search.py) objects — the same unified
type the rest of NOLAN consumes — so extracted assets flow straight into
scoring / download / assemble.

```python
from nolan.extractors import extract_from_url, download_assets
assets = extract_from_url("https://www.gutenberg.org/files/21790/21790-h/21790-h.htm")
# -> [ImageSearchResult(url=".../illus-048.jpg", thumbnail_url=".../p048-t.png", ...), ...]
```

## Parsers

| Extractor | Matches | High-def strategy |
|---|---|---|
| `gutenberg` | `*.gutenberg.org` | Books wrap a thumbnail in `<a href>` to the full illustration (`<a href="images/illus-048.jpg"><img src="images/p048-t.png">`) → take the href. |
| `wikimedia` | `*.wikimedia.org`, `*.wikipedia.org` | Collect every `upload.wikimedia.org` URL; map thumbnails (`/thumb/.../960px-Name.jpg`) to the original (`/.../Name.jpg`). |
| `met` | `metmuseum.org/art/collection` | Pages are JS-rendered; read the object ID from the URL and call the public collection API for `primaryImage` (full-res) + `additionalImages`. |
| `archive` | `archive.org/details|download|embed/<id>` | Read the identifier; call `archive.org/metadata/{id}`; emit `download/...` URLs for the original image files (skip auto thumbnails). |
| `loc` | `loc.gov/item|resource|pictures|collections` | Append `?fo=json`; `item.image_url` is a size-ordered list (last = largest); strip LoC's `#h=&w=` dimension fragment into width/height. |
| `iiif` | URL has `/iiif/`, or ends `manifest.json` / `info.json` | **One parser, many institutions.** Parses Presentation manifests (v2 `sequences`/`canvases`, v3 `items`) → one image/canvas, and Image API `info.json` → a single max-res image. Builds `{base}/full/{max\|full}/0/default.jpg` (v2 → `full`, 2.1+/3 → `max`). On an HTML viewer page, discovers the embedded manifest URL and fetches it. |
| `web` (fallback) | anything | `<a href>`-wraps-`<img>` → largest `srcset` → `<img src>`; plus `og:image`/`twitter:image` hero; resolve relatives; drop icons/logos/sprites/data-URIs and tiny declared dimensions; dedup. |

**Why IIIF matters:** it's the standard digital libraries and museums use to serve
images, so a single parser unlocks a whole class of GLAM archives (national/university
libraries, many museums) that the generic extractor only sees thumbnails of. Note: IIIF
is a *delivery* standard, not a search API — there is no global "search IIIF" endpoint,
so it lives here as an extractor, not as an `image_search.py` provider.

Adding a site = drop a `BaseExtractor` subclass in `src/nolan/extractors/` and
list it in `EXTRACTORS` (before the generic fallback).

## Surfaces

**CLI**
```bash
nolan extract-assets <url> [-n LIMIT] [-o DIR] [--no-download]
# Gutenberg book illustrations:
nolan extract-assets https://www.gutenberg.org/files/21790/21790-h/21790-h.htm
# one full-res Wikimedia original, preview only:
nolan extract-assets https://commons.wikimedia.org/wiki/File:The_Blue_Marble.jpg -n 1 --no-download
```
Downloads to `.scratch/extracted/<host>/` and writes `manifest.json`.

**Hub UI** — `/extract` (card on the home page). Paste a URL → **Preview**
(lists found assets in a gallery, no download) or **Extract & Download**
(background job → saves full-res + manifest). Endpoint: `POST /api/extract-assets`
(synchronous preview, or `download:true` to start a job).

## Resolve — upgrade search thumbnails to full-res

Aggregators (DPLA especially) return a thumbnail in `url` plus the item's landing
page in `source_url`. `resolve_result` / `resolve_results` (in `extractors/`)
upgrade these, two tiers, both best-effort (never lose data on failure):

1. **Deterministic URL rewrite** of the thumbnail itself — e.g. ContentDM/OCLC
   `utils/getthumbnail/collection/{c}/id/{n}` → IIIF `digital/iiif/{c}/{n}/full/max/0/default.jpg`,
   verified to actually serve an image.
2. **Source-page extraction** — run `source_url` through the extractor registry
   and take the best image (largest, or `og:image`/canonical first).

Then any sized IIIF URL is bumped to `/full/max/` (`_maximize_iiif`) — this turns a
page's `/full/730,/` derivative into the true original.

Exposed as `nolan image-search <q> -s dpla --resolve`. Measured on DPLA: ~9/12
results upgraded, e.g. Calisphere 150px thumbnails → **5562×4350** IIIF originals,
ContentDM previews → 3307×2502. The ~3 that don't upgrade are JS-only viewers
(NYPL, NARA catalog) with no extractable full-res — pair those with the institution's
API if needed. DPLA is best treated as a **discovery** source; resolve closes much of
the gap to full-res.

## Design notes

- **No new dependency** — HTML is parsed with the stdlib `html.parser`
  (`extractors/html_utils.py`), not BeautifulSoup.
- **Linked-over-embedded is the core heuristic**: a thumbnail wrapped in an
  `<a>` pointing at an image is the single most reliable hi-res signal, and is
  near-universal (galleries, MediaWiki, WordPress, Gutenberg).
- `fetch_html` retries on transient timeouts (the Windows-side network is flaky).

## Verified (live)

- Gutenberg 21790 → 50 illustrations, `illus-048.jpg` full-res with `p048-t.png`
  thumbnail; downloaded a real 750×1178 @300 DPI JPEG.
- Wikimedia *Blue Marble* → full original (non-thumb) + archive revisions.
- Met object 436535 → `primaryImage` via API.
- IIIF v3 cookbook book → 5 canvases at `full/max`; v3 single-image; Image API
  `info.json` → max-res URL with real dims (3204×4613).
- Internet Archive image item → original `download/...` JPEG.
- LoC item 2021669449 → full-res `tile.loc.gov` image with parsed dimensions.
- 26 unit tests (`tests/test_extractors.py`, network-free) + in-process hub
  route test (preview, validation, download job).

## Limits / follow-ups

- No vision **scoring** wired in yet (results carry the fields; `image-search`'s
  `ImageScorer` could rank them).
- Met is the only API-backed extractor; other JS-heavy museum sites need their
  own parser or an API path.
- Wikimedia returns older `archive/` revisions alongside the current original —
  fine, but noisier than necessary.
- Extract-into-a-project-pool (vs `.scratch`) is a follow-up; v1 lands files in
  `.scratch/extracted/<host>` with a manifest.
