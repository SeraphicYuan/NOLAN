"""Probe the project-local segment index for Roaring Twenties beat b-roll.

Confirms the asset pool is actually useful before we build scenes.
"""
from pathlib import Path
from nolan.indexer import VideoIndex
from nolan.vector_search import VectorSearch

PROJECT = Path("projects/US Economy")
index = VideoIndex(PROJECT / "index.db")
vs = VectorSearch(db_path=PROJECT / "vectors", index=index)

QUERIES = [
    "1929 stock market crash, panic, falling chart",
    "rising stock market line chart going up",
    "Great Depression breadline, people waiting in line, poverty",
    "1920s vintage archival footage, old city, roaring twenties",
    "factory production, farmers, debt",
    "split screen comparison rich versus poor",
]

for q in QUERIES:
    print("\n" + "=" * 80)
    print("QUERY:", q)
    results = vs.search(q, limit=4, search_level="segments")
    for r in results:
        ts = f"{r.timestamp_start:6.1f}-{r.timestamp_end:6.1f}s"
        desc = (r.description or "")[:140].replace("\n", " ")
        print(f"  [{r.score:.3f}] {ts}  {desc}")
