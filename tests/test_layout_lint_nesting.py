"""A child overlapping its own parent is layout; two siblings colliding is a defect.

All three "errors" in the diamond-v2 run were `process` step-number badges — 44x44 circles pinned to
their own card at left:-16px; top:-16px — verified correct by eye in the render. A linter whose only
failures are false positives gets ignored, which is exactly how a REAL overlap ships. After the fix the
composition lints OK with its four genuine advisories intact.
"""
from nolan.hyperframes.layout_lint import Item, _is_nested


def _item(path):
    return Item(box=None, text="x", window=(0.0, 1.0), sel="s", path=path)


def test_a_child_overlapping_its_parent_is_exempt():
    assert _is_nested(_item((0, 2)), _item((0, 2, 1)))
    assert _is_nested(_item((0, 2, 1)), _item((0, 2)))      # order must not matter


def test_a_deep_descendant_is_still_nested():
    assert _is_nested(_item((0,)), _item((0, 4, 3, 7)))


def test_siblings_are_NOT_exempt():
    """The real defect this linter exists for — must keep failing."""
    assert not _is_nested(_item((0, 1)), _item((0, 2)))
    assert not _is_nested(_item((0, 1, 0)), _item((0, 2, 0)))


def test_cousins_are_not_exempt():
    assert not _is_nested(_item((0, 1, 5)), _item((0, 2, 5)))


def test_identical_paths_and_unknown_shapes_claim_nothing():
    assert not _is_nested(_item((0, 1)), _item((0, 1)))     # same element
    assert not _is_nested(_item(()), _item((0, 1)))         # unknown tree → no exemption
    assert not _is_nested(_item((0, 1)), _item(()))


def test_the_overlap_check_consults_nesting_before_reporting():
    import inspect

    from nolan.hyperframes import layout_lint
    src = inspect.getsource(layout_lint)
    body = src[src.index("# overlap — pairwise"):]
    assert "_is_nested(a, c)" in body
    assert body.index("_is_nested(a, c)") < body.index("of the smaller box")
