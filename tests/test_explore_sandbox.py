"""The one enforced rule of `explore/`.

Adapted from HERMES, which arrived at it the expensive way: a cleanup session found 1.77 GB of
experiment databases sitting beside production, distinguishable from the real store only by
filename, and one of them turned out not to be an experiment at all — proving that took a schema
diff.

NOLAN already has the same bill accrued. `projects/` is 8.4 GB across 37 entries, of which 14
(2.3 GB) are experiment-shaped — `aidc-2beat-test`, `homer-auto`, `_sem_shake`, `aeneid-auto-test`
— sitting next to `the-diamond-illusion` and `holbein-dance-of-death` with nothing but a naming
convention between them.

So: an experiment lives in `explore/<YYYY-MM-DD>-<slug>/` and its README carries a `status:`.
That is the whole contract. Everything else about an experiment is its own business — experiments
differ enormously in shape, and a template that suits all of them suits none.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EXPLORE = REPO / "explore"

DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*$")
STATUS_RE = re.compile(r"^status:\s*(active|promoted|abandoned)\s*$", re.M | re.I)
VALID = {"active", "promoted", "abandoned"}


def _experiments():
    if not EXPLORE.is_dir():
        return []
    return [d for d in sorted(EXPLORE.iterdir())
            if d.is_dir() and not d.name.startswith((".", "_"))]


def test_every_explore_dir_is_dated_and_slugged():
    """The date is what makes an experiment's AGE visible. An undated directory becomes furniture
    — nobody can tell a live experiment from one abandoned eighteen months ago."""
    bad = [d.name for d in _experiments() if not DIR_RE.match(d.name)]
    assert not bad, ("explore/ dirs must be <YYYY-MM-DD>-<slug>: " + ", ".join(bad))


def test_every_experiment_declares_a_status():
    """`status:` is the whole enforced contract.

    `abandoned` matters most and is the one people want to delete: a dead end kept is the record
    of why nobody should retry it, and deleting the directory throws that away.
    """
    missing, invalid = [], []
    for d in _experiments():
        readme = d / "README.md"
        if not readme.exists():
            missing.append(f"{d.name} (no README.md)")
            continue
        m = STATUS_RE.search(readme.read_text(encoding="utf-8"))
        if not m:
            missing.append(f"{d.name} (README has no `status:` line)")
        elif m.group(1).lower() not in VALID:
            invalid.append(f"{d.name} -> {m.group(1)}")
    assert not missing, "experiments must declare a status: " + "; ".join(missing)
    assert not invalid, "status must be active|promoted|abandoned: " + "; ".join(invalid)


@pytest.mark.skipif(not (REPO / "explore").is_dir(), reason="no explore/ yet")
def test_experiments_do_not_write_into_projects():
    """An experiment that writes into `projects/` is the failure this directory exists to stop —
    it is how 2.3 GB of test runs ended up beside real productions in the first place.

    Checked by SOURCE INSPECTION rather than at runtime: a test cannot catch a write that only
    happens when someone runs the experiment by hand.
    """
    offenders = []
    for d in _experiments():
        for py in d.rglob("*.py"):
            src = py.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r'(write_text|mkdir|open)\s*\([^)]*projects[/\\]', src):
                line = src[:m.start()].count("\n") + 1
                offenders.append(f"{py.relative_to(REPO)}:{line}")
    assert not offenders, (
        "explore code must not write into projects/ — read production, write locally: "
        + ", ".join(offenders))
