"""The video source-kind registry — and the binding that stops a new kind from silently
inheriting YouTube's behaviour."""


def test_every_kind_declares_the_things_the_ui_and_dispatchers_ask_for():
    from nolan import transcript_sources as ts
    assert set(ts.KINDS) == {"youtube", "youtube_cc", "archive", "tdf"}
    for k in ts.all_kinds():
        assert k.label and k.icon, f"{k.id}: needs a label and icon for the picker"
        assert k.ref_kind in ("user", "singleton")
        assert k.enumeration in ts.ENUMERATION
        assert k.duration_coverage != "unknown", (
            f"{k.id}: the length filter needs to know where a duration comes from")
        if k.ref_kind == "user":
            assert k.ref_placeholder, f"{k.id}: an add box needs to say what to type"


def test_ref_kind_separates_a_reference_from_an_adapter_that_IS_the_source():
    """The distinction the Sources tab is built on. You ADD a channel; you ENABLE a site crawler,
    because there is no second topdocumentaryfilms.com to name."""
    from nolan import transcript_sources as ts
    assert [k.id for k in ts.user_addable()] == ["archive", "youtube", "youtube_cc"]
    assert [k.id for k in ts.connectors()] == ["tdf"]
    assert ts.kind("tdf").is_singleton and not ts.kind("youtube").is_singleton
    assert not ts.kind("tdf").ref_placeholder, "a singleton has no reference to type"


def test_an_unknown_kind_falls_back_to_the_SAFEST_family():
    """A wrong guess must never mark a copyrighted documentary as free footage."""
    from nolan import transcript_sources as ts
    fallback = ts.kind("something-new")
    assert fallback.id == "youtube" and fallback.copyright_free_default is False


def test_copyright_free_defaults_match_what_each_family_actually_is():
    from nolan import transcript_sources as ts
    assert ts.kind("youtube").copyright_free_default is False       # documentaries are never free
    assert ts.kind("youtube_cc").copyright_free_default is True     # free by definition
    assert ts.kind("tdf").copyright_free_default is False           # copyrighted documentaries
    # archive is the curator's assertion at add time, so the DEFAULT must not claim free
    assert ts.kind("archive").copyright_free_default is False


def test_a_bad_kind_definition_is_refused_at_construction():
    import pytest
    from nolan import transcript_sources as ts
    with pytest.raises(ValueError):
        ts.SourceKind(id="x", label="X", icon="?", ref_kind="whatever", enumeration="site-crawl")
    with pytest.raises(ValueError):
        ts.SourceKind(id="x", label="X", icon="?", ref_kind="user", enumeration="telepathy")


def test_the_registry_covers_every_kind_the_library_actually_uses():
    """THE BINDING. `kind` used to be matched with exclusion lists — `(archive||cc) ? "" : Sync` —
    so an unregistered kind inherited YouTube's behaviour and got a Sync button that would call
    list_channel() on a website. Every kind reachable through the library must be declared here."""
    import re
    from pathlib import Path
    from nolan import transcript_sources as ts
    src = Path("src/nolan/transcript_lib.py").read_text(encoding="utf-8")
    used = set(re.findall(r'kind\s*==\s*"([a-z_]+)"', src))
    unknown = used - set(ts.KINDS)
    assert not unknown, f"transcript_lib branches on kinds absent from the registry: {unknown}"


def test_the_add_box_is_rendered_FROM_the_registry_not_hand_written():
    """WIRING_CHECKLIST #5: a menu copied into a template by hand is the menu that rots. The picker
    was three hard-coded buttons, so a new kind meant remembering to edit the HTML."""
    from pathlib import Path
    tpl = Path("src/nolan/templates/transcripts.html").read_text(encoding="utf-8")
    assert "fillAddKinds" in tpl, "the add-box picker must be built from the registry payload"
    # the old hand-written buttons must be gone, or both would coexist and drift
    import re
    hard = re.findall(r'<button data-k="(youtube|youtube_cc|archive)"', tpl)
    assert not hard, f"hand-written kind buttons still in the template: {hard}"


def test_a_singleton_connector_is_never_offered_in_the_add_box():
    """You do not TYPE a reference for a site crawler — there is no second topdocumentaryfilms.com.
    Offering it in a box that asks for an identifier would promise a shape that does not exist."""
    from nolan import transcript_sources as ts
    payload = ts.payload()
    for cid in payload["connectors"]:
        assert cid not in payload["addable"], f"{cid} is a singleton and must not be user-addable"
    assert set(payload["addable"]) | set(payload["connectors"]) == set(ts.KINDS)


def test_sync_all_refuses_a_kind_its_walker_cannot_enumerate():
    """`ingest_channel_transcripts` walks a channel with yt-dlp. Sync-all used to hand it EVERY
    registered source, so an archive collection or a site crawler produced a job that enumerated
    nothing — and the tile offered Sync to any kind not named in an exclusion list."""
    from pathlib import Path
    from nolan import transcript_sources as ts
    route = Path("src/nolan/webui/routes/transcripts.py").read_text(encoding="utf-8")
    assert 'spec.enumeration != "channel-listing"' in route, (
        "sync-all must ask the registry whether a kind can be walked as a channel")
    assert '"skipped": skipped' in route, "a batch covering a subset must report what it skipped"
    walkable = [k.id for k in ts.all_kinds() if k.enumeration == "channel-listing"]
    assert set(walkable) == {"youtube", "youtube_cc"}
