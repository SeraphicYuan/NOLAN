"""The motion dial must reach the ASSET-NEED derivation.

Measured on the diamond v2 launch: with `video_share=heavy` the derivation still returned 24/24 IMAGE
needs, so the pool came back all stills and the (now hard) video_share gate was unsatisfiable however
well the author authored. A gate the pipeline cannot feed is worse than no gate.
"""
import asyncio
import json

from nolan.hyperframes.edit import _VIDEO_NEED_SHARE, derive_asset_needs


class _Spy:
    """Captures the system prompt; returns an empty need list (we assert on the INSTRUCTION, not the LLM)."""

    def __init__(self):
        self.system = None

    async def generate(self, prompt, system_prompt=None, **kw):
        self.system = system_prompt
        return "[]"


def _system_for(**kw):
    spy = _Spy()
    asyncio.run(derive_asset_needs("a script about diamonds", spy, k=24, **kw))
    return spy.system


def test_heavy_dial_sets_an_explicit_video_quota():
    s = _system_for(video_share="heavy")
    assert "MOTION QUOTA" in s
    assert str(round(24 * _VIDEO_NEED_SHARE["heavy"])) in s     # 11 of 24
    assert '"media_type":"video"' in s


def test_light_dial_asks_for_fewer():
    heavy = round(24 * _VIDEO_NEED_SHARE["heavy"])
    light = round(24 * _VIDEO_NEED_SHARE["light"])
    assert light < heavy
    assert str(light) in _system_for(video_share="light")


def test_no_dial_keeps_the_original_prefer_image_behaviour():
    for s in (_system_for(), _system_for(video_share="none"), _system_for(video_share="bogus")):
        assert "MOTION QUOTA" not in s
        assert "prefer image" in s.lower()


# --- malformed-JSON salvage ---------------------------------------------------------------
from nolan.hyperframes.edit import _parse_need_items


def test_clean_array_parses_normally():
    raw = '[{"id":"a1","query":"one"},{"id":"a2","query":"two"}]'
    assert [x["id"] for x in _parse_need_items(raw)] == ["a1", "a2"]


def test_one_malformed_object_costs_only_itself():
    """REGRESSION: an unescaped quote at char 10590 raised JSONDecodeError and lost the WHOLE 24-need
    plan, taking the acquisition down. The needs are independent objects — a bad one costs one need."""
    raw = ('[{"id":"a1","query":"good one"},'
           '{"id":"a2","query":"he said "unescaped" here"},'      # malformed
           '{"id":"a3","query":"good two"}]')
    got = _parse_need_items(raw)
    assert [x["id"] for x in got] == ["a1", "a3"]


def test_braces_inside_strings_do_not_confuse_the_scanner():
    raw = ('[{"id":"a1","query":"a {brace} and a \\" quote"},'
           '{"id":"a2","query":"bad "x" here"},'
           '{"id":"a3","query":"fine"}]')
    assert [x["id"] for x in _parse_need_items(raw)] == ["a1", "a3"]


def test_no_array_returns_empty():
    assert _parse_need_items("sorry, I cannot help with that") == []


def test_quota_shortfall_is_reported_not_swallowed(capsys):
    """The quota is a prompt instruction the planner can miss (observed: 9 video when 11 were asked).
    Missing it must be VISIBLE — a silently thin pool is how the motion gate becomes unreachable."""
    class _Short:
        async def generate(self, prompt, system_prompt=None, **kw):
            return json.dumps([{"id": f"a{i}", "query": f"q{i}",
                                "media_type": "video" if i < 2 else "image"} for i in range(24)])

    asyncio.run(derive_asset_needs("script", _Short(), k=24, video_share="heavy"))
    assert "motion quota" in capsys.readouterr().out.lower()


def test_meeting_the_quota_is_silent(capsys):
    class _Ok:
        async def generate(self, prompt, system_prompt=None, **kw):
            return json.dumps([{"id": f"a{i}", "query": f"q{i}", "media_type": "video"} for i in range(24)])

    asyncio.run(derive_asset_needs("script", _Ok(), k=24, video_share="heavy"))
    assert "motion quota" not in capsys.readouterr().out.lower()


# --- retry BEFORE salvage ----------------------------------------------------------------------

_BAD = '[{"id":"a1","query":"ok"},{"id":"a2","query":"he said "x" here"},{"id":"a3","query":"ok2"}]'
_GOOD = '[{"id":"b1","query":"one"},{"id":"b2","query":"two"},{"id":"b3","query":"three"}]'


class _Seq:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0

    async def generate(self, prompt, system_prompt=None, **kw):
        r = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return r


def test_malformed_json_regenerates_before_salvaging(capsys):
    """Salvage costs whole needs (one live run lost 11 of 24), so a retry comes first."""
    c = _Seq(_BAD, _GOOD)
    got = asyncio.run(derive_asset_needs("s", c, k=24))
    assert c.calls == 2                                   # it asked again
    assert [n["id"] for n in got] == ["b1", "b2", "b3"]    # and used the CLEAN plan, not the wreckage
    assert "regenerating once" in capsys.readouterr().out


def test_salvage_is_the_last_resort_when_the_retry_also_fails():
    c = _Seq(_BAD, _BAD)
    got = asyncio.run(derive_asset_needs("s", c, k=24))
    assert c.calls == 2
    assert [n["id"] for n in got] == ["a1", "a3"]          # degraded, but not empty


def test_clean_first_response_costs_no_retry():
    c = _Seq(_GOOD)
    got = asyncio.run(derive_asset_needs("s", c, k=24))
    assert c.calls == 1 and len(got) == 3
