"""ensure_storyboard — cold-start scaffold gap: new_essay writes SOURCE.md but not STORYBOARD.md,
which audio.mjs/captions.mjs/assemble-index.mjs HARD-require, so the first finish used to fail.
finish now synthesizes it from the composed frames + audio_meta + SOURCE.md (idempotent)."""
import json

from nolan.hyperframes import edit as hfedit


def _scaffold(tmp_path, monkeypatch):
    fdir = tmp_path / "compositions" / "frames"
    fdir.mkdir(parents=True)
    for fid in ("01-hook", "02-claim"):
        (fdir / f"{fid}.spec.json").write_text(json.dumps({"frames": [{}]}), encoding="utf-8")
    (tmp_path / "SOURCE.md").write_text(
        "# Homer\n\n## Hook\nHomer may never have existed.\n\n## Claim\nNearly twenty-eight thousand lines.\n",
        encoding="utf-8")
    (tmp_path / "audio_meta.json").write_text(json.dumps({"voices": [
        {"frame": 0, "duration_s": 14.4, "file": "assets/voice/01.wav"},
        {"frame": 1, "duration_s": 16.8, "file": "assets/voice/02.wav"}]}), encoding="utf-8")
    monkeypatch.setattr(hfedit, "_project_dir", lambda c: tmp_path)
    monkeypatch.setattr(hfedit, "list_frames", lambda c: ["01-hook", "02-claim"])
    monkeypatch.setattr(hfedit, "_frames_dir", lambda c: fdir)


def test_ensure_storyboard_synthesizes_when_missing(tmp_path, monkeypatch):
    _scaffold(tmp_path, monkeypatch)
    sb = hfedit.ensure_storyboard("x")
    assert sb.exists()
    txt = sb.read_text(encoding="utf-8")
    assert "format: 1920x1080" in txt                       # frontmatter present (drives the canvas)
    assert "## Frame 1 — Hook" in txt and "## Frame 2 — Claim" in txt
    assert "compositions/frames/01-hook.html" in txt         # points at the composed frame
    assert "14.4s" in txt and "assets/voice/01.wav" in txt   # duration + voice from audio_meta
    assert "Homer may never have existed." in txt            # narration from SOURCE.md


def test_ensure_storyboard_never_overwrites_hand_authored(tmp_path, monkeypatch):
    _scaffold(tmp_path, monkeypatch)
    (tmp_path / "STORYBOARD.md").write_text("HAND-AUTHORED", encoding="utf-8")
    hfedit.ensure_storyboard("x")
    assert (tmp_path / "STORYBOARD.md").read_text(encoding="utf-8") == "HAND-AUTHORED"
