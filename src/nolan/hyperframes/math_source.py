"""Pipeline integration for the MATH source: resolve every `math` scene into a Manim clip and mount it
as that scene's video ground — BEFORE recompose, alongside dataset and document binding.

  data.template + data.params + data.formulas  →  a rendered clip + data.ground = {kind:"video", src}

The step is HARD, not soft. It carries the math-provenance gate (a formula on screen that traces to
nothing does not ship) and refuses a clip whose duration does not match its narration window. The
engine, the adapter and the gate live in `nolan.mathanim`; this module is the DAG's handle on them,
the same shape `datasets.py` and `documents.py` have.
"""
from __future__ import annotations


def resolve_math_scenes(comp) -> int:
    """Resolve every math-bound scene in a comp. Returns how many were resolved.

    Raises `RuntimeError` on a gate failure or a render failure — `finish.py` surfaces the message
    verbatim, because it already names the scene and the fix.
    """

    from nolan.mathanim.resolve import MathResolveError, resolve_math

    try:
        return resolve_math(comp)
    except MathResolveError as exc:
        raise RuntimeError(f"hf-finish: {exc}") from exc


def main():
    import argparse

    parser = argparse.ArgumentParser(prog="nolan.hyperframes.math_source")
    parser.add_argument("comp")
    parser.add_argument("--gate-only", action="store_true",
                        help="build + provenance-check every math scene without spending a render")
    args = parser.parse_args()
    from nolan.mathanim.resolve import resolve_math

    count = resolve_math(args.comp, render=not args.gate_only)
    print(f"resolved {count} math scene(s) → Manim clips mounted as video grounds")


if __name__ == "__main__":
    main()
