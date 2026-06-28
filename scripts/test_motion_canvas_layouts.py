"""Test multiple Motion Canvas effects with different layouts."""

import requests
import time
import shutil
from pathlib import Path

RENDER_SERVICE_URL = "http://localhost:3010"
OUTPUT_DIR = Path("test_output/motion_canvas_layouts")


def submit_render(effect: str, params: dict, layout: str = "center", region: str = None):
    """Submit a render job and wait for completion."""
    payload = {
        "effect": effect,
        "params": params,
        "layout": layout,
        "width": 1920,
        "height": 1080,
    }
    if region:
        payload["region"] = region

    r = requests.post(f"{RENDER_SERVICE_URL}/render", json=payload)
    if r.status_code != 202:
        return None, f"HTTP {r.status_code}: {r.text}"

    data = r.json()
    job_id = data.get("job_id")
    engine = data.get("engine")
    print(f"    Job: {job_id}, Engine: {engine}")

    # Poll for completion
    for _ in range(60):
        time.sleep(2)
        r = requests.get(f"{RENDER_SERVICE_URL}/render/status/{job_id}")
        status_data = r.json()
        status = status_data.get("status")

        if status == "done":
            # Get video path from result endpoint
            result = requests.get(f"{RENDER_SERVICE_URL}/render/result/{job_id}")
            result_data = result.json()
            return result_data.get("video_path"), None
        elif status == "error":
            return None, status_data.get("error", "Unknown error")

    return None, "Timeout"


def copy_result(src_path: str, filename: str):
    """Copy result to output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if src_path and Path(src_path).exists():
        dest = OUTPUT_DIR / filename
        shutil.copy(src_path, dest)
        print(f"    Saved: {dest}")
        return True
    return False


def main():
    print("=" * 60)
    print("MOTION CANVAS LAYOUT TESTS")
    print("=" * 60)

    # Check server
    try:
        r = requests.get(f"{RENDER_SERVICE_URL}/health")
        if r.status_code != 200:
            print("Render service not running!")
            return
        print("\nRender service is running!")
    except:
        print("Cannot connect to render service!")
        return

    # Test cases: (effect, params, layout, region, output_name)
    tests = [
        # Quote effects with different layouts
        (
            "quote-fade-center",
            {"text": "Center Layout Test", "author": "Test"},
            "center",
            None,
            "quote_center.mp4",
        ),
        (
            "quote-fade-center",
            {"text": "Split Left Layout", "author": "Test"},
            "split",
            "left",
            "quote_split_left.mp4",
        ),
        (
            "quote-fade-center",
            {"text": "Split Right Layout", "author": "Test"},
            "split",
            "right",
            "quote_split_right.mp4",
        ),
        (
            "quote-fade-center",
            {"text": "Lower Third Layout", "author": "Breaking News"},
            "lower-third",
            None,
            "quote_lower_third.mp4",
        ),
        (
            "quote-fade-center",
            {"text": "Upper Third Layout", "author": "Headlines"},
            "upper-third",
            None,
            "quote_upper_third.mp4",
        ),
        # Counter effect with layouts (stat-counter-roll)
        (
            "stat-counter-roll",
            {"value": 2024, "label": "Year", "duration": 3},
            "center",
            None,
            "counter_center.mp4",
        ),
        (
            "stat-counter-roll",
            {"value": 50, "suffix": "%", "label": "Progress", "duration": 3},
            "split",
            "right",
            "counter_split_right.mp4",
        ),
        # Typewriter effect (text-typewriter)
        (
            "text-typewriter",
            {"text": "Testing typewriter in lower third...", "duration": 4},
            "lower-third",
            None,
            "typewriter_lower_third.mp4",
        ),
        # Highlight text (text-highlight)
        (
            "text-highlight",
            {"text": "IMPORTANT", "style": "underline", "duration": 3},
            "center",
            None,
            "highlight_center.mp4",
        ),
        (
            "text-highlight",
            {"text": "Breaking", "style": "marker", "color": "#ef4444", "duration": 3},
            "upper-third",
            None,
            "highlight_upper_third.mp4",
        ),
    ]

    print(f"\nRunning {len(tests)} tests...")
    print("-" * 60)

    success = 0
    failed = 0

    for effect, params, layout, region, output_name in tests:
        region_str = f", region={region}" if region else ""
        print(f"\n[{effect}] layout={layout}{region_str}")

        video_path, error = submit_render(effect, params, layout, region)

        if error:
            print(f"    ERROR: {error}")
            failed += 1
        elif video_path:
            if copy_result(video_path, output_name):
                success += 1
            else:
                print(f"    ERROR: Could not copy result")
                failed += 1
        else:
            print(f"    ERROR: No video path returned")
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {success} passed, {failed} failed")
    print(f"Output directory: {OUTPUT_DIR.absolute()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
