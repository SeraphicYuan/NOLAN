"""Did the caption run buy anything? — and which subjects still have material on the table."""


def test_library_quality_flags_what_bought_nothing(monkeypatch, tmp_path):
    """`frames > 0` is not the same as useful: a static lecture yields ONE keyframe and a leader-heavy reel
    yields title cards, and both count as "captioned". The report separates them by frame count, DISTINCT
    caption ratio and content mix — measured live, 7 of 144 captioned videos bought <= 4 frames."""
    from nolan import transcript_frames as tfr
    from nolan import transcript_lib as tl
    frames = {
        "good": [{"caption": f"a distinct shot {i}", "content_kind": "broll"} for i in range(20)],
        "static": [{"caption": "the same wide shot of a lecture", "content_kind": "talking_head"}
                   for _ in range(10)],
        "onlyone": [{"caption": "single frame", "content_kind": "broll"}],
        "cards": [{"caption": f"title card {i}", "content_kind": "graphics"} for i in range(8)]
                 + [{"caption": "one real shot", "content_kind": "broll"}],
    }
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {
        "good": {"title": "Good film", "frames": 20}, "static": {"title": "A lecture", "frames": 10},
        "onlyone": {"title": "One frame", "frames": 1}, "cards": {"title": "Leader reel", "frames": 9},
        "uncaptioned": {"title": "Not captioned", "frames": 0}})
    monkeypatch.setattr(tfr, "frames_for_video", lambda vid: frames.get(vid, []))

    q = tl.library_quality(tmp_path)
    assert q["captioned"] == 4 and "uncaptioned" not in [v["video_id"] for v in q["videos"]]
    by = {v["video_id"]: v for v in q["videos"]}
    assert by["good"]["thin"] is False and by["good"]["ratio"] == 1.0
    assert by["static"]["thin"] and "distinct captions" in by["static"]["why"]     # repetitive → static
    assert by["onlyone"]["thin"] and "keyframe" in by["onlyone"]["why"]
    assert by["cards"]["thin"] and "title cards" in by["cards"]["why"]
    assert set(q["thin_ids"]) == {"static", "onlyone", "cards"}
    assert q["content_mix"]["broll"] == 22 and q["frames"] == 40   # 20 good + 1 single + 1 in the reel
    assert [v["video_id"] for v in q["videos"]][:1] == ["onlyone"]                 # worst first


def test_coverage_shows_where_material_is_still_on_the_table(monkeypatch, tmp_path):
    """Growing a library by topic has a blind spot: you never see the rows you left behind. Coverage
    reports, per subject, the high/medium rows NOT in the catalog — where a second pick pays with no new
    search."""
    from nolan import transcript_lib as tl
    from nolan import transcript_memory as mem
    mem.put_judgements("the space race", [{"video_id": "a", "fit": "high"}, {"video_id": "b", "fit": "high"},
                                          {"video_id": "c", "fit": "medium"}, {"video_id": "d", "fit": "off"}],
                       "m", tmp_path)
    mem.put_judgements("prohibition", [{"video_id": "p1", "fit": "high"}], "m", tmp_path)
    mem.record_accepted([{"video_id": "a", "topic": "the space race", "fit": "high"}], "topic", tmp_path)
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {"a": {}, "p1": {}})   # both ingested

    cov = mem.coverage(tmp_path)
    space = next(t for t in cov["topics"] if t["topic"] == "the space race")
    assert space["judged"] == 4 and space["high"] == 2 and space["off"] == 1
    assert space["in_library"] == 1 and space["accepted"] == 1
    assert space["remaining_high"] == 2                       # b + c are still takeable; d was `off`
    proh = next(t for t in cov["topics"] if t["topic"] == "prohibition")
    assert proh["remaining_high"] == 0 and proh["in_library"] == 1
    assert cov["with_material_left"] == 1 and cov["total_remaining_high"] == 2
    assert cov["topics"][0]["topic"] == "the space race"       # most material left, first
