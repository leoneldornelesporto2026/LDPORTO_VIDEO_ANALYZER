"""Stage 64: dry-run by default; --apply requires a previously reviewed snapshot."""
import argparse
import json
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ldporto.curation_recovery import recover
from ldporto.export_privacy import safe_path, sanitize_export


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', required=True)
    parser.add_argument('--cache', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--snapshot')
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.apply and (not args.snapshot or not args.output):
        parser.error('--apply requires --snapshot and --output')
    path = Path(args.report).absolute()
    source = safe_path(args.analysis)
    if path.is_relative_to(source):
        parser.error('report must be outside original analysis')
    ancestor = path.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    safe_path(ancestor)
    if path.exists():
        safe_path(path)
    try:
        hashes = json.loads(Path(args.snapshot).read_text(encoding='utf-8'))['reference_hashes'] if args.snapshot else None
        report = recover(args.analysis, args.cache, args.output, apply=args.apply, expected_hashes=hashes)
    except (ValueError, OSError, KeyError) as exc:
        report = {'status': 'blocked', 'error_type': type(exc).__name__, 'publication_ready': False}
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_path(path.parent)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as temporary:
        temporary.write(json.dumps(sanitize_export(report), ensure_ascii=False, sort_keys=True, indent=2))
    try:
        os.replace(temporary.name, path)
    finally:
        Path(temporary.name).unlink(missing_ok=True)
    print(json.dumps({'mode': report.get('mode'), 'can_replay': report.get('can_replay'),
                      'status': report.get('status'), 'publication_ready': False}))
    return 2 if report.get('status') == 'blocked' or report.get('can_replay') is False else 0


if __name__ == '__main__':
    raise SystemExit(main())
