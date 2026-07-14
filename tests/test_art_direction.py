"""Art direction for generated b-roll — the shared visual BRIEF + per-shot composition. The point is
COHERENCE: the brief owns the style + locks medium/reference/era so the set feels authored, and the LLM
writes only the subject (disambiguated / metaphor). All derived from theme+subject — nothing essay-hardcoded."""
import asyncio

from nolan.acquire.art_direction import (VisualBrief, derive_brief, compose_prompt, _EVOCATIVE_SYS)


class FakeLLM:
    def __init__(self, resp):
        self.resp = resp
        self.last = None

    async def generate(self, user, system_prompt=""):
        self.last = (user, system_prompt)
        return self.resp


def test_visual_brief_roundtrip():
    b = VisualBrief(style="Dark Moody Atmosphere", medium="oil painting", reference="Caravaggio",
                    era="antiquity", negatives=["cartoon"])
    assert VisualBrief.from_dict(b.to_dict()) == b


def test_derive_brief_carries_theme_style_and_parses_look():
    """The style comes from the theme-derived default (one decision, one place); the LLM defines only the
    parts the style tag can't express (medium/reference/era)."""
    llm = FakeLLM('{"medium":"neoclassical oil painting","reference":"in the manner of Caravaggio",'
                  '"era":"classical antiquity","realism":"painterly","texture":"aged","negatives":["modern","cartoon"]}')
    b = asyncio.run(derive_brief(None, subject="a Homer essay", theme="dark-botanical",
                                 style_default="Dark Moody Atmosphere", llm=llm))
    assert b.style == "Dark Moody Atmosphere"                        # style NOT invented by the LLM
    assert b.medium == "neoclassical oil painting" and "Caravaggio" in b.reference and b.negatives


def test_compose_locks_medium_and_reference_across_shots():
    """Coherence lock: two different subjects share the SAME medium + reference (deterministic wrap), which
    the style tag alone cannot guarantee — this is the brief's whole reason to exist."""
    brief = VisualBrief(style="Dark Moody Atmosphere", medium="neoclassical oil painting",
                        reference="in the manner of Caravaggio", era="classical antiquity")
    p1, n1 = asyncio.run(compose_prompt(None, {"id": "a1", "query": "Homer", "evocative": False}, brief,
                                        llm=FakeLLM("the blind poet Homer")))
    p2, _ = asyncio.run(compose_prompt(None, {"id": "a2", "query": "the sea", "evocative": False}, brief,
                                       llm=FakeLLM("a stormy wine-dark sea")))
    for p in (p1, p2):
        assert p.startswith("neoclassical oil painting")            # same medium leads every prompt
        assert "in the manner of Caravaggio" in p                    # same reference anchor
        assert "empty space at the lower left" in p                  # composed for the (later) overlaid title
        assert "title" not in p                                       # but NEVER the word 'title' (it renders as text)
    assert "the blind poet Homer" in p1 and "wine-dark sea" in p2    # only the subject varies
    assert "watermark" in n1 and "cartoon" in n1                     # generic failure-mode negatives


def test_compose_evocative_uses_metaphor_branch():
    llm = FakeLLM("a thousand raised hands merging into one")
    asyncio.run(compose_prompt(None, {"id": "a", "query": "the fingerprint of a crowd", "evocative": True},
                               VisualBrief(medium="oil painting"), llm=llm))
    assert "ABSTRACT" in llm.last[1]                                 # the evocative system prompt was used


def test_verify_generation_matches_and_flags_mismatch(tmp_path):
    from nolan.acquire.art_direction import verify_generation
    img = tmp_path / "x.png"
    img.write_bytes(b"\0" * 100)

    class FV:
        def __init__(self, r):
            self.r = r

        async def describe_image(self, p, prompt):
            return self.r

    need = {"query": "a marble bust of Homer", "evocative": False}
    ok = asyncio.run(verify_generation(None, img, need, provider=FV('{"matches": true, "reason": "a classical bust"}')))
    bad = asyncio.run(verify_generation(None, img, need, provider=FV('{"matches": false, "reason": "a modern man in a suit"}')))
    assert ok["matches"] is True
    assert bad["matches"] is False and "modern" in bad["reason"]


def test_verify_generation_graceful_never_blocks(tmp_path):
    """Vision down / error / no image -> matches:True, so a fidelity check can never empty a beat."""
    from nolan.acquire.art_direction import verify_generation
    img = tmp_path / "x.png"
    img.write_bytes(b"\0")

    class Boom:
        async def describe_image(self, p, prompt):
            raise RuntimeError("vision down")

    assert asyncio.run(verify_generation(None, "/nope.png", {"query": "x"}))["matches"] is True
    assert asyncio.run(verify_generation(None, img, {"query": "x"}, provider=Boom()))["matches"] is True


def test_compose_contained_on_dead_llm():
    class Dead:
        async def generate(self, u, system_prompt=""):
            raise RuntimeError("down")

    p, _ = asyncio.run(compose_prompt(None, {"id": "a", "query": "Homer", "gen_prompt": "headshot of Homer"},
                                      VisualBrief(medium="oil painting"), llm=Dead()))
    assert "headshot of Homer" in p                                  # falls back to the raw subject
