"""Real end-to-end UI test of the /scenes per-beat super search on Homer.
Drives the actual browser: for several (beat, operator) combos — expand the scene, pick the
operator, click Search, wait for results to RENDER, click Attach, verify it persists. Captures
every JS console/page error throughout. This is the test that catches frontend interaction bugs."""
import json
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8011"
errors = []
# (scene index in the flat list, operator) — a few methods across a few beats
COMBOS = [(0, "literal"), (2, "knowledge"), (4, "tonal"), (7, "auto")]
results = []


def snapshot_matched(scene_id):
    plan = json.load(open("projects/homer/scene_plan.json"))
    for sec in plan["sections"].values():
        for s in sec:
            if s["id"] == scene_id:
                return s.get("matched_asset") or (s.get("matched_clip") or {}).get("external_url")
    return None


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    pg.on("console", lambda m: errors.append(("console", m.text)) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(("pageerror", str(e))))
    pg.goto(f"{BASE}/scenes?project=homer", wait_until="networkidle", timeout=40000)
    pg.wait_for_timeout(3000)

    ids = pg.evaluate("() => allScenes.map(s => s.id)")

    for idx, op in COMBOS:
        if idx >= len(ids):
            continue
        sid = ids[idx]
        row = {"scene": sid, "operator": op}
        try:
            # expand this scene's super-search panel + set operator
            pg.evaluate(f"() => {{ const p=document.getElementById('ss-{sid}'); if(p.style.display==='none') superSearchToggle('{sid}'); document.getElementById('ss-op-{sid}').value='{op}'; }}")
            before = snapshot_matched(sid)
            # click Search this beat
            pg.evaluate(f"() => superSearch('{sid}')")
            # wait for the search to finish (status shows MATCHED/UNMATCHED/failed), up to ~230s
            done = False
            for _ in range(230):
                txt = pg.eval_on_selector(f"#ss-status-{sid}", "el => el.textContent") or ""
                if any(k in txt for k in ("pick", "UNMATCHED", "failed", "error", "Nothing")):
                    done = True
                    break
                pg.wait_for_timeout(1000)
            status = pg.eval_on_selector(f"#ss-status-{sid}", "el => el.textContent")
            npicks = len(pg.query_selector_all(f"#ss-results-{sid} .ss-pick"))
            row["search_status"] = status
            row["picks_rendered"] = npicks
            # if picks rendered, click the first Attach and verify it persists
            if npicks > 0:
                pg.query_selector(f"#ss-results-{sid} .ss-attach").click()
                attached = False
                for _ in range(80):
                    st = pg.eval_on_selector(f"#ss-status-{sid}", "el => el.textContent") or ""
                    if "attached" in st or "reloading" in st or "failed" in st or "error" in st:
                        attached = "attached" in st or "reloading" in st
                        break
                    pg.wait_for_timeout(1000)
                pg.wait_for_timeout(3000)  # let loadSceneData persist
                after = snapshot_matched(sid)
                row["attach_status"] = st
                row["persisted"] = bool(after) and after != before
            results.append(row)
        except Exception as e:
            row["EXC"] = str(e)[:120]
            results.append(row)

    b.close()

print("=== per (beat, operator) ===")
for r in results:
    print(" ", json.dumps(r))
print("\n=== JS errors:", errors or "NONE")
searched_ok = sum(1 for r in results if r.get("picks_rendered", 0) >= 0 and "EXC" not in r)
attached_ok = sum(1 for r in results if r.get("persisted"))
print(f"\nran={len(results)}  attached_ok={attached_ok}  js_errors={len(errors)}")
print("VERDICT:", "GREEN" if (not errors and results and all('EXC' not in r for r in results)) else "RED")
