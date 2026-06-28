"""Tests for the Lottie showcase hub endpoints (uses the real on-disk catalog)."""

from starlette.testclient import TestClient

from nolan.hub import create_hub_app

client = TestClient(create_hub_app(db_path=None, projects_dir=None))


def test_lottie_page_loads():
    assert client.get("/lottie").status_code == 200


def test_api_lottie_list():
    d = client.get("/api/lottie").json()
    assert d["total"] > 0 and d["templates"]
    assert isinstance(d["categories"], list) and d["categories"]
    t = d["templates"][0]
    for k in ("id", "name", "category", "raw", "has_schema", "schema_fields"):
        assert k in t


def test_api_lottie_category_filter():
    cats = client.get("/api/lottie").json()["categories"]
    d = client.get(f"/api/lottie?category={cats[0]}").json()
    assert d["total"] >= 1 and all(t["category"] == cats[0] for t in d["templates"])


def test_api_lottie_search():
    # search for a substring of an existing name
    first = client.get("/api/lottie").json()["templates"][0]
    term = first["name"].split()[0][:4]
    d = client.get(f"/api/lottie?q={term}").json()
    assert d["total"] >= 1


def test_api_lottie_get_and_raw():
    tid = client.get("/api/lottie").json()["templates"][0]["id"]
    assert client.get(f"/api/lottie/{tid}").json()["id"] == tid
    raw = client.get(f"/api/lottie/{tid}/raw")
    assert raw.status_code == 200 and "json" in raw.headers["content-type"]
    assert isinstance(raw.json(), dict)  # valid lottie JSON


def test_api_lottie_unknown_404():
    assert client.get("/api/lottie/__nope__").status_code == 404
    assert client.get("/api/lottie/__nope__/raw").status_code == 404


def test_render_requires_id():
    assert client.post("/api/lottie/render", json={}).status_code == 400


def test_render_starts_job():
    tid = client.get("/api/lottie").json()["templates"][0]["id"]
    r = client.post("/api/lottie/render", json={"id": tid})
    assert r.status_code == 200 and r.json().get("type") == "lottie-render"


def test_preview_path_traversal_blocked():
    assert client.get("/api/lottie/preview/..%2f..%2fpyproject.toml").status_code == 404
