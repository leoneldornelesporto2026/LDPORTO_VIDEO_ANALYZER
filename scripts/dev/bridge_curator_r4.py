"""Audit a second-curation ZIP and optionally export a Curator V2-compatible folder."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ldporto.curator_bridge import audit_second_curation_package, export_legacy_curator_bridge


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True, help='SECOND_CURATION_READY/PARTIAL ZIP')
    parser.add_argument('--output', help='Parent folder for a new legacy Curator bridge; omitted = audit only')
    parser.add_argument('--report', help='Optional JSON audit report')
    args = parser.parse_args()
    audit = audit_second_curation_package(args.package)
    if args.output:
        if not audit['bridge_possible']:
            print(json.dumps(audit, ensure_ascii=False, indent=2))
            return 2
        audit['export'] = export_legacy_curator_bridge(args.package, args.output)
    if args.report:
        p = Path(args.report)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit['validation']['status'] == 'valid' else 2


if __name__ == '__main__':
    raise SystemExit(main())
