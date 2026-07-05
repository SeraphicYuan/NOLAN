"""Content budgets on the template->block adapters (one enforcement point).

Over-limit descriptive text ellipsizes; content whose truncation would lie
(quotes, headlines, item counts over a block's capacity) rejects the mapping
so callers fall back to the python renderer.
"""

from nolan.layout_blocks import ADAPTERS, BLOCK_BUDGETS, adapt


def test_trim_ellipsizes_descriptive_text():
    block, props = adapt("quote", {"quote": "brief", "attribution": "A" * 200})
    assert block == "PullQuote"
    assert len(props["attribution"]) <= 70
    assert props["attribution"].endswith("…")


def test_reject_on_untrimmable_primary_text():
    assert adapt("quote", {"quote": "long " * 100}) is None      # 500 chars
    assert adapt("news_headline", {"headline": "X" * 200}) is None


def test_reject_on_item_count():
    items = [[f"name {i}", str(i)] for i in range(9)]
    assert adapt("ranking", {"items": items}) is None            # > 6 items


def test_nested_list_field_trims():
    events = [{"year": "70 BC", "label": "L" * 300}]
    block, props = adapt("timeline", {"events": events})
    assert block == "StepFlow"
    assert len(props["steps"][0]["detail"]) <= 80


def test_side_title_reject_in_comparison():
    assert adapt("comparison", {"left_text": "L" * 100, "right_text": "ok"}) is None


def test_within_budget_untouched():
    block, props = adapt("quote", {"quote": "Arma virumque cano",
                                   "attribution": "Virgil"})
    assert props == {"mode": "quote", "quote": "Arma virumque cano",
                     "attribution": "Virgil"}


def test_budget_paths_resolve_for_every_declared_block():
    # guard against budget keys drifting from adapter output shapes: every
    # budgeted block must be producible by at least one adapter
    produced = set()
    samples = {
        "quote": {"quote": "q", "attribution": "a"},
        "counter": {"value": 5, "label": "l"},
        "statistic": {"value": "73%", "label": "l"},
        "timeline": {"events": [{"year": "1", "label": "a"}, {"year": "2", "label": "b"}]},
        "ranking": {"items": [["a", "1"]]},
        "comparison": {"left_text": "a", "right_text": "b"},
        "question": {"question": "q?"},
        "chapter_card": {"title": "t"},
        "title": {"title": "t"},
        "list": {"items": ["a"]},
        "lower_third": {"name": "n"},
        "source_citation": {"source_name": "s"},
        "verdict": {"verdict": "v"},
        "location_stamp": {"location": "l"},
        "progress_bar": {"progress": 0.5},
        "percentage_bar": {"percentage": 50, "label": "l"},
        "tweet_card": {"content": "c"},
        "news_headline": {"headline": "h"},
    }
    for template, params in samples.items():
        adapted = adapt(template, params)
        assert adapted, template
        produced.add(adapted[0])
    assert set(BLOCK_BUDGETS) <= produced | {"StatCount"}
