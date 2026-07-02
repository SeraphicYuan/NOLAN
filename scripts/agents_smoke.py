"""Headless smoke test for the orchestrator dashboard (/agents): full-pipeline strip (incl.
tempo_enrich) + the run-agent selector. Needs the `homer` project (has .orchestrator).
Run: python scripts/agents_smoke.py  (hub up on 127.0.0.1:8011)."""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8011"
errors, checks = [], []


def check(n, c):
    checks.append((n, bool(c)))


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{BASE}/agents", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(2500)
    check("project cards rendered", pg.query_selector(".project") is not None)
    check("pipeline strip present", len(pg.query_selector_all(".pipeline-strip")) > 0)
    check("pipeline shows steps (pstep)", len(pg.query_selector_all(".pstep")) > 0)
    check("tempo step in the pipeline", "tempo" in pg.content())
    check("a step marked 'next'", pg.query_selector(".pstep.next") is not None)
    check("run-agent selector present", pg.query_selector('[id^="run-agent-"]') is not None)
    check("run-here default option", "run here (local)" in pg.content())
    b.close()

print("console/page errors:", errors or "none")
for n, ok in checks:
    print(("PASS" if ok else "FAIL"), n)
ok = all(c for _, c in checks) and not errors
print("\nAGENTS-SMOKE:", "GREEN" if ok else "RED")
sys.exit(0 if ok else 1)
