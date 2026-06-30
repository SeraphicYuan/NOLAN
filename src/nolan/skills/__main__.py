import sys

from . import _cli, health_report

if len(sys.argv) > 1 and sys.argv[1] == "health":
    rows = health_report()
    if not rows:
        print("no skill feedback recorded yet (gates wire corrections via record_feedback)")
        raise SystemExit(0)
    print(f"{'skill':28} {'ver':>3} {'inv':>5} {'fb':>4} {'open':>5}   (revision queue: most open first)")
    for r in rows:
        print(f"{r['skill']:28} {str(r['version']):>3} {r['invocations']:>5} {r['feedback_total']:>4} {r['feedback_open']:>5}")
    raise SystemExit(0)

raise SystemExit(_cli())
