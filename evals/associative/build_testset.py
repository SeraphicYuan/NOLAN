"""Build the associative-eval test set from a video_style's pairing data + synthetic cases.

  python evals/associative/build_testset.py [style_id] [slug]

Outputs evals/associative/testset.json:
  { style: {name, look, fewshot:[[said,shown]...]}, cases:[{id,line,context,line_type,source,ref_shown}] }
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.nolan.video_style import VideoStyleStore

HERE = os.path.dirname(os.path.abspath(__file__))

# Curated synthetic cases (held-out hard edges + concrete controls).
SYNTH_ABSTRACT = [
    "and slowly, their freedom slipped away",
    "the whole system was rotting from within",
    "for the first time in years, she felt at peace",
    "a quiet economic anxiety settled over the country",
    "and just like that, time had run out",
    "the truth was finally starting to surface",
]
SYNTH_CONCRETE = [
    "the bridge collapsed into the river below",
    "he signed the treaty in front of the cameras",
    "she planted a single tree in the empty lot",
]


def _look(extract: dict) -> str:
    c = extract.get("color", {}) or {}
    pal = ",".join(p["hex"] for p in c.get("palette", [])[:3])
    reads = (extract.get("cinematography", {}) or {}).get("reads", [])
    cine = reads[0]["read"][:160] if reads else ""
    return f"{c.get('temperature','?')} palette ({pal}), saturation {c.get('saturation','?')}. {cine}".strip()


def main():
    style_id = sys.argv[1] if len(sys.argv) > 1 else "liu-xiu-historical-narrative"
    store = VideoStyleStore("video_styles")
    srcs = store.sources(style_id)
    slug = sys.argv[2] if len(sys.argv) > 2 else (srcs[0]["slug"] if srcs else None)
    ex = store.read_extract(style_id, slug)
    if not ex:
        raise SystemExit(f"no extract for {style_id}/{slug} — run analysis first")

    samples = (ex.get("pairing", {}) or {}).get("samples", [])
    assoc = [s for s in samples if s["band"] in ("associative", "tonal/abstract") and s.get("shown")]
    literal = [s for s in samples if s["band"] == "literal" and s.get("shown")]

    # Few-shot = up to 6 real non-literal pairs (held OUT of the test cases).
    fewshot = [[s["said"], s["shown"]] for s in assoc[:6]]
    fewshot_said = {s["said"] for s in assoc[:6]}

    cases = []
    for s in assoc[6:]:
        if s["said"] in fewshot_said:
            continue
        cases.append({"id": f"real-abs-{len(cases)}", "line": s["said"], "context": "",
                      "line_type": "abstract", "source": "reference", "ref_shown": s["shown"]})
    for s in literal:
        cases.append({"id": f"real-con-{len(cases)}", "line": s["said"], "context": "",
                      "line_type": "concrete", "source": "reference", "ref_shown": s["shown"]})
    for line in SYNTH_ABSTRACT:
        cases.append({"id": f"syn-abs-{len(cases)}", "line": line, "context": "",
                      "line_type": "abstract", "source": "synthetic", "ref_shown": None})
    for line in SYNTH_CONCRETE:
        cases.append({"id": f"syn-con-{len(cases)}", "line": line, "context": "",
                      "line_type": "concrete", "source": "synthetic", "ref_shown": None})

    testset = {
        "style": {"id": style_id, "name": store.get(style_id).get("name", style_id),
                  "look": _look(ex), "fewshot": fewshot},
        "cases": cases,
    }
    out = os.path.join(HERE, "testset.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(testset, f, indent=2, ensure_ascii=False)

    by = {}
    for c in cases:
        by[(c["line_type"], c["source"])] = by.get((c["line_type"], c["source"]), 0) + 1
    print(f"wrote {out}")
    print(f"  style: {testset['style']['name']}  | fewshot exemplars: {len(fewshot)}")
    print(f"  cases: {len(cases)}  breakdown {dict((f'{k[0]}/{k[1]}', v) for k, v in sorted(by.items()))}")
    print(f"  look: {testset['style']['look'][:120]}")


if __name__ == "__main__":
    main()
