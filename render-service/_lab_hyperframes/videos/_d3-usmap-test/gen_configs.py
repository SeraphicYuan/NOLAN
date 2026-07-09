"""Write config.js for the d3 US-map composition — proves any state / multi-state works
by only changing FIPS ids + labels (geometry + centroid are computed by d3 at render)."""
import json, sys

CFG = {
    "va":   {"kicker": "The map · U.S. data-center power", "title": "Virginia", "states": ["51"],
             "sub": '"Data Center Alley" — the largest concentration of data centers on Earth. Its grid demand is set to <b>double by 2030</b>.'},
    "ca":   {"kicker": "State spotlight · the West", "title": "California", "states": ["06"],
             "sub": "40M people, the world's 5th-largest economy — and a fast-growing cluster of AI compute."},
    "tx":   {"kicker": "State spotlight · the grid", "title": "Texas", "states": ["48"],
             "sub": "Its own grid (ERCOT) makes it a magnet for power-hungry data-center build-outs."},
    "gaky": {"kicker": "The land · new builds", "title": "Georgia & Kentucky", "states": ["13", "21"], "primary": "13",
             "sub": "Where new data centers are buying farmland <b>outright</b> — reshaping rural land use."},
}
name = sys.argv[1]
open("config.js", "w", encoding="utf-8").write("window.__HL = " + json.dumps(CFG[name], ensure_ascii=False) + ";")
print("wrote config.js for", name, "→ states", CFG[name]["states"])
