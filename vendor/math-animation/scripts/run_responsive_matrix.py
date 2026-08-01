"""Render the narrated algebra film across aspect and style variants."""

from __future__ import annotations

import argparse
from pathlib import Path

from build_synthetic_algebra_fixture import build
from math_animation.bundle import write_json_atomic
from math_animation.contracts import RenderSettings, StyleTemplateRef
from math_animation.pipeline import AuthoringPipeline


ROOT = Path(__file__).resolve().parents[1]


VARIANTS = {
    "landscape-light-720": {
        "render": (1280, 720),
        "dark": False,
    },
    "square-dark-720": {
        "render": (720, 720),
        "dark": True,
    },
    "portrait-light-960": {
        "render": (540, 960),
        "dark": False,
    },
}


def _style(dark: bool) -> StyleTemplateRef:
    if not dark:
        return build().style
    return StyleTemplateRef(
        template_id="synthetic-nolan-dark",
        raw={
            "colors": {
                "background": "#0b1118",
                "foreground": "#f2eee6",
                "muted": "#89939d",
            },
            "semantic_colors": {
                "primary": "#62b9ae",
                "changing": "#ee765f",
                "fixed": "#78a4d2",
                "secondary": "#d4aa55",
                "positive": "#74c184",
            },
            "typography": {
                # Deliberately missing to verify Manim's font fallback.
                "font": "Nolan Missing Font Acceptance Test",
                "title_size": 54,
                "body_size": 27,
                "math_size": 52,
            },
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("/tmp/math-animation-responsive-matrix"),
    )
    parser.add_argument("--render", action="store_true")
    parser.add_argument(
        "--variant",
        choices=tuple(VARIANTS),
        help="Run one variant instead of the complete matrix.",
    )
    args = parser.parse_args()

    summaries = []
    spec_dir = ROOT / "examples" / "responsive_matrix"
    spec_dir.mkdir(parents=True, exist_ok=True)
    selected = (
        {args.variant: VARIANTS[args.variant]}
        if args.variant is not None
        else VARIANTS
    )
    for name, settings in selected.items():
        width, height = settings["render"]
        project = build().model_copy(deep=True)
        project.project_id = f"synthetic-nolan-algebra-{name}"
        project.title = f"{project.title} [{name}]"
        project.style = _style(bool(settings["dark"]))
        project.render = RenderSettings(
            renderer="cairo",
            quality="l",
            pixel_width=width,
            pixel_height=height,
            frame_rate=24,
            seed=23,
        )
        spec_path = spec_dir / f"{name}.json"
        write_json_atomic(spec_path, project)
        result = AuthoringPipeline(
            runs_dir=args.runs_dir,
            render_timeout_seconds=360,
        ).run(
            project,
            render=args.render,
            compose=args.render,
            use_cache=False,
        )
        summaries.append(
            {
                "variant": name,
                "resolution": [width, height],
                "style": "dark" if settings["dark"] else "light",
                "status": result.manifest.status,
                "run_dir": str(result.run_dir),
                "video": (
                    str(result.final_video)
                    if result.final_video is not None
                    else None
                ),
            }
        )
    write_json_atomic(args.runs_dir / "matrix-summary.json", summaries)
    print(args.runs_dir / "matrix-summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
