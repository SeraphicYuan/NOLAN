from __future__ import annotations

import pytest

from math_animation.safety import (
    normalize_math_expression,
    normalize_vector_expression,
    validate_custom_scene_source,
)


def test_normalize_math_expression_maps_math_functions_to_numpy() -> None:
    assert normalize_math_expression("sin(x) + x**2") == "np.sin(x) + x ** 2"


def test_normalize_math_expression_blocks_code_execution() -> None:
    with pytest.raises(ValueError):
        normalize_math_expression("__import__('os').system('whoami')")


def test_vector_expression_preserves_declared_e_binding() -> None:
    assert (
        normalize_vector_expression(
            "sqrt(e**2) + sin(i)",
            variable_names={"i", "t", "e"},
        )
        == "np.sqrt(e ** 2) + np.sin(i)"
    )


def test_custom_scene_gate_accepts_one_declared_scene() -> None:
    validate_custom_scene_source(
        "from manim import *\n\n"
        "class CustomBeatScene(Scene):\n"
        "    def construct(self):\n"
        "        self.add(Dot())\n",
        "CustomBeatScene",
    )


def test_custom_scene_gate_blocks_file_access() -> None:
    with pytest.raises(ValueError, match="blocked call"):
        validate_custom_scene_source(
            "from manim import *\n\n"
            "class CustomBeatScene(Scene):\n"
            "    def construct(self):\n"
            "        open('secret.txt')\n",
            "CustomBeatScene",
        )
