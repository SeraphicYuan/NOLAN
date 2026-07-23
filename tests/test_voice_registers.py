"""Honesty test for the narration-register registry (module contract).

Enforces: every register is well-formed, its calibrated base_wpm is a real measured int, and
target_wpm is reachable without pushing the global speed into time-stretch artifact territory
(a target the instruct can't hit means the instruct is mis-worded, not that we should stretch).
"""
from pathlib import Path

from nolan.voice_registers import (
    NARRATION_REGISTERS, DEFAULT_REGISTER, resolve_register, read_project_register,
    _SPEED_MIN, _SPEED_MAX,
)


def test_default_register_exists():
    assert DEFAULT_REGISTER in NARRATION_REGISTERS


def test_registers_well_formed():
    for name, r in NARRATION_REGISTERS.items():
        assert r.name == name, f"{name}: key/name mismatch"
        assert r.instruct.strip(), f"{name}: empty instruct"
        assert isinstance(r.base_wpm, int) and r.base_wpm > 0, f"{name}: bad base_wpm"
        assert isinstance(r.target_wpm, int) and r.target_wpm > 0, f"{name}: bad target_wpm"
        assert r.when_to_use.strip(), f"{name}: empty when_to_use"


def test_speed_in_safe_band():
    # The RAW (unclamped) ratio must already be in band — clamping is a backstop, not a crutch.
    for r in NARRATION_REGISTERS.values():
        raw = r.target_wpm / r.base_wpm
        assert _SPEED_MIN <= raw <= _SPEED_MAX, f"{r.name}: raw speed {raw:.3f} out of band"
        assert _SPEED_MIN <= r.speed <= _SPEED_MAX


def test_resolve_fallbacks():
    assert resolve_register(None).name == DEFAULT_REGISTER
    assert resolve_register("does-not-exist").name == DEFAULT_REGISTER
    assert resolve_register("explainer").name == "explainer"


def test_read_project_register(tmp_path: Path):
    assert read_project_register(tmp_path) is None            # no project.yaml
    (tmp_path / "project.yaml").write_text("name: x\nnarration_register: punchy-news\n",
                                           encoding="utf-8")
    assert read_project_register(tmp_path) == "punchy-news"
    (tmp_path / "project.yaml").write_text("name: x\n", encoding="utf-8")
    assert read_project_register(tmp_path) is None            # key absent
