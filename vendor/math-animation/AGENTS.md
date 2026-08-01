# Python Environment Rules

This package is vendored into NOLAN and runs across **two** conda envs. Read
`CLAUDE.md` for why; the short version:

- Authoring (validate / compile / pedagogy / review / cache) — pydantic only:
  python `D:\env\nolan\python.exe`, pip `D:\env\nolan\Scripts\pip.exe`.
- Rendering (Manim + LaTeX + dvisvgm): python `D:\env\mas\python.exe`, pip
  `D:\env\mas\Scripts\pip.exe`.

Always pass `-X utf8`. Do not use system python and do not create a `.venv`.

The `/opt/miniconda3/envs/mas/...` paths still in `docs/V0_*.md`,
`docs/FEATURED_STRESS_TEST.md` and `docs/NOLAN_HANDOFF.md` are the upstream
acceptance record — they document runs that happened, not commands to re-run
here.
