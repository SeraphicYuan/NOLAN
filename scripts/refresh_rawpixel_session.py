"""Refresh NOLAN's Rawpixel session from the authorised Chrome CDP profile."""
from __future__ import annotations

import argparse
from pathlib import Path

from nolan.source_sessions import refresh_rawpixel_session


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Safely refresh Rawpixel cookie, user-agent and CDP settings in .env")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--verify-query", default="wave")
    parser.add_argument("--dry-run", action="store_true",
                        help="verify Chrome/session health without modifying .env")
    args = parser.parse_args(argv)

    try:
        result = refresh_rawpixel_session(
            cdp_url=args.cdp_url, env_path=args.env_file,
            verify_query=args.verify_query, dry_run=args.dry_run)
    except RuntimeError as exc:
        parser.exit(1, f"Rawpixel refresh failed: {exc}\n")

    action = "verified; .env unchanged" if result.dry_run else "refreshed"
    print(f"Rawpixel session {action}.")
    print(f"  Chrome session cookie: present ({result.cookie_count} Rawpixel cookies captured)")
    print(f"  Search verification: {result.search_rows} rows, total={result.search_total}")
    if result.env_path is not None and not result.dry_run:
        print(f"  Updated: {result.env_path}")
    print("  Secret values were not printed. Chrome CDP remains the preferred transport.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
