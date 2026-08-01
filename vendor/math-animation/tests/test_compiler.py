from __future__ import annotations

from pathlib import Path

import pytest

from math_animation.compiler import ManimCompiler
from math_animation.contracts import (
    BeatSpec,
    CustomSceneBlock,
    NarrationInput,
    ProjectSpec,
    RequestSpec,
    StyleTemplateRef,
    TitleCardBlock,
    UtteranceTiming,
    WordAnchor,
    WordTiming,
)
from math_animation.style import normalize_style


def timed_project() -> ProjectSpec:
    return ProjectSpec(
        project_id="timed-demo",
        title="Timed demo",
        request=RequestSpec(source_kind="screenplay", content="demo"),
        narration=NarrationInput(
            provider="nolan",
            utterances=[
                UtteranceTiming(
                    id="u1",
                    text="Start the visual now",
                    words=[
                        WordTiming(
                            word="Start", start_seconds=2.0, end_seconds=2.3
                        ),
                        WordTiming(
                            word="the", start_seconds=2.3, end_seconds=2.5
                        ),
                        WordTiming(
                            word="visual", start_seconds=3.0, end_seconds=3.4
                        ),
                        WordTiming(
                            word="now", start_seconds=3.4, end_seconds=3.8
                        ),
                    ],
                )
            ],
        ),
        style=StyleTemplateRef(
            raw={
                "colors": {"background": "#f5f0e6", "foreground": "#181818"},
                "semantic_colors": {"primary": "#1255aa"},
            }
        ),
        beats=[
            BeatSpec(
                id="intro",
                title="Intro",
                learning_objective="Show a timed title.",
                narration_utterance_id="u1",
                duration_seconds=3.0,
                blocks=[
                    TitleCardBlock(
                        id="intro.title",
                        title="A timed title",
                        start_at=WordAnchor(
                            utterance_id="u1", word_index=2, edge="start"
                        ),
                        run_time=0.5,
                        hold_seconds=0.2,
                    )
                ],
            )
        ],
    )


def test_compiler_resolves_word_anchor_and_style(tmp_path: Path) -> None:
    project = timed_project()
    result = ManimCompiler().compile(
        project, normalize_style(project.style), tmp_path
    )
    source = result.source_files[0].read_text(encoding="utf-8")
    assert "self.wait(1.0)" in source
    assert "#f5f0e6" in source
    assert result.timeline.clips[0].start_seconds == 2.0
    assert result.timeline.clips[0].duration_seconds == 3.0


def test_custom_scene_is_disabled_by_default(tmp_path: Path) -> None:
    source = (
        "from manim import *\n\n"
        "class CustomBeatScene(Scene):\n"
        "    def construct(self):\n"
        "        self.add(Dot())\n"
    )
    project = ProjectSpec(
        project_id="custom",
        title="Custom",
        request=RequestSpec(content="custom"),
        beats=[
            BeatSpec(
                id="custom-beat",
                title="Custom",
                learning_objective="Exercise the escape hatch.",
                duration_seconds=2.0,
                blocks=[
                    CustomSceneBlock(
                        id="custom.source",
                        scene_class="CustomBeatScene",
                        source=source,
                    )
                ],
            )
        ],
    )
    with pytest.raises(ValueError, match="disabled"):
        ManimCompiler().compile(
            project, normalize_style(project.style), tmp_path
        )


def test_custom_scene_compiles_when_explicitly_enabled(tmp_path: Path) -> None:
    source = (
        "from manim import *\n\n"
        "class CustomBeatScene(Scene):\n"
        "    def construct(self):\n"
        "        self.add(Dot())\n"
    )
    project = ProjectSpec(
        project_id="custom",
        title="Custom",
        request=RequestSpec(content="custom"),
        beats=[
            BeatSpec(
                id="custom-beat",
                title="Custom",
                learning_objective="Exercise the escape hatch.",
                duration_seconds=2.0,
                blocks=[
                    CustomSceneBlock(
                        id="custom.source",
                        scene_class="CustomBeatScene",
                        source=source,
                    )
                ],
            )
        ],
    )
    result = ManimCompiler(allow_custom_python=True).compile(
        project, normalize_style(project.style), tmp_path
    )
    assert result.source_files[0].read_text(encoding="utf-8") == source
