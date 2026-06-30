"""CLI shim — the art ingest now lives in nolan.flows.ingest.ingest_art (in-process).
Usage: python web-video-lab/art_ingest.py <art-spec.json> <out.job.json>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nolan.flows.ingest import ingest_art

if __name__ == "__main__":
    ingest_art(sys.argv[1], sys.argv[2])
