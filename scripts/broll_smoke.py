"""Headless-browser smoke test for the /broll page (gap C) — loads the live hub page in
chromium, asserts no JS errors and that the key UI wiring works (operator/mode toggles,
providers load, show/hide). Does NOT run a full search (slow); it verifies the JS wiring.
Run: python .scratch/broll_smoke.py   (hub must be up on 127.0.0.1:8011)"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8011/broll"
errors, checks = [], []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL, wait_until="networkidle", timeout=25000)

    def check(name, cond):
        checks.append((name, bool(cond)))

    for sel, name in [("#line", "narration box"), ("#go", "search button"),
                      (".opbtn[data-op='tonal']", "tonal operator"),
                      (".opbtn[data-op='conceptual']", "conceptual operator"),
                      (".opbtn[data-op='ironic']", "ironic operator"),
                      (".opbtn[data-op='trait']", "trait operator"),
                      (".opbtn[data-op='relational']", "relational operator"),
                      (".modebtn[data-mode='stock']", "stock mode"),
                      (".modebtn[data-mode='library']", "library mode"),
                      (".modebtn[data-mode='generate']", "generate mode"),
                      ("#media .med", "media checkboxes")]:
        check(name, page.query_selector(sel) is not None)

    page.wait_for_timeout(1800)                       # let /api/broll/providers populate
    check("providers loaded", len(page.query_selector_all("#provlist .prov")) > 0)

    page.click(".opbtn[data-op='conceptual']")
    check("operator toggle active", "active" in (page.get_attribute(".opbtn[data-op='conceptual']", "class") or ""))
    check("operator hint updated", "mechanic" in page.inner_html("#ophint").lower())

    page.click(".modebtn[data-mode='library']")
    check("providers hidden in library mode",
          page.eval_on_selector("#providers", "el => getComputedStyle(el).display") == "none")
    page.click(".modebtn[data-mode='stock']")
    check("providers shown again in stock mode",
          page.eval_on_selector("#providers", "el => getComputedStyle(el).display") != "none")

    browser.close()

print("console/page errors:", errors or "none")
for n, ok in checks:
    print(("PASS" if ok else "FAIL"), n)
ok = all(c for _, c in checks) and not errors
print("\nSMOKE:", "GREEN" if ok else "RED")
sys.exit(0 if ok else 1)
