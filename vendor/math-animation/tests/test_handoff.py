from __future__ import annotations

import json
from pathlib import Path

from math_animation.compiler import ManimCompiler
from math_animation.handoff import write_nolan_handoff
from math_animation.style import normalize_style
from tests.test_compiler import timed_project


def test_nolan_handoff_preserves_timing_style_and_alignment(
    tmp_path: Path,
) -> None:
    project = timed_project()
    style = normalize_style(project.style)
    compilation = ManimCompiler().compile(project, style, tmp_path)
    destination = write_nolan_handoff(
        project,
        style,
        compilation.timeline,
        tmp_path,
    )
    payload = json.loads(destination.read_text(encoding="utf-8"))

    assert payload["clips"][0]["kind"] == "manim"
    assert payload["clips"][0]["start_seconds"] == 2.0
    assert payload["narration"]["utterances"][0]["words"][2]["word"] == "visual"
    assert payload["style"]["normalized"]["background"] == "#f5f0e6"
