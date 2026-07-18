"""Effects umbrella foundation (nolan.effects): the registry is internally consistent, the authored
`treatments` gate is loud on bad input, and the backend-agnostic executor composes a css filter chain
+ emits blended overlay layers (procedural now; plate-based when a resolver supplies a clip). The
compose/author/map WIRING + GRADES parity live in tests/test_ground_effect.py."""
from nolan.effects import registry as reg
from nolan.effects import render as rnd


# --- registry integrity -----------------------------------------------------

def test_registry_entries_are_well_formed():
    ids = [e.id for e in reg.REGISTRY]
    assert len(ids) == len(set(ids)), "duplicate effect ids"
    for e in reg.REGISTRY:
        assert e.family in reg.FAMILIES, f"{e.id}: bad family {e.family}"
        assert e.method in reg.METHODS, f"{e.id}: bad method {e.method}"
        assert e.purpose and e.when_to_use, f"{e.id}: missing purpose/when_to_use"
        assert e.duration_preserving is True, f"{e.id}: effects are always duration_preserving"
        assert e.executor, f"{e.id}: no executor named"
        if e.method == "css_filter":
            assert e.css and not e.plate and not e.css_bg, f"{e.id}: css_filter needs css, no overlay src"
        elif e.method == "blend_overlay":
            assert e.blend in reg.BLEND_MODES, f"{e.id}: bad blend {e.blend}"
            assert bool(e.css_bg) ^ bool(e.plate), f"{e.id}: overlay is EITHER procedural css_bg OR a plate"
        elif e.method == "ffmpeg_bake":
            assert "ffmpeg" in e.backends, f"{e.id}: bake effect must run on the ffmpeg backend"


def test_covers_every_family_and_the_grade_vocabulary():
    fams = {e.family for e in reg.REGISTRY}
    assert fams == set(reg.FAMILIES), f"missing families: {set(reg.FAMILIES) - fams}"
    # the ground.grade vocabulary is preserved as first-class colour effects (safe to supersede GRADES)
    grades = {"warm", "cool", "darken", "brighten", "contrast", "desaturate", "mute", "noir"}
    color_ids = {e.id for e in reg.REGISTRY if e.method == "css_filter"}
    assert grades <= color_ids, f"lost grade values: {grades - color_ids}"
    # element overlays (the physical plates) are present as vocabulary even before plates are bundled
    element_ids = {e.id for e in reg.REGISTRY if e.family == "element"}
    assert {"fire", "rain", "smoke", "light-leak"} <= element_ids


# --- the authored gate ------------------------------------------------------

def test_validate_treatments_accepts_good_and_rejects_bad():
    assert reg.validate_treatments(None) == []
    assert reg.validate_treatments(["noir", {"id": "film-grain", "opacity": 0.3}]) == []
    assert reg.validate_treatments("noir")                       # a bare string is not a list
    assert reg.validate_treatments(["no-such-effect"])           # unknown id
    assert reg.validate_treatments([{"id": "noir", "opacity": 2.0}])   # opacity out of range
    assert reg.validate_treatments([{"id": "noir", "opacity": "loud"}])


def test_normalize_resolves_defaults_and_drops_unknown():
    out = reg.normalize_treatments(["film-grain", {"id": "fire", "opacity": 0.5}, "bogus"])
    assert [n["effect"].id for n in out] == ["film-grain", "fire"]   # unknown dropped, order kept
    assert out[0]["opacity"] == reg.BY_ID["film-grain"].default_opacity   # default filled
    assert out[1]["opacity"] == 0.5                                       # override honoured


# --- the render-time executor ----------------------------------------------

def test_filter_chain_stacks_colour_treatments_in_order():
    chain = rnd.filter_chain(["sepia", "contrast"])
    assert reg.BY_ID["sepia"].css in chain and reg.BY_ID["contrast"].css in chain
    assert chain.index("sepia") < chain.index("contrast")           # author order preserved
    assert rnd.filter_chain(["fire"]) == ""                          # an overlay is NOT a filter
    assert rnd.filter_chain([]) == ""


def test_overlay_layers_procedural_and_plate():
    # procedural grain -> a div layer carrying its blend + opacity, above content
    frags = rnd.overlay_layers(["film-grain"], "s1", 0.0, 6.0)
    assert len(frags) == 1
    assert 'class="clip"' in frags[0] and "mix-blend-mode:overlay" in frags[0]
    assert 'data-track-index="8"' in frags[0] and "id=\"s1-fx-film-grain\"" in frags[0]
    # a plate effect is SKIPPED without a resolver (library not populated) ...
    assert rnd.overlay_layers(["fire"], "s1", 0.0, 6.0) == []
    # ... and emits a looping muted <video> overlay once a resolver supplies a clip
    frags = rnd.overlay_layers(["fire"], "s1", 0.0, 6.0, resolve_plate=lambda tag: f"_library/overlays/{tag}.mp4")
    assert len(frags) == 1 and frags[0].startswith("<video") and "mix-blend-mode:screen" in frags[0]
    assert "_library/overlays/fire.mp4" in frags[0] and "loop" in frags[0]
    # a css_filter treatment emits NO overlay
    assert rnd.overlay_layers(["noir"], "s1", 0.0, 6.0) == []


def test_stacked_overlays_get_distinct_tracks():
    frags = rnd.overlay_layers(["film-grain", "scanlines"], "s1", 0.0, 6.0)
    assert 'data-track-index="8"' in frags[0] and 'data-track-index="9"' in frags[1]
