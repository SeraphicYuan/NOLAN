"""Tests for the assemble endpoint fix (Studio 'Assemble final' was broken — it sent
`--audio-file` but the CLI takes audio as a positional arg)."""

from pathlib import Path

from nolan.hub import _resolve_assemble_audio


def test_explicit_absolute_audio(tmp_path):
    a = tmp_path / "vo.wav"; a.write_bytes(b"x")
    assert _resolve_assemble_audio(tmp_path / "proj", str(a)) == a


def test_project_relative_audio(tmp_path):
    proj = tmp_path / "proj"
    (proj / "assets").mkdir(parents=True)
    (proj / "assets" / "narration.mp3").write_bytes(b"x")
    got = _resolve_assemble_audio(proj, "assets/narration.mp3")
    assert got == proj / "assets" / "narration.mp3"


def test_autodetect_standard_voiceover(tmp_path):
    proj = tmp_path / "proj"
    (proj / "assets" / "voiceover").mkdir(parents=True)
    (proj / "assets" / "voiceover" / "voiceover.mp3").write_bytes(b"x")
    got = _resolve_assemble_audio(proj, None)   # field left blank in the UI
    assert got and got.name == "voiceover.mp3"


def test_none_when_missing(tmp_path):
    assert _resolve_assemble_audio(tmp_path / "proj", None) is None
    assert _resolve_assemble_audio(tmp_path / "proj", "nope.wav") is None


def test_assemble_endpoint_400_without_audio_and_200_with(tmp_path):
    """Endpoint cleanly errors when no audio is resolvable, and starts a job when it is."""
    import os
    from starlette.testclient import TestClient
    from nolan.hub import create_hub_app

    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "scene_plan.json").write_text('{"sections": {}}')

    cwd = os.getcwd(); os.chdir(tmp_path)
    try:
        client = TestClient(create_hub_app(db_path=None, projects_dir=tmp_path / "projects"))
        # no audio yet -> clear 400 (instead of the old broken --audio-file crash)
        assert client.post("/api/assemble", json={"project": "demo"}).status_code == 400
        # add the standard voiceover -> endpoint starts the job
        (proj / "assets" / "voiceover").mkdir(parents=True)
        (proj / "assets" / "voiceover" / "voiceover.wav").write_bytes(b"x")
        r = client.post("/api/assemble", json={"project": "demo"})
        assert r.status_code == 200 and r.json().get("type") == "assemble"
    finally:
        os.chdir(cwd)
