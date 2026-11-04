"""Offline JSON-only goldset and paired comparison. Never opens source media.

PYTHONPATH=src python scripts/dev/visual_review_stage50.py create --analysis analysis.json --output new_review.json
PYTHONPATH=src python scripts/dev/visual_review_stage50.py compare --goldset reviewed.json --before before.json --after after.json --output new_comparison.json
"""
import argparse
import json
from pathlib import Path

from ldporto.visual_review import create_goldset, compare_goldset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create')
    create.add_argument('--analysis', type=Path, required=True)
    create.add_argument('--limit', type=int, default=16)
    create.add_argument('--window-seconds', type=float, default=4.)
    compare = commands.add_parser('compare')
    for name in ('goldset', 'before', 'after'):
        compare.add_argument('--' + name, type=Path, required=True)
    for command in (create, compare):
        command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    def read(path):
        return json.loads(path.read_text(encoding='utf-8-sig'))
    if args.command == 'create':
        result = create_goldset(read(args.analysis), limit=args.limit, window_seconds=args.window_seconds)
    else:
        result = compare_goldset(read(args.goldset), read(args.before), read(args.after))
    encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves prior analyses and reviewer annotations.
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(encoded + '\n')
    print(json.dumps({'output': str(args.output), 'status': result.get('status'),
                      'improvement_accepted': result.get('improvement_accepted')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
