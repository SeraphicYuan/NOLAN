"""topdocumentaryfilms adapter — the extraction rules, pinned against the page shapes actually
observed on the live site (see `tdf_source`'s module docstring for how each was established)."""

# The real player: a lazy-load facade — thumbnail + inline SVG play button, id already in the HTML.
# A documentary page ALSO carries thumbnails for two related films, which is the trap this pins.
DOC_PAGE = """
<html><head>
<meta property="og:image" content="https://i.ytimg.com/vi/4EdMImlZE2s/maxresdefault.jpg">
<meta itemprop="embedURL" content="https://www.youtube-nocookie.com/embed/4EdMImlZE2s?iv_load_policy=3&autoplay=1">
</head><body>
<div id="post-content"><div><div class="youtube-player"><div class="player-content">
  <img src="https://i.ytimg.com/vi/4EdMImlZE2s/maxresdefault.jpg" alt="How Hoover Dam Works">
  <svg role="img" aria-label="Play"><circle cx="12"/></svg>
</div></div></div>
<p>Constructed between 1931 and 1936, the Hoover Dam stands as a monumental achievement.</p></div>
<aside class="related">
  <img src="https://i.ytimg.com/vi/ZZJPnAer7EM/hqdefault.jpg">
  <img src="https://i.ytimg.com/vi/ofI03X9hAJI/hqdefault.jpg">
</aside></body></html>
"""

# A listicle / blog post: no embed meta, no player, zero ytimg ids. This is how the site's
# non-documentary posts identify themselves — 93 of 100 on the first API page.
LISTICLE = """
<html><head><meta property="og:image" content="https://media.topdocumentaryfilms.com/x.jpg"></head>
<body><div id="post-content"><p>The best psychology documentaries to watch right now.</p>
<a href="https://topdocumentaryfilms.com/the-century-of-the-self/">The Century of the Self</a>
</div></body></html>
"""

VIMEO_PAGE = """
<html><head>
<meta itemprop="embedURL" content="https://player.vimeo.com/video/58341318?autoplay=1">
</head><body><div id="post-content"><div><div class="youtube-player"><div class="player-content">
<img src="https://media.topdocumentaryfilms.com/uploads/weather.jpg" alt="Weather Underground">
</div></div></div></div></body></html>
"""


def test_documentary_page_yields_the_films_own_id_not_a_related_one():
    """A page-wide ytimg scan finds three ids and picks the right one only by luck — the embed meta
    is authoritative and the player's own thumbnail corroborates it."""
    from nolan import tdf_source as tdf
    v = tdf.extract_video(DOC_PAGE)
    assert v == {"host": "youtube", "video_id": "4EdMImlZE2s",
                 "watch_url": "https://www.youtube.com/watch?v=4EdMImlZE2s"}
    assert "ZZJPnAer7EM" in DOC_PAGE and "ofI03X9hAJI" in DOC_PAGE   # the decoys really are present


def test_a_post_with_no_player_is_not_a_documentary():
    """The site mixes blog posts, listicles and casino spam into the same archive. Absence of a
    player is the discriminator, and it costs nothing extra because it IS the field we extract."""
    from nolan import tdf_source as tdf
    assert tdf.extract_video(LISTICLE) is None


def test_vimeo_is_recognised_and_kept():
    """~4% of sampled documentaries are Vimeo-hosted. They are STORED with their host so they are
    not silently lost; whether they can be transcribed is a separate question the ingest answers."""
    from nolan import tdf_source as tdf
    v = tdf.extract_video(VIMEO_PAGE)
    assert v["host"] == "vimeo" and v["video_id"] == "58341318"
    assert v["watch_url"] == "https://vimeo.com/58341318"


def test_disagreement_between_the_two_routes_is_reported_not_resolved():
    """If the embed meta and the player thumbnail name different videos, something has changed about
    the page shape. Guessing would attach a real film to the wrong description."""
    from nolan import tdf_source as tdf
    bad = DOC_PAGE.replace('<img src="https://i.ytimg.com/vi/4EdMImlZE2s/maxresdefault.jpg" alt="How',
                           '<img src="https://i.ytimg.com/vi/DIFFERENT11/maxresdefault.jpg" alt="How')
    v = tdf.extract_video(bad)
    assert v["conflict"] == "DIFFERENT11" and v["video_id"] == "4EdMImlZE2s"


def test_parse_post_maps_the_editorial_metadata():
    """runtime is the prize: minutes, on every documentary. Archive rows carry a duration 14% of the
    time and the length filter can only bite when a row has one."""
    from nolan import tdf_source as tdf
    post = {"slug": "how-hoover-dam-works", "link": "https://topdocumentaryfilms.com/how-hoover-dam-works/",
            "title": {"rendered": "How Hoover Dam Works"},
            "content": {"rendered": "<p>Constructed between 1931 &amp; 1936, the <b>Hoover Dam</b>.</p>"},
            "meta": {"runtime": "66", "director": "Jake O'Neal", "ratings_average": "6"},
            "categories": [2709], "release": [3173], "date": "2025-08-17T00:00:00"}
    row = tdf.parse_post(post, {2709: "Technology", 3173: "2025"})
    assert row["title"] == "How Hoover Dam Works"
    assert row["duration"] == 66 * 60
    assert row["subject"] == ["Technology", "2025", "Jake O'Neal"]
    assert "Constructed between 1931 & 1936" in row["description"]   # entities decoded, tags stripped
    assert "<b>" not in row["description"] and row["date"] == "2025-08-17"


def test_a_missing_or_junk_runtime_never_invents_a_duration():
    """Unknown duration must stay unknown — the length filter KEEPS unknowns, so a fabricated one
    would silently include or exclude a film on a number nobody measured."""
    from nolan import tdf_source as tdf
    base = {"slug": "x", "link": "u", "title": {"rendered": "T"}, "content": {"rendered": ""},
            "categories": [], "release": [], "date": "2020-01-01"}
    assert tdf.parse_post({**base, "meta": {}}, {})["duration"] is None
    assert tdf.parse_post({**base, "meta": {"runtime": ""}}, {})["duration"] is None
    assert tdf.parse_post({**base, "meta": {"runtime": "n/a"}}, {})["duration"] is None


def test_watch_url_per_host():
    from nolan import tdf_source as tdf
    assert tdf.watch_url("youtube", "abc12345678") == "https://www.youtube.com/watch?v=abc12345678"
    assert tdf.watch_url("vimeo", "58341318") == "https://vimeo.com/58341318"


PLAYLIST_PAGE = DOC_PAGE.replace(
    'content="https://www.youtube-nocookie.com/embed/4EdMImlZE2s?iv_load_policy=3&autoplay=1"',
    'content="https://www.youtube-nocookie.com/embed/videoseries?list=PL_IlIlrxhtPNpzwxznelqfP7At1akMTKF&amp;iv_load_policy=3"')


def test_a_multipart_documentary_embeds_a_playlist_not_a_video():
    """`embed/videoseries?list=...` names no video — and `videoseries` is exactly 11 characters, so
    it satisfies a YouTube-id pattern and reads as an ordinary id. That cost 190 films (8% of the
    crawl) before the thumbnail cross-check flagged them as conflicts. The player's own thumbnail is
    the first part, and the playlist id is kept so the remaining parts stay recoverable."""
    from nolan import tdf_source as tdf
    v = tdf.extract_video(PLAYLIST_PAGE)
    assert v["video_id"] == "4EdMImlZE2s"                    # the thumbnail, not the marker
    assert v["playlist"] == "PL_IlIlrxhtPNpzwxznelqfP7At1akMTKF"
    assert "conflict" not in v
    assert v["watch_url"] == "https://www.youtube.com/watch?v=4EdMImlZE2s"


def test_a_single_video_page_carries_no_playlist_key():
    from nolan import tdf_source as tdf
    assert "playlist" not in tdf.extract_video(DOC_PAGE)


def test_the_survey_sink_keeps_what_a_source_enriched(tmp_path):
    """save_survey allow-listed ARCHIVE's extra fields, so a tdf survey persisted only
    id/url/title/duration and dropped the synopsis, category, host, playlist and page_url on write —
    2,131 rows' worth. A sink must not discard what it did not author."""
    from nolan import transcript_lib as tl
    rows = [{"video_id": "abc12345678", "url": "https://www.youtube.com/watch?v=abc12345678",
             "title": "How Hoover Dam Works", "duration": 3960, "host": "youtube",
             "subject": ["Technology", "2025"], "description": "Constructed between 1931 and 1936.",
             "page_url": "https://topdocumentaryfilms.com/how-hoover-dam-works/",
             "playlist": "PL_x", "director": "Jake O'Neal", "rating": "6", "date": "2025-08-17"}]
    tl.save_survey("topdocumentaryfilms.com", rows, tmp_path, kind="tdf", total=1)
    got = tl.load_surveys(tmp_path)[tl._survey_key("topdocumentaryfilms.com", "tdf")]["titles"][0]
    for f in ("host", "subject", "description", "page_url", "playlist", "director", "rating"):
        assert got.get(f) == rows[0][f], f"{f} was dropped on write"
