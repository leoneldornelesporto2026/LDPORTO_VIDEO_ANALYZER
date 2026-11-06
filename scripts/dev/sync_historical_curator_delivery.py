"""Inventory/re-deliver historical Analyzer R6 exports without inference or edits."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ldporto.historical_curator_sync import sync_historical  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Dry-run inventory of historical R6 exports; --apply enables atomic Curator delivery"
    )
    parser.add_argument("--scan-root", help="Scan immediate child folders of this analysis directory")
    parser.add_argument("--analysis-dir", action="append", default=[],
                        help="One explicit previous analysis directory; repeat to select multiple")
    parser.add_argument("--curator-root", help="Existing local Curator repository root")
    parser.add_argument("--max-runs", type=int, default=250)
    parser.add_argument("--apply", action="store_true",
                        help="Explicitly deliver only already validated R6 ZIPs")
    args = parser.parse_args(argv)
    result = sync_historical(
        analysis_root=args.scan_root, analysis_dirs=args.analysis_dir,
        curator_root=args.curator_root, apply=args.apply, max_runs=args.max_runs,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    invalid = any(row["status"].startswith("BLOCKED") for row in result["rows"])
    return 2 if invalid else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print("HISTORICAL_SYNC_BLOCKED:", exc, file=sys.stderr)
        raise SystemExit(2)
