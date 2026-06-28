"""
Test the render-service with actual Motion Canvas and Remotion renders.

This script:
1. Starts the render-service if not running
2. Sends render requests using different layouts
3. Waits for completion and saves the videos

Prerequisites:
- Node.js installed
- render-service dependencies installed (npm install)
"""

import os
import sys
import json
import time
import subprocess
import requests
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RENDER_SERVICE_URL = "http://localhost:3010"
RENDER_SERVICE_DIR = Path(__file__).parent.parent / "render-service"
OUTPUT_DIR = Path(__file__).parent.parent / "test_output" / "render_service_layouts"


def check_server_running():
    """Check if render service is running."""
    try:
        r = requests.get(f"{RENDER_SERVICE_URL}/health", timeout=2)
        return r.status_code == 200
    except:
        return False


def start_server():
    """Start the render service in background."""
    print("Starting render service...")

    # Check if npm/node is available
    try:
        subprocess.run(["node", "--version"], check=True, capture_output=True)
    except:
        print("ERROR: Node.js not found. Please install Node.js.")
        return None

    # Start the server
    process = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=RENDER_SERVICE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,  # Needed for Windows
    )

    # Wait for server to start
    for i in range(30):
        time.sleep(1)
        if check_server_running():
            print(f"  Server started after {i+1}s")
            return process
        print(f"  Waiting... ({i+1}s)")

    print("ERROR: Server failed to start")
    return None


def submit_render(effect: str, params: dict, layout: str = "center", engine_hint: str = None):
    """Submit a render job and return job_id."""
    payload = {
        "effect": effect,
        "params": params,
        "layout": layout,
        "width": 1920,
        "height": 1080,
        "duration": 4,
    }

    r = requests.post(f"{RENDER_SERVICE_URL}/render", json=payload)
    if r.status_code != 202:
        print(f"  ERROR: {r.status_code} - {r.text}")
        return None

    data = r.json()
    return data


def wait_for_job(job_id: str, timeout: int = 120):
    """Wait for a job to complete."""
    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(f"{RENDER_SERVICE_URL}/render/status/{job_id}")
        data = r.json()

        status = data.get("status")
        progress = data.get("progress", 0)

        if status == "done":
            return data
        elif status == "error":
            print(f"  ERROR: {data.get('error')}")
            return None

        print(f"  Status: {status}, Progress: {progress}%")
        time.sleep(2)

    print("  TIMEOUT")
    return None


def get_result(job_id: str):
    """Get the result video path."""
    r = requests.get(f"{RENDER_SERVICE_URL}/render/result/{job_id}")
    if r.status_code != 200:
        return None
    return r.json().get("video_path")


def copy_result(video_path: str, output_name: str):
    """Copy result to output directory."""
    import shutil

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # The video_path is relative to render-service
    src = RENDER_SERVICE_DIR / video_path
    dst = OUTPUT_DIR / output_name

    if src.exists():
        shutil.copy(src, dst)
        print(f"  Saved: {dst}")
        return dst
    else:
        print(f"  ERROR: Source not found: {src}")
        return None


def test_remotion_quote_layouts():
    """Test Remotion quote renders with different layouts."""
    print("\n" + "=" * 60)
    print("TEST: Remotion Quote with Different Layouts")
    print("=" * 60)

    # Use quote-fade-center which is the correct effect ID
    tests = [
        ("center", "center"),
        ("split", "left"),  # Quote in left region of split layout
        ("lower-third", "main"),
    ]

    for layout, region in tests:
        print(f"\nRendering quote with layout='{layout}', region='{region}'...")

        result = submit_render(
            effect="quote-fade-center",
            params={
                "text": f"Testing {layout} layout",
                "author": "Layout Test",
            },
            layout=layout,
        )

        if not result:
            continue

        job_id = result.get("job_id")
        engine = result.get("engine")
        print(f"  Job: {job_id}, Engine: {engine}")

        # Wait for completion
        final = wait_for_job(job_id)
        if not final:
            continue

        # Get result
        video_path = get_result(job_id)
        if video_path:
            copy_result(video_path, f"remotion_quote_{layout}.mp4")


def test_motion_canvas_effects():
    """Test Motion Canvas renders with different layouts."""
    print("\n" + "=" * 60)
    print("TEST: Motion Canvas Effects with Layouts")
    print("=" * 60)

    # Check available effects that use Motion Canvas
    try:
        r = requests.get(f"{RENDER_SERVICE_URL}/effects")
        effects = r.json().get("effects", [])
        mc_effects = [e for e in effects if e.get("engine") == "motion-canvas"]
        print(f"\nAvailable Motion Canvas effects: {len(mc_effects)}")
        for e in mc_effects[:5]:
            print(f"  - {e.get('id')}: {e.get('description', '')[:50]}")
    except Exception as e:
        print(f"  Could not list effects: {e}")
        mc_effects = []

    # Try a Motion Canvas effect if available
    if mc_effects:
        effect = mc_effects[0]
        print(f"\nTesting effect: {effect.get('id')}")

        result = submit_render(
            effect=effect.get("id"),
            params=effect.get("default_params", {}),
            layout="center",
        )

        if result:
            job_id = result.get("job_id")
            engine = result.get("engine")
            print(f"  Job: {job_id}, Engine: {engine}")

            final = wait_for_job(job_id)
            if final:
                video_path = get_result(job_id)
                if video_path:
                    copy_result(video_path, f"motion_canvas_{effect.get('id')}.mp4")


def test_layouts_endpoint():
    """Test the layouts endpoint."""
    print("\n" + "=" * 60)
    print("TEST: Available Layouts from Render Service")
    print("=" * 60)

    try:
        r = requests.get(f"{RENDER_SERVICE_URL}/render/layouts")
        data = r.json()
        templates = data.get("templates", [])

        print(f"\nAvailable layouts: {len(templates)}")
        for t in templates:
            name = t.get("name")
            regions = t.get("regions", [])
            print(f"  - {name}: regions = {regions}")

        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def main():
    print("=" * 60)
    print("RENDER SERVICE LAYOUT TESTS")
    print("=" * 60)

    # Check if server is running
    if not check_server_running():
        print("\nRender service not running.")
        print("Please start it manually with:")
        print(f"  cd {RENDER_SERVICE_DIR}")
        print("  npm run dev")
        print("\nThen run this script again.")
        return False

    print("\nRender service is running!")

    # Run tests
    test_layouts_endpoint()
    test_remotion_quote_layouts()
    test_motion_canvas_effects()

    print("\n" + "=" * 60)
    print("TESTS COMPLETE")
    print("=" * 60)
    print(f"\nOutput directory: {OUTPUT_DIR}")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
