"""topdocumentaryfilms.com — a CURATED INDEX over YouTube/Vimeo, not a content host.

Every entry resolves to a video hosted elsewhere, so this is a DISCOVERY adapter in the shape of
``archive_source``: it produces survey rows and nothing else. Ingest, transcripts, keyframes and
search all reuse the existing YouTube path unchanged — the ``kind`` only namespaces the survey and
the coverage lane.

Two sources of truth, deliberately:

* **The WordPress REST API** (``/wp-json/wp/v2/posts``) carries the editorial metadata — title, the
  human-written synopsis, category, release year, director, star rating, and ``runtime`` IN MINUTES.
  That last one matters: the length filter can only bite when a row has a duration, and archive rows
  carry one just 14% of the time. Here it is structured metadata on every documentary.
* **The rendered page** carries the video id and NOTHING ELSE we need. The theme injects the player
  at render time, so the id is absent from the API — verified: not in ``content.rendered``, not in
  ``meta``, not in ``yoast_head_json``, not as a bare string anywhere in the payload.

So the crawl is ~31 cheap JSON calls plus one page fetch per documentary, and the page fetch is the
only part that has to be paced.

**Why a browser at all.** The site is behind a Cloudflare managed challenge: every plain HTTP
request 403s, including the ``sitemap.xml`` that robots.txt itself advertises, and a full browser
header set does not help. Measured: ``page.goto`` clears it (headless included), but an in-page
``fetch()`` does not — Cloudflare separates navigation from XHR and ``Sec-Fetch-*`` cannot be set
from JS. A fresh browser context sustains only ~2 navigations before being challenged, and pacing
does not change that (2/10 at both 1s and 3s), so the context is RECYCLED rather than slowed down.
The API, by contrast, is not challenged at all.

robots.txt permits everything used here (it disallows only /docpot/, /cdn-cgi/, /doubleclick/,
/forum/ and wp-admin / wp-login).
"""
from __future__ import annotations

import html as _html
import json
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

SITE = "https://topdocumentaryfilms.com"
API = f"{SITE}/wp-json/wp/v2"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# Navigations a fresh context reliably serves before Cloudflare challenges it. Measured at 2; the
# context is rebuilt on the challenge itself, so this is only how often we pre-empt one.
_NAV_PER_CONTEXT = 2
_BLOCK = ("image", "media", "font", "stylesheet")

# The player is a lazy-load facade: a thumbnail plus an SVG play button, with the real id already in
# the HTML. Two independent routes to it — the theme's embed <meta>, and the thumbnail inside
# .youtube-player — so they can be cross-checked instead of trusted singly.
_EMBED_META = re.compile(
    r'<meta[^>]+content="[^"]*?(?:youtube(?:-nocookie)?\.com/embed/([A-Za-z0-9_-]{11})'
    r'|player\.vimeo\.com/video/(\d+))', re.I)
_PLAYER_BLOCK = re.compile(r'<div[^>]+class="[^"]*youtube-player[^"]*"[^>]*>(.{0,1200}?)</div>', re.I | re.S)
_YTIMG = re.compile(r'i\.ytimg\.com/vi/([A-Za-z0-9_-]{11})')
_VIMEO_ANY = re.compile(r'(?:player\.)?vimeo\.com/(?:video/)?(\d+)')
# A MULTI-PART documentary is embedded as a playlist: `embed/videoseries?list=<PL...>`. The literal
# marker `videoseries` is exactly 11 characters, so it satisfies a YouTube-id pattern and reads as a
# perfectly ordinary id — it silently cost 190 films (8%) before the thumbnail cross-check caught it.
_PLAYLIST_MARKER = "videoseries"
_PLAYLIST_ID = re.compile(r'[?&]list=([A-Za-z0-9_-]+)')
_TAG = re.compile(r"<[^>]+>")


def watch_url(host: str, vid: str) -> str:
    """The canonical player URL — what yt-dlp is handed for captions and duration."""
    return f"https://www.youtube.com/watch?v={vid}" if host == "youtube" else f"https://vimeo.com/{vid}"


def extract_video(page_html: str) -> Optional[Dict[str, str]]:
    """``{host, video_id, watch_url}`` from a rendered documentary page, or None when the page has no
    player at all — which is how a blog post or a listicle identifies itself (verified: those carry
    no embed meta, no player and zero ytimg ids, while every documentary page carries all three).

    The embed <meta> wins; the ``.youtube-player`` thumbnail confirms it. A page-wide ytimg scan is
    NOT a fallback worth having on its own — a documentary page also carries thumbnails for two
    RELATED videos, so a bare regex picks a neighbouring film about two thirds of the time. It is
    used only to corroborate, or when scoped inside the player element.
    """
    m = _EMBED_META.search(page_html)
    meta_id = (m.group(1) or m.group(2)) if m else None
    meta_host = "youtube" if (m and m.group(1)) else ("vimeo" if m else None)

    # Playlist embed: the meta names no video at all. The player's thumbnail is the first part, which
    # is the entry point the page itself presents; the playlist id is kept so the rest is recoverable.
    playlist = None
    # NOTE for the length filter: on a playlist row the API's `runtime` describes the WHOLE series
    # (e.g. 13,500s across five parts) while `video_id` is part one (2,683s). The row therefore reads
    # longer than the video an ingest would actually fetch.
    if meta_id == _PLAYLIST_MARKER:
        pl = _PLAYLIST_ID.search(page_html[m.start():m.end() + 220]) if m else None
        playlist = pl.group(1) if pl else None
        meta_id = None

    player = _PLAYER_BLOCK.search(page_html)
    scoped = player.group(1) if player else ""
    thumb = _YTIMG.search(scoped)
    thumb_id = thumb.group(1) if thumb else None
    if not thumb_id and scoped:
        v = _VIMEO_ANY.search(scoped)
        thumb_id = v.group(1) if v else None

    vid, host = meta_id, meta_host
    if vid is None:
        if not thumb_id:
            return None
        vid = thumb_id
        host = "vimeo" if (_VIMEO_ANY.search(scoped) and not thumb) else "youtube"
    elif thumb_id and thumb_id != vid:
        # the two routes disagree — refuse rather than pick one and be wrong silently
        return {"host": host, "video_id": vid, "watch_url": watch_url(host, vid),
                "conflict": thumb_id}
    out = {"host": host, "video_id": vid, "watch_url": watch_url(host, vid)}
    if playlist:
        out["playlist"] = playlist
    return out


def _text(fragment: str) -> str:
    return _html.unescape(_TAG.sub(" ", fragment or "")).replace("\xa0", " ").strip()


def parse_post(post: Dict[str, Any], terms: Dict[int, str]) -> Dict[str, Any]:
    """One REST post → the editorial half of a survey row (everything but the video id)."""
    meta = post.get("meta") or {}
    runtime = str(meta.get("runtime") or "").strip()
    try:
        dur = int(float(runtime)) * 60 if runtime else None
    except ValueError:
        dur = None
    subject = [terms[t] for t in (post.get("categories") or []) if t in terms]
    for t in (post.get("release") or []):
        if t in terms:
            subject.append(terms[t])
    if meta.get("director"):
        subject.append(str(meta["director"]))
    body = _text((post.get("content") or {}).get("rendered", ""))
    return {
        "slug": post.get("slug") or "",
        "page_url": post.get("link") or "",
        "title": _text((post.get("title") or {}).get("rendered", "")),
        "description": re.sub(r"\s+", " ", body)[:4000],
        "duration": dur,
        "subject": subject,
        "director": str(meta.get("director") or ""),
        "rating": str(meta.get("ratings_average") or ""),
        "date": (post.get("date") or "")[:10],
    }


class _Session:
    """A browser that recycles its context around Cloudflare's per-context navigation budget."""

    def __init__(self, pw, headless: bool = True):
        self._b = pw.chromium.launch(headless=headless)
        self._ctx = None
        self._page = None
        self._used = 0

    def _fresh(self):
        if self._ctx is not None:
            try:
                self._ctx.close()
            except Exception:
                pass
        self._ctx = self._b.new_context(user_agent=UA, locale="en-US",
                                        viewport={"width": 1280, "height": 900})
        self._page = self._ctx.new_page()
        self._page.route("**/*", lambda r: r.abort()
                         if r.request.resource_type in _BLOCK else r.continue_())
        self._used = 0

    def get(self, url: str, timeout: float = 45000) -> Tuple[int, str]:
        """``(status, body)``. A challenged response rebuilds the context and retries ONCE, so a
        challenge costs a page rather than silently returning the challenge HTML as content."""
        for attempt in (1, 2):
            if self._page is None or self._used >= _NAV_PER_CONTEXT:
                self._fresh()
            try:
                resp = self._page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                self._used += 1
                body = self._page.content()
                status = resp.status if resp else 0
            except Exception:
                self._used = _NAV_PER_CONTEXT           # force a rebuild next time round
                if attempt == 2:
                    return 0, ""
                continue
            if "Just a moment" in body or status == 403:
                self._used = _NAV_PER_CONTEXT
                if attempt == 2:
                    return 403, ""
                continue
            return status, body
        return 0, ""

    def json(self, url: str) -> Any:
        status, body = self.get(url)
        if status != 200:
            return None
        m = re.search(r"<pre[^>]*>(.*?)</pre>", body, re.S)
        raw = _html.unescape(m.group(1)) if m else _text(body)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def close(self):
        try:
            self._b.close()
        except Exception:
            pass


def load_terms(sess: _Session) -> Dict[int, str]:
    """``{term_id: name}`` for the taxonomies we fold into `subject` (category + release year)."""
    out: Dict[int, str] = {}
    for tax in ("categories", "release"):
        for page in range(1, 6):
            rows = sess.json(f"{API}/{tax}?per_page=100&page={page}")
            if not rows or not isinstance(rows, list):
                break
            for t in rows:
                if isinstance(t, dict) and t.get("id"):
                    out[int(t["id"])] = _text(str(t.get("name") or ""))
            if len(rows) < 100:
                break
    return out


def survey_since(known_urls: set, delay: float = 1.0,
                 progress: Optional[Callable[[str], None]] = None,
                 headless: bool = True) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Only what is NEW: the API returns posts newest-first, so stop at the first one already held.

    A full pass is ~70 minutes of paced browser navigation. This is the difference between a Sync
    button that is usable and one that is a trap — and it is cheap because the expensive half (the
    per-documentary page fetch) is paid only for genuinely new rows.

    Returns the same `(rows, stats)` shape as `survey_collection`; the caller merges by page_url.
    """
    from playwright.sync_api import sync_playwright

    def say(msg):
        if progress:
            progress(msg)

    rows: List[Dict[str, Any]] = []
    stats = {"scanned": 0, "new": 0, "no_video": 0, "unreachable": 0, "hosts": {},
             "stopped_at_known": False}
    with sync_playwright() as pw:
        sess = _Session(pw, headless=headless)
        try:
            terms = load_terms(sess)
            fresh: List[Dict[str, Any]] = []
            for page_no in range(1, 40):
                batch = sess.json(f"{API}/posts?per_page=100&page={page_no}&_fields="
                                  "id,slug,link,title,content,meta,categories,release,date")
                if not batch or not isinstance(batch, list):
                    break
                stats["scanned"] += len(batch)
                hit_known = False
                for post in batch:
                    if post.get("link") in known_urls:
                        hit_known = True                 # newest-first, so everything after is held
                        continue
                    if str((post.get("meta") or {}).get("runtime") or "").strip():
                        fresh.append(post)
                say(f"api page {page_no}: {len(fresh)} candidates")
                if hit_known:
                    stats["stopped_at_known"] = True
                    break
                if len(batch) < 100:
                    break
                time.sleep(delay)

            for post in fresh:
                meta = parse_post(post, terms)
                status, page_html = sess.get(meta["page_url"])
                if status != 200 or not page_html:
                    stats["unreachable"] += 1
                    time.sleep(delay)
                    continue
                vid = extract_video(page_html)
                if not vid or vid.get("conflict"):
                    stats["no_video"] += 1
                else:
                    stats["hosts"][vid["host"]] = stats["hosts"].get(vid["host"], 0) + 1
                    rows.append({
                        "video_id": vid["video_id"], "url": vid["watch_url"], "title": meta["title"],
                        "duration": meta["duration"], "subject": meta["subject"], "license": "",
                        "copyright_free": False, "description": meta["description"],
                        "host": vid["host"], "playlist": vid.get("playlist", ""),
                        "page_url": meta["page_url"], "director": meta["director"],
                        "rating": meta["rating"], "date": meta["date"]})
                time.sleep(delay)
        finally:
            sess.close()
    stats["new"] = len(rows)
    return rows, stats


def survey_collection(limit: Optional[int] = None, delay: float = 1.0,
                      progress: Optional[Callable[[str], None]] = None,
                      headless: bool = True,
                      checkpoint: Optional[Callable[[List[Dict[str, Any]], Dict[str, Any]], None]] = None,
                      every: int = 100) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """``(rows, stats)`` — every documentary on the site, in the shape the transcript library's
    survey machinery already consumes.

    Rows are keyed by the HOST's video id, so a documentary already ingested from a YouTube channel
    crawl dedupes against itself rather than arriving twice.

    `stats` reports every drop, because a survey that quietly returns fewer rows than the site holds
    is indistinguishable from a small site: `no_video` (a blog post or listicle — the site mixes them
    in), `unreachable` (the page 403'd or timed out past its retry), and `conflict` (the embed meta
    and the player thumbnail named different videos, so neither was trusted).
    """
    from playwright.sync_api import sync_playwright

    def say(msg):
        if progress:
            progress(msg)

    rows: List[Dict[str, Any]] = []
    stats = {"posts": 0, "no_video": 0, "unreachable": 0, "conflict": 0, "total": 0,
             "hosts": {}, "unreachable_slugs": [], "conflict_slugs": []}
    with sync_playwright() as pw:
        sess = _Session(pw, headless=headless)
        try:
            terms = load_terms(sess)
            say(f"{len(terms)} taxonomy terms")
            posts: List[Dict[str, Any]] = []
            for page_no in range(1, 60):
                batch = sess.json(f"{API}/posts?per_page=100&page={page_no}&_fields="
                                  "id,slug,link,title,content,meta,categories,release,date")
                if not batch or not isinstance(batch, list):
                    break
                posts.extend(batch)
                say(f"api page {page_no}: {len(posts)} posts")
                if limit and len(posts) >= limit * 4:      # over-fetch: most posts are not documentaries
                    break
                if len(batch) < 100:
                    break
                time.sleep(delay)
            stats["posts"] = len(posts)

            # `meta.runtime` is a strong, FREE documentary filter: measured 100/100 on recent API
            # pages and 56-73/100 on the oldest, while blog posts and listicles never carry one. The
            # page fetch is the only rate-limited step, so screening here is most of the crawl budget.
            docs = [p for p in posts if str((p.get("meta") or {}).get("runtime") or "").strip()]
            stats["skipped_no_runtime"] = len(posts) - len(docs)
            say(f"{len(docs)} of {len(posts)} posts carry a runtime — fetching those pages only")

            for i, post in enumerate(docs):
                if limit and len(rows) >= limit:
                    break
                meta = parse_post(post, terms)
                status, page_html = sess.get(meta["page_url"])
                if status != 200 or not page_html:
                    stats["unreachable"] += 1
                    if len(stats["unreachable_slugs"]) < 25:
                        stats["unreachable_slugs"].append(meta["slug"])
                    time.sleep(delay)
                    continue
                vid = extract_video(page_html)
                if not vid:
                    stats["no_video"] += 1              # blog post / listicle — not a documentary
                elif vid.get("conflict"):
                    stats["conflict"] += 1
                    if len(stats["conflict_slugs"]) < 25:
                        stats["conflict_slugs"].append(meta["slug"])
                else:
                    host = vid["host"]
                    stats["hosts"][host] = stats["hosts"].get(host, 0) + 1
                    rows.append({
                        "video_id": vid["video_id"], "url": vid["watch_url"],
                        "title": meta["title"], "duration": meta["duration"],
                        "subject": meta["subject"], "license": "", "copyright_free": False,
                        "description": meta["description"], "host": host,
                        "playlist": vid.get("playlist", ""),
                        "page_url": meta["page_url"], "director": meta["director"],
                        "rating": meta["rating"], "date": meta["date"],
                    })
                if i % 25 == 0:
                    say(f"{len(rows)} documentaries / {i+1} posts scanned")
                # a full pass is hours of paced fetching; hand the caller partial results so a crash
                # at the end costs one interval rather than the whole crawl
                if checkpoint and rows and len(rows) % every == 0 and i:
                    stats["total"] = len(rows)
                    checkpoint(rows, stats)
                time.sleep(delay)
        finally:
            sess.close()
    stats["total"] = len(rows)
    return rows, stats
