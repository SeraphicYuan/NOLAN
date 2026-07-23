"""Shared acquisition plumbing (acquire/shared.py) — the one home both pools now use."""
from nolan.acquire import shared


def test_valid_image(tmp_path):
    from PIL import Image
    good = tmp_path / "g.jpg"
    Image.new("RGB", (10, 10), "white").save(good)
    assert shared.valid_image(good) is True
    bad = tmp_path / "b.jpg"
    bad.write_text("<html>not an image</html>", encoding="utf-8")
    assert shared.valid_image(bad) is False
    assert shared.valid_image(tmp_path / "missing.jpg") is False


def test_downscale_for_vision(tmp_path):
    from PIL import Image
    big = tmp_path / "big.png"
    Image.new("RGB", (3000, 2000), "white").save(big)
    send, tmp = shared.downscale_for_vision(big)
    assert tmp is not None and send == tmp
    with Image.open(send) as im:
        assert max(im.size) <= 1024
    tmp.unlink()
    small = tmp_path / "s.png"
    Image.new("RGB", (400, 300), "white").save(small)
    send2, tmp2 = shared.downscale_for_vision(small)
    assert tmp2 is None and str(send2) == str(small)         # small: sent as-is, no temp


def test_parse_vision_json():
    assert shared.parse_vision_json('{"matches": true}') == {"matches": True}
    assert shared.parse_vision_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert shared.parse_vision_json('prose {"x": 2} trailing') == {"x": 2}
    assert shared.parse_vision_json("no json here") is None
    assert shared.parse_vision_json("") is None
    assert shared.parse_vision_json("[1,2,3]") is None       # not an object → None


def test_build_search_client_smoke():
    from nolan.config import NolanConfig
    c = shared.build_search_client(NolanConfig())
    assert hasattr(c, "search_assets") and hasattr(c, "get_available_providers")
