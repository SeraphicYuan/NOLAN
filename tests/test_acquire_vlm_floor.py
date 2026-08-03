"""The VLM usability floor is ONE organ with two callers.

It used to live inside `render-service/_lab_hyperframes/bridge/pool.py` — a CLI script — so it was
reachable only by running the whole-project pool build. Every other acquisition path shipped without it:
the edit loop's scene-scoped search had no floor at all, and one real batch landed 24 candidates of
which two carried burned-in period-drama subtitles with recognisable actors and several were topically
wrong (a museum atrium for "auction house"). Captions and CLIP scores decided nothing; pixels did, and
the organ that looks at pixels was on the other path.

Pitfall class: docs/WIRING_CHECKLIST.md #4 (two dialects for one decision) — pre-empted here, because
the cheap fix would have been to copy the pass into the edit path.
"""
import importlib.util
import inspect
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"

_spec = importlib.util.spec_from_file_location("_bridge_pool_vlm", BRIDGE / "pool.py")
poolmod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poolmod)


def test_the_floor_lives_in_the_acquire_organ():
    from nolan.acquire import vlm_floor
    assert inspect.iscoroutinefunction(vlm_floor.score_and_caption)
    assert callable(vlm_floor.video_still)


def test_the_bridge_delegates_rather_than_keeping_a_copy():
    src = inspect.getsource(poolmod.score_and_caption)
    assert "from nolan.acquire.vlm_floor import score_and_caption" in src
    assert "describe_image" not in src, "the bridge must not grow a second implementation"
    assert "is_junk" not in src


def test_the_filmstrip_sampler_is_shared_too():
    src = inspect.getsource(poolmod._video_still)
    assert "from nolan.acquire.vlm_floor import video_still" in src
    assert "hstack" not in src, "one filmstrip implementation, not two"


def test_the_edit_path_routes_through_the_same_floor():
    from nolan.hyperframes import acquire_scene
    src = inspect.getsource(acquire_scene.acquire_for_scene)
    assert "from nolan.acquire.vlm_floor import score_and_caption" in src, \
        "the gap this move exists to close: the edit path had no floor"
    assert inspect.signature(acquire_scene.acquire_for_scene).parameters["vlm_floor"].default is True, \
        "the floor is ON by default on the edit path — opting out must be deliberate"


def test_a_dead_vlm_keeps_the_assets(monkeypatch):
    """Contained by design: an outage yields a NEUTRAL verdict and the asset is KEPT. A floor that
    empties the pool when the judge is down is worse than no floor."""
    from nolan.acquire.judge import is_junk, parse_verdict
    neutral = parse_verdict(None)
    assert neutral["usable"] is None
    assert is_junk(neutral) is False
