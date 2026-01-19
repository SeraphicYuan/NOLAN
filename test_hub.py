"""Quick test for hub server."""
import sys
import time
import threading
import urllib.request
import urllib.error

def test_endpoints():
    """Test hub endpoints."""
    time.sleep(3)  # Wait for server to start

    endpoints = [
        ("http://127.0.0.1:8099/", "Landing"),
        ("http://127.0.0.1:8099/showcase", "Showcase"),
        ("http://127.0.0.1:8099/showcase/api/effects", "Effects API"),
    ]

    results = []
    for url, name in endpoints:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Test'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                results.append(f"{name}: {resp.status} OK")
        except urllib.error.HTTPError as e:
            results.append(f"{name}: {e.code} {e.reason}")
        except Exception as e:
            results.append(f"{name}: ERROR - {e}")

    for r in results:
        print(r)

    # Exit after tests
    import os
    os._exit(0)

if __name__ == "__main__":
    from pathlib import Path

    # Start test thread
    t = threading.Thread(target=test_endpoints, daemon=True)
    t.start()

    # Run server
    from nolan.hub import create_hub_app
    import uvicorn

    db_path = Path(r"D:\ClaudeProjects\.nolan\nolan.db")
    app = create_hub_app(
        db_path=db_path if db_path.exists() else None,
        project_dir=None,
    )

    print(f"Database exists: {db_path.exists()}")
    print("Starting server...")
    uvicorn.run(app, host="127.0.0.1", port=8099, log_level="warning")
