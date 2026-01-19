"""HTTP test for hub with file output."""
import sys
import time
import threading

# Redirect stdout to file immediately
log_file = open(r"D:\ClaudeProjects\NOLAN\test_output.txt", "w")
sys.stdout = log_file
sys.stderr = log_file

print("Starting test...", flush=True)

import urllib.request
import urllib.error

def run_tests():
    time.sleep(3)

    tests = [
        "http://127.0.0.1:8099/",
        "http://127.0.0.1:8099/showcase",
        "http://127.0.0.1:8099/showcase/api/effects",
    ]

    print("\n=== TEST RESULTS ===", flush=True)
    all_passed = True
    for url in tests:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Test'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                print(f"PASS: {url} -> {resp.status}", flush=True)
        except urllib.error.HTTPError as e:
            print(f"FAIL: {url} -> {e.code} {e.reason}", flush=True)
            all_passed = False
        except Exception as e:
            print(f"ERROR: {url} -> {e}", flush=True)
            all_passed = False

    print(f"\nAll tests passed: {all_passed}", flush=True)
    log_file.close()
    import os
    os._exit(0 if all_passed else 1)

if __name__ == "__main__":
    from pathlib import Path
    from nolan.hub import create_hub_app
    import uvicorn

    print("Imports successful", flush=True)

    t = threading.Thread(target=run_tests, daemon=True)
    t.start()

    app = create_hub_app(db_path=None, project_dir=None)
    print("App created, starting server on port 8099...", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8099, log_level="error")
