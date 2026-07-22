"""A-P2 — dataset source + binding resolver (data as a first-class source). Fake data throughout."""
import json
from pathlib import Path

import pytest

from nolan.data import verbs, resolve
from nolan.data.registry import Dataset, load_dataset, list_datasets


# --- verbs -----------------------------------------------------------------------------------------

def test_verbs_filter_sort_and_timeseries_derive_in_order():
    rows = [{"year": 2021, "pct": 2.5}, {"year": 2023, "pct": 4.4}, {"year": 2028, "pct": 12.0},
            {"year": 2025, "pct": 7.1}]
    out = verbs.apply_query(rows, {"filter": {"pct": {">=": 4}}, "sort": {"by": "year"},
                                   "derive": {"growth": ["pct_change", "pct"]}})
    assert [r["year"] for r in out] == [2023, 2025, 2028]              # filtered (>=4) + sorted by year
    # pct_change runs AFTER the sort → year-over-year is correct: 4.4→7.1 = +61.4%, not the pre-sort value
    assert out[0]["growth"] is None
    assert abs(out[1]["growth"] - 61.36) < 0.1
    assert abs(out[2]["growth"] - 69.01) < 0.1


def test_verbs_aggregate_share_and_top_n():
    rows = [{"cat": "a", "v": 3}, {"cat": "a", "v": 5}, {"cat": "b", "v": 2}, {"cat": "c", "v": 10}]
    agg = verbs.apply_query(rows, {"aggregate": {"group_by": "cat", "agg": {"v": "sum"}},
                                   "derive": {"share": ["share_of_total", "v"]}, "top_n": {"n": 2, "by": "v"}})
    assert [r["cat"] for r in agg] == ["c", "a"]                       # top-2 by summed value
    assert agg[0]["v"] == 10 and abs(agg[0]["share"] - 50.0) < 0.1


def test_verbs_never_mutate_source():
    rows = [{"a": 1}]
    verbs.apply_query(rows, {"derive": {"b": ["cumsum", "a"]}})
    assert "b" not in rows[0]                                          # source untouched


# --- registry (provenance gate) --------------------------------------------------------------------

def _project(tmp: Path, index: dict, files: dict):
    (tmp / "datasets").mkdir(parents=True)
    (tmp / "datasets" / "index.json").write_text(json.dumps(index), encoding="utf-8")
    for name, content in files.items():
        (tmp / "datasets" / name).write_text(content, encoding="utf-8")
    return tmp


def test_load_dataset_coerces_dtypes(tmp_path):
    comp = _project(tmp_path,
                    {"elec": {"file": "elec.csv", "provenance": "IEA 2024",
                              "columns": [{"name": "year", "dtype": "int"}, {"name": "pct", "dtype": "float"}]}},
                    {"elec.csv": "year,pct\n2023,4.4\n2028,12.0\n"})
    ds = load_dataset(comp, "elec")
    assert ds.rows == [{"year": 2023, "pct": 4.4}, {"year": 2028, "pct": 12.0}]  # real ints/floats, not strings
    assert ds.provenance == "IEA 2024"
    assert any(d["id"] == "elec" for d in list_datasets(comp))


def test_load_dataset_rejects_unsourced(tmp_path):
    comp = _project(tmp_path, {"x": {"file": "x.csv", "columns": []}}, {"x.csv": "a\n1\n"})
    with pytest.raises(ValueError):                                   # no provenance → cannot register
        load_dataset(comp, "x")


# --- resolver (binding → block data shape + provenance) --------------------------------------------

def test_resolve_scene_materializes_chart_from_cells():
    ds = Dataset(id="elec", rows=[{"year": 2023, "pct": 4.4}, {"year": 2028, "pct": 12.0}],
                 meta={"provenance": "IEA 2024"})
    scene = {"id": "s1", "type": "chart", "data": {"kicker": "SHARE", "dataset": "elec",
             "encode": {"x": "year", "y": "pct", "suffix": "%"}}}
    resolve.resolve_scene(scene, ds)
    assert scene["data"]["series"] == [{"label": "2023", "value": 4.4}, {"label": "2028", "value": 12.0}]
    assert scene["data"]["value_source"] == "IEA 2024"               # gate now sees these numbers as sourced
    assert scene["data"]["kicker"] == "SHARE"                        # non-data fields preserved


def test_resolve_pie_and_sankey_shapes():
    ds = Dataset(id="split", rows=[{"cat": "power", "w": 60}, {"cat": "water", "w": 40}],
                 meta={"provenance": "internal"})
    pie = {"type": "pie", "data": {"dataset": "split", "encode": {"label": "cat", "value": "w"}}}
    resolve.resolve_scene(pie, ds)
    assert pie["data"]["segments"] == [{"label": "power", "value": 60.0}, {"label": "water", "value": 40.0}]
    sk = {"type": "sankey", "data": {"dataset": "split", "encode": {"label": "cat", "value": "w",
          "source_label": "The bill"}}}
    resolve.resolve_scene(sk, ds)
    assert sk["data"]["source"] == {"label": "The bill", "value": 100.0}
    assert len(sk["data"]["targets"]) == 2


def test_resolve_datasets_in_spec_end_to_end(tmp_path):
    comp = _project(tmp_path,
                    {"elec": {"file": "elec.csv", "provenance": "IEA 2024",
                              "columns": [{"name": "year", "dtype": "int"}, {"name": "pct", "dtype": "float"}]}},
                    {"elec.csv": "year,pct\n2023,4.4\n2028,12.0\n"})
    spec = {"frames": [{"id": "01", "scenes": [
        {"id": "s1", "type": "chart", "data": {"dataset": "elec", "encode": {"x": "year", "y": "pct"}}},
        {"id": "s2", "type": "statement", "data": {"lines": ["no dataset here"]}}]}]}
    n = resolve.resolve_datasets_in_spec(spec, comp)
    assert n == 1                                                    # only the bound scene resolved
    assert spec["frames"][0]["scenes"][0]["data"]["series"][0]["value"] == 4.4


# --- A-P2 follow-ups: resolver↔shape parity + A-P2.5 auto-playhead -----------------------------------

def test_resolver_shape_parity_no_drift():
    """Every field the resolver MATERIALIZES for a block must be a key the block's catalog data_schema
    declares (no phantom the block won't read — the ledger `items` vs `rows` drift this test caught), and
    the block's resolver-owned data field is produced. Guards the resolver↔block contract from silent drift."""
    cat = json.loads((Path(__file__).resolve().parents[1] /
                      "render-service/_lab_hyperframes/bridge/catalog.json").read_text(encoding="utf-8"))
    schema = cat["scene_templates"]
    RESOLVER_FIELD = {"chart": "series", "pie": "segments", "stat": "items", "scale": "items",
                      "spectrum": "items", "sankey": "targets", "funnel": "stages", "spans": "spans",
                      "bullet_list": "items", "ledger": "rows", "trajectory": "points"}
    rows = [{"x": "2020", "y": 10, "lo": 2000, "hi": 2002}, {"x": "2021", "y": 20, "lo": 2003, "hi": 2005},
            {"x": "2022", "y": 30, "lo": 2006, "hi": 2008}]
    enc = {"x": "x", "y": "y", "label": "x", "value": "y", "start": "lo", "end": "hi", "text": "x"}
    for bt, field in RESOLVER_FIELD.items():
        out = resolve._materialize(bt, rows, enc)
        assert field in out, f"{bt}: resolver did not produce its data field {field!r}"
        ds = schema.get(bt, {}).get("data_schema", {})
        ds_keys = set(ds.keys()) if isinstance(ds, dict) else set()
        for k in out:
            assert k in ds_keys, f"{bt}: resolver emits phantom key {k!r} not in catalog data_schema {sorted(ds_keys)}"


def test_line_chart_over_temporal_x_auto_enables_playhead():
    """A-P2.5: a line chart bound to a TEMPORAL x gets the sweeping time-cursor automatically; a non-temporal
    x does not; an explicit playhead:false is respected."""
    ds = Dataset(id="t", rows=[{"year": 2020, "pct": 4.0}, {"year": 2021, "pct": 6.0}, {"year": 2022, "pct": 9.0}],
                 meta={"provenance": "fake", "columns": [{"name": "year", "dtype": "int"}, {"name": "pct", "unit": "%"}]})
    sc = {"type": "chart", "data": {"type": "line", "encode": {"x": "year", "y": "pct"}}}
    resolve.resolve_scene(sc, ds)
    assert sc["data"].get("playhead") is True, "temporal-x line chart should auto-enable the playhead"
    # non-temporal x → no playhead
    ds2 = Dataset(id="c", rows=[{"co": "A", "n": 1}, {"co": "B", "n": 2}], meta={"provenance": "f"})
    sc2 = {"type": "chart", "data": {"type": "line", "encode": {"x": "co", "y": "n"}}}
    resolve.resolve_scene(sc2, ds2)
    assert "playhead" not in sc2["data"]
    # explicit off wins
    sc3 = {"type": "chart", "data": {"type": "line", "playhead": False, "encode": {"x": "year", "y": "pct"}}}
    resolve.resolve_scene(sc3, ds)
    assert sc3["data"]["playhead"] is False


def test_data_table_materializes_and_resolves_where_highlight():
    """A-P3: a dataset → a full table (columns × rows from real cells), and highlight:{where:{col:val}} maps
    to the matching row + value column, so a one-line beat spotlights the exact number IN CONTEXT."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"))
    import compose
    ds = Dataset(id="e", rows=[{"year": 2020, "pct": 2.0}, {"year": 2023, "pct": 4.4}, {"year": 2028, "pct": 13.0}],
                 meta={"provenance": "fake", "columns": [{"name": "year"}, {"name": "pct", "unit": "%"}]})
    sc = {"type": "data_table", "data": {"dataset": "e",
          "encode": {"columns": ["year", "pct"], "value": "pct", "suffix": "%"},
          "highlight": {"where": {"year": 2023}}}}
    resolve.resolve_scene(sc, ds)
    d = sc["data"]
    assert d["columns"] == ["year", "pct"]
    assert d["rows"] == [["2020", "2.0%"], ["2023", "4.4%"], ["2028", "13.0%"]]     # cells from real data, % suffix
    assert d["highlight"]["row"] == 1 and d["highlight"]["col"] == 1               # where→ the 2023/4.4% cell
    assert d["value_source"] == "fake"                                             # provenance (A-P1 passes)
    # the composer emits the highlighted cell id + a pulse on that row
    frag, tl = compose.BLOCKS["data_table"]("dt", {"id": "dt", "type": "data_table", "start": 0, "dur": 8, "data": d})
    assert "dt-c1-1" in "".join(frag) and any("dt-r1" in x and "scale" in x for x in tl)


def test_a_p4_marks_compose_and_emit():
    """A-P4: the three time-series marks compose and emit their signature elements (a drawing line, a stacked
    band sweep, ranked bars + a period ticker). Structural smoke — the render QA verifies the visual."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"))
    import compose
    traj = compose.BLOCKS["trajectory"]("tj", {"id": "tj", "type": "trajectory", "start": 0, "dur": 10,
           "data": {"points": [{"x": 1, "y": 2, "label": "a"}, {"x": 3, "y": 1, "label": "b"}, {"x": 2, "y": 4, "label": "c"}]}})
    assert "tj-path" in "".join(traj[0]) and any("strokeDashoffset" in x for x in traj[1])   # a drawn path
    strm = compose.BLOCKS["stream"]("sm", {"id": "sm", "type": "stream", "start": 0, "dur": 10,
           "data": {"series": [{"label": "A", "values": [1, 2, 3]}, {"label": "B", "values": [2, 1, 2]}], "x": ["1", "2", "3"]}})
    assert "sm-wipe" in "".join(strm[0]) and any("sm-wipe" in x for x in strm[1])             # left→right sweep
    race = compose.BLOCKS["bar_race"]("br", {"id": "br", "type": "bar_race", "start": 0, "dur": 12,
           "data": {"series": [{"label": "X", "values": [1, 5]}, {"label": "Y", "values": [3, 2]}], "steps": ["t1", "t2"]}})
    assert "br-period" in "".join(race[0]) and any("br-b0" in x and "width" in x for x in race[1])  # ranked bars + ticker


# --- A4: the gate accepts a dataset-only scene in BOTH routes (finish + incremental accept) ---

def _gate_errs(scene):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"))
    import author
    spec = {"frames": [{"id": "f1", "dur": 8, "scenes": [{"id": "s1", "start": 0, "dur": 8, **scene}]}]}
    return [e for e in author.validate_spec(spec) if "s1" in e]


def test_gate_accepts_dataset_only_chart_without_materialized_series():
    # binding a dataset IS the data; series is filled by resolve_datasets before recompose. The accept path
    # (which recomposes before resolution) must not reject the legal scene the finish path accepts.
    assert not _gate_errs({"type": "chart", "data": {"dataset": "gpu_cost", "encode": {"x": "year", "y": "v"}}})
    assert not _gate_errs({"type": "data_table", "data": {"dataset": "gpu_cost", "encode": {"columns": ["year"]}}})


def test_gate_still_rejects_a_bare_chart_with_neither_series_nor_dataset():
    assert _gate_errs({"type": "chart", "data": {"kicker": "x"}}), \
        "a chart with no series and no dataset binding is genuinely empty and must still be rejected"
