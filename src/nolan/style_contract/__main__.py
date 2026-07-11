"""CLI: lint a HyperFrames essay against a style contract, or print the compiled author brief.

  python -X utf8 -m nolan.style_contract <comp_dir> [--preset essay] [--dial asset_density=dense] [--brief]
"""
import argparse

from .contract import StyleContract
from .linter import format_report, lint, scenes_from_hf


def main():
    ap = argparse.ArgumentParser(prog="nolan.style_contract",
                                 description="Score a HyperFrames essay against a style contract")
    ap.add_argument("comp", help="composition dir (…/videos/<slug>) holding compositions/frames/*.spec.json")
    ap.add_argument("--preset", default="essay")
    ap.add_argument("--dial", action="append", default=[],
                    help="dial=value, e.g. asset_density=dense (repeatable)")
    ap.add_argument("--brief", action="store_true", help="print the compiled author brief instead of linting")
    a = ap.parse_args()

    dials = {}
    for d in a.dial:
        k, _, v = d.partition("=")
        dials[k.strip()] = v.strip()
    contract = StyleContract.resolve(a.preset, **dials)

    if a.brief:
        print(contract.compile_brief())
        return
    scenes = scenes_from_hf(a.comp)
    if not scenes:
        raise SystemExit(f"no frame specs under {a.comp}/compositions/frames/")
    print(format_report(lint(scenes, contract)))


if __name__ == "__main__":
    main()
