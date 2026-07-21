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
