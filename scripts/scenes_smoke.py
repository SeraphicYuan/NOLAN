"""Headless-browser smoke test for the new pipeline-visibility UI:
  - /scenes tempo chips (energy/transition/motion from tempo_enrich) on an orchestrator project
  - /scenes flow-refine agent picker (#flowAgent) on a flow project
  - /studio knowledge-match checkbox (#knowledgeMatch)
Asserts no JS errors and that the elements render. Run: python scripts/scenes_smoke.py
(hub must be up on 127.0.0.1:8011; needs the `homer` + `holbein-dance-of-death` projects).
"""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8011"
errors, checks = [], []


def check(name, cond):
    checks.append((name, bool(cond)))


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))

    # 1. /scenes on an orchestrator project (homer) → tempo chips
    page.goto(f"{BASE}/scenes?project=homer", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2500)                        # let scenes render
    check("scene rows rendered", len(page.query_selector_all(".scene-card, .scene")) > 0
          or page.query_selector("#sceneList") is not None)
    tempo = page.query_selector_all(".scene-tempo")
    check("tempo chips present (homer)", len(tempo) > 0)
    check("super-search panel present", page.query_selector(".super-search") is not None)
    check("super-search operator menu", page.query_selector(".ss-op") is not None)
    check("energy chip shows a value", "⚡" in (page.content()))
    check("tempo bar has a fill", page.query_selector(".tempo-fill") is not None)

    # 2. /scenes on a flow project (holbein) → flow-refine agent picker
    page.goto(f"{BASE}/scenes?project=holbein-dance-of-death", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    fc_display = page.eval_on_selector("#flowControls", "el => getComputedStyle(el).display") \
        if page.query_selector("#flowControls") else "none"
    check("flow controls visible on flow project", fc_display != "none")
    check("flow agent selector present", page.query_selector("#flowAgent") is not None)

    # 3. /studio → knowledge-match checkbox
    page.goto(f"{BASE}/studio?project=homer", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(1500)
    # studio may need the project chosen via the dropdown to render the match stage
    if not page.query_selector("#knowledgeMatch"):
        sel = page.query_selector("#project")
        if sel:
            try:
                page.select_option("#project", "homer")
                page.wait_for_timeout(1500)
            except Exception:
                pass
    check("knowledge match checkbox present", page.query_selector("#knowledgeMatch") is not None)

    browser.close()

print("console/page errors:", errors or "none")
for n, ok in checks:
    print(("PASS" if ok else "FAIL"), n)
ok = all(c for _, c in checks) and not errors
print("\nSCENES-SMOKE:", "GREEN" if ok else "RED")
sys.exit(0 if ok else 1)
