"""The 7 gap effects (2026-07) are wired end-to-end — registry → Remotion
composition → Chapter host → contact-gate classification. Each assertion is a
link in the chain the wiring checklist requires; if any breaks, this fails.
"""
from pathlib import Path

import pytest

from nolan.motion.registry import get_effect
from nolan.motion.executor import _CHAPTER_TARGETS
from nolan.flows.gate.contact import _MEDIA_BLOCKS, _TEXT_BLOCKS

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "render-service" / "remotion-lib" / "src"

GAP = {
    "screen-frame": "ScreenFrame",
    "camera-shake": "CameraShake",
    "bar-race": "BarRace",
    "typewriter": "Typewriter",
    "before-after": "BeforeAfter",
    "whip-transition": "WhipTransition",
    "picture-in-picture": "PictureInPicture",
}


@pytest.mark.parametrize("eid,target", GAP.items())
def test_registered_with_remotion_backend(eid, target):
    e = get_effect(eid)
    assert e is not None, f"{eid} missing from REGISTRY"
    assert e.backend == "remotion"
    assert e.target == target
    assert e.when_to_use, f"{eid} has no craft guidance"


@pytest.mark.parametrize("eid,target", GAP.items())
def test_component_exists_and_registered(eid, target):
    assert (LIB / f"{target}.tsx").exists(), f"{target}.tsx missing"
    root = (LIB / "Root.tsx").read_text(encoding="utf-8")
    assert f'id="{target}"' in root, f"{target} not registered as a Composition in Root.tsx"
    comps = (LIB / "comps.ts").read_text(encoding="utf-8")
    assert target in comps, f"{target} not in comps.ts COMPS (not Chapter-hostable)"


@pytest.mark.parametrize("eid,target", GAP.items())
def test_chapter_hostable_and_classified(eid, target):
    assert target in _CHAPTER_TARGETS, f"{target} not in executor._CHAPTER_TARGETS"
    assert (target in _MEDIA_BLOCKS) ^ (target in _TEXT_BLOCKS), \
        f"{target} must be classified in exactly one of the contact-gate sets"
