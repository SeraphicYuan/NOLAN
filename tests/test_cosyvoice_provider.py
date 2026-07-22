"""CosyVoiceTTS provider: factory routing, instruct-capability, JSONL batch, loud failure."""

import json
from types import SimpleNamespace

import pytest

from nolan.config import TtsConfig, CosyVoiceConfig
from nolan.tts import create_tts_provider, CosyVoiceTTS, OmniVoiceTTS
import nolan.tts as tts


def test_instruct_capable():
    c = TtsConfig()
    assert c.instruct_capable() is False                 # omnivoice default: no
    c.provider = "cosyvoice3"
    assert c.instruct_capable() is True                  # cosyvoice3: yes
    c.provider = "omnivoice"
    c.omnivoice.supports_instruct = True
    assert c.instruct_capable() is True                  # omnivoice flagged on


def test_factory_routes_provider():
    # cosyvoice3 routes without a live env (its __init__ just stores cfg)
    assert isinstance(create_tts_provider(TtsConfig(provider="cosyvoice3")), CosyVoiceTTS)
    with pytest.raises(ValueError, match="unknown tts provider"):
        create_tts_provider(TtsConfig(provider="bogus"))
    # OmniVoiceTTS validates env_python at construction (a real engine env is required)
    assert OmniVoiceTTS is not None


def test_batch_builds_jsonl_and_collects(tmp_path, monkeypatch):
    prov = CosyVoiceTTS(CosyVoiceConfig(env_python="py", repo_dir=str(tmp_path), model_dir="m"))
    items = [{"id": "sec_0000", "text": "hi", "ref_audio": "r.wav", "ref_text": "t", "instruct": "calm"},
             {"id": "sec_0001", "text": "bye", "ref_audio": "r.wav"}]

    def fake_run(cmd, **kw):
        out = __import__("pathlib").Path(cmd[cmd.index("--res_dir") + 1])
        jl = __import__("pathlib").Path(cmd[cmd.index("--test_list") + 1])
        lines = [json.loads(x) for x in jl.read_text(encoding="utf-8").splitlines()]
        assert lines[0]["instruct"] == "calm" and lines[0]["ref_audio"] == "r.wav"
        assert "instruct" not in lines[1]                # only where provided
        (out / "sec_0000.wav").write_bytes(b"a")
        (out / "sec_0001.wav").write_bytes(b"b")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tts.subprocess, "run", fake_run)
    produced = prov.synthesize_batch(items, tmp_path)
    assert set(produced) == {"sec_0000", "sec_0001"}


def test_batch_raises_loud_on_failure(tmp_path, monkeypatch):
    prov = CosyVoiceTTS(CosyVoiceConfig(repo_dir=str(tmp_path)))
    monkeypatch.setattr(tts.subprocess, "run",
                        lambda cmd, **kw: SimpleNamespace(returncode=1, stdout="", stderr="boom"))
    with pytest.raises(RuntimeError, match="cosyvoice runner failed"):
        prov.synthesize_batch([{"id": "x", "text": "t", "ref_audio": "r"}], tmp_path)
