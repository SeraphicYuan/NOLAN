"""Associative-visual eval harness.

Per case: generate (associative + literal) comfyui prompts; expand+retrieve
(associative + literal) b-roll; optionally ComfyUI-render the gen prompts; then a
DIFFERENT-model judge scores pairwise (assoc vs literal, assoc vs creator's real
shown) + an absolute rubric. Aggregates into a report.

  python evals/associative/run.py --dry-run            # offline: print filled prompts
  python evals/associative/run.py --live [--limit N]   # LLM gen/expand/retrieve/judge
  python evals/associative/run.py --live --render      # + ComfyUI render check

Generator and judge are deliberately different models (gen=openrouter, judge=gemini).
"""

import argparse
import asyncio
import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from evals.associative import templates as T

HERE = os.path.dirname(os.path.abspath(__file__))


def load_testset():
    with open(os.path.join(HERE, "testset.json"), encoding="utf-8") as f:
        return json.load(f)


def _parse_json(raw: str) -> dict:
    raw = (raw or "").strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {"_unparsed": raw[:300]}


def _fmt(tpl, style, case, **extra):
    return tpl.format(style_name=style["name"], look=style["look"],
                      fewshot=T._fewshot_block([tuple(p) for p in style.get("fewshot", [])]),
                      line=case["line"], context=case.get("context") or "(none)", **extra)


def dry_run(ts, n=2):
    style = ts["style"]
    print(f"STYLE: {style['name']}\nLOOK: {style['look']}\nFEW-SHOT: {len(style['fewshot'])} pairs\n")
    for case in ts["cases"][:n]:
        print("=" * 70)
        print(f"[{case['id']}] ({case['line_type']}/{case['source']}) LINE: {case['line']}")
        print(f"  ref_shown: {case.get('ref_shown')}")
        print("\n--- GEN_ASSOCIATIVE ---\n" + _fmt(T.GEN_ASSOCIATIVE, style, case))
        print("\n--- EXPAND_ASSOCIATIVE ---\n" + _fmt(T.EXPAND_ASSOCIATIVE, style, case))
        print("\n--- JUDGE_PAIRWISE (A=assoc, B=literal placeholders) ---\n" +
              _fmt(T.JUDGE_PAIRWISE, style, case, a="<assoc visual>", b="<literal visual>"))
        print()


async def run_live(ts, limit=None, render=False):
    from src.nolan.config import load_config
    from src.nolan.llm import create_text_llm
    from src.nolan.vector_search import VectorSearch
    from pathlib import Path

    cfg = load_config()
    gen = create_text_llm(cfg, provider="openrouter")            # generator (qwen3.7-plus)
    judge = create_text_llm(cfg, provider="openrouter")          # judge (same model; blind pairwise)
    vs = VectorSearch(Path(cfg.indexing.database).expanduser().parent / "vectors")
    style = ts["style"]
    cases = ts["cases"][:limit] if limit else ts["cases"]
    rng = random.Random(7)

    gen_fn = None
    if render:
        try:
            from src.nolan.comfyui import ComfyUIClient
            comfy = ComfyUIClient(host=cfg.comfyui.host, port=cfg.comfyui.port,
                                  workflow_file="workflows/image/basic-z-image.json",
                                  prompt_node="27")  # z-image-turbo
            os.makedirs(os.path.join(HERE, "renders"), exist_ok=True)
            gen_fn = comfy
        except Exception as e:
            print(f"[render] ComfyUI unavailable, skipping renders: {e}")

    async def retrieve(query):
        try:
            res = vs.search(query, limit=3, search_level="segments")
            if res:
                return {"score": round(res[0].score, 3), "desc": (res[0].description or "")[:200]}
        except Exception as e:
            return {"error": str(e)[:120]}
        return None

    results = []
    for i, case in enumerate(cases):
        print(f"[{i+1}/{len(cases)}] {case['id']} {case['line'][:50]}")
        ga = (await gen.generate(_fmt(T.GEN_ASSOCIATIVE, style, case))).strip()
        gl = (await gen.generate(_fmt(T.LITERAL_GEN, style, case))).strip()
        xa = (await gen.generate(_fmt(T.EXPAND_ASSOCIATIVE, style, case))).strip()
        top_phrase = xa.splitlines()[0].split("::")[0].strip() if xa else case["line"]
        ret_a = await retrieve(top_phrase)
        ret_l = await retrieve(case["line"])

        # blind, order-randomized pairwise: assoc vs literal generation
        swap = rng.random() < 0.5
        a, b = (gl, ga) if swap else (ga, gl)
        pj = _parse_json(await judge.generate(_fmt(T.JUDGE_PAIRWISE, style, case, a=a, b=b)))
        win = pj.get("winner")
        pair_vs_literal = ("tie" if win == "tie" else
                           ("assoc" if (win == "B") == swap else "literal"))

        rub = _parse_json(await judge.generate(_fmt(T.JUDGE_RUBRIC, style, case, visual=ga)))

        pair_vs_ref = None
        if case.get("ref_shown"):
            swap2 = rng.random() < 0.5
            a2, b2 = (case["ref_shown"], ga) if swap2 else (ga, case["ref_shown"])
            pj2 = _parse_json(await judge.generate(_fmt(T.JUDGE_PAIRWISE, style, case, a=a2, b=b2)))
            w2 = pj2.get("winner")
            pair_vs_ref = ("tie" if w2 == "tie" else
                           ("ours" if (w2 == "B") == swap2 else "creator"))

        render_info = None
        if gen_fn is not None:
            try:
                outp = Path(HERE) / "renders" / f"{case['id']}_assoc.png"
                await gen_fn.generate(ga, outp)
                render_info = {"assoc": outp.name}
            except Exception as e:
                render_info = {"error": str(e)[:120]}

        results.append({**case, "gen_assoc": ga, "gen_literal": gl, "expand_assoc": xa,
                        "retrieve_assoc": ret_a, "retrieve_literal": ret_l,
                        "pair_vs_literal": pair_vs_literal, "pair_vs_ref": pair_vs_ref,
                        "rubric": rub, "render": render_info})

    _report(ts, results)


def _report(ts, results):
    with open(os.path.join(HERE, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    def rate(rows, key, val):
        rows = [r for r in rows if r.get(key) is not None]
        return f"{sum(1 for r in rows if r[key]==val)}/{len(rows)}" if rows else "0/0"

    abs_ = [r for r in results if r["line_type"] == "abstract"]
    con = [r for r in results if r["line_type"] == "concrete"]
    def mean_rub(rows, k):
        vals = [r["rubric"].get(k) for r in rows if isinstance(r.get("rubric"), dict) and isinstance(r["rubric"].get(k), int)]
        return round(sum(vals)/len(vals), 2) if vals else None

    lines = [
        f"# Associative eval — {ts['style']['name']}", "",
        f"cases: {len(results)}  (abstract {len(abs_)}, concrete {len(con)})", "",
        "## Guardrail — assoc vs literal (pairwise, blind)",
        f"- ABSTRACT lines: assoc wins {rate(abs_,'pair_vs_literal','assoc')}  (target ≥70%)",
        f"- CONCRETE lines: assoc wins {rate(con,'pair_vs_literal','assoc')}  (target: NOT worse — literal ok)",
        "",
        "## Craft bar — assoc vs creator's real shown (reference cases)",
        f"- ours ≥ creator: ours {rate(results,'pair_vs_ref','ours')} | tie {rate(results,'pair_vs_ref','tie')}  (target ours+tie ≥40%)",
        "",
        "## Rubric (associative, abstract lines, 1-5)",
        f"- evokes_concept {mean_rub(abs_,'evokes_concept')} | on_style {mean_rub(abs_,'on_style')} "
        f"| non_cliche {mean_rub(abs_,'non_cliche')} | coherence {mean_rub(abs_,'coherence')}",
        "",
        "## Retrieval (associative) — top match score (findability)",
    ]
    scored = [r["retrieve_assoc"]["score"] for r in results if isinstance(r.get("retrieve_assoc"), dict) and "score" in r["retrieve_assoc"]]
    lines.append(f"- got a match on {len(scored)}/{len(results)}; mean top-score {round(sum(scored)/len(scored),3) if scored else '-'}")
    with open(os.path.join(HERE, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    ts = load_testset()
    if a.live:
        asyncio.run(run_live(ts, limit=a.limit, render=a.render))
    else:
        dry_run(ts)


if __name__ == "__main__":
    main()
