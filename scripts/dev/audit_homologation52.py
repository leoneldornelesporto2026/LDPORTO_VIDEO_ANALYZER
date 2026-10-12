"""Read-only stage 52 report; no inference, extraction, upload or ZIP generation."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ldporto.homologation_audit import audit_package, compare_outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', action='append', required=True)
    parser.add_argument('--feedback')
    parser.add_argument('--baseline')
    parser.add_argument('--current')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    inputs = [Path(p).resolve() for p in args.package +
              [p for p in (args.feedback, args.baseline, args.current) if p]]
    if output in inputs or output.suffix.lower() != '.json':
        parser.error('output must be a new JSON report, never an input or ZIP')
    report = {'verification_scope': 'offline_read_only', 'historical_reprocessing': False,
              'publication_ready': False, 'human_review_status': 'human_review_pending',
              'packages': [audit_package(p, args.feedback) for p in args.package],
              'comparison': compare_outputs(args.baseline, args.current)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'output': str(output), 'statuses': [r['status'] for r in report['packages']]}))
    return 0 if all(r['status'] == 'offline_verified' for r in report['packages']) else 2


if __name__ == '__main__':
    raise SystemExit(main())
