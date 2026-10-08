"""Read-only S2 integrity audit for existing second-curation ZIP or analysis.json.

No video, Whisper, Ollama, MediaPipe, GPU, cache modification or network access.

Examples (Windows CMD, inside Analyzer project root):
    py -3.11 scripts/dev/audit_pipeline_integrity_s2.py --package "C:\\path\\SECOND_CURATION_READY_....zip"
    py -3.11 scripts/dev/audit_pipeline_integrity_s2.py --analysis "analysis\\video_id\\analysis.json" --report "diagnostico_s2.json"
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ldporto.integrity_contracts import audit_editorial_contract
from ldporto.second_curation_export import validate_core_package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', help='Existing second-curation ZIP')
    parser.add_argument('--analysis', help='Existing analysis.json')
    parser.add_argument('--report', help='Write diagnostic report to JSON file')
    args = parser.parse_args()
    if not args.package and not args.analysis:
        parser.error('Provide --package and/or --analysis')
    report = {'schema_version': '1.0', 'scope': 'read_only_integrity_audit',
              'reprocessed_stages': [], 'source_video_loaded': False,
              'publication_authorized': False, 'results': {}}
    if args.package:
        report['results']['package'] = validate_core_package(Path(args.package))
    if args.analysis:
        raw = json.loads(Path(args.analysis).read_text(encoding='utf-8-sig'))
        report['results']['upstream'] = audit_editorial_contract(raw)
    integrity_ok = all(value.get('status') == 'valid' for value in report['results'].values())
    package_result = report['results'].get('package') or {}
    review_ready = (package_result.get('readiness') or {}).get('editorial_ready') is True and \
                   all((package_result.get('readiness') or {}).get(key) is True for key in ('transcript_ready', 'visual_ready'))
    report['integrity_status'] = 'PASS' if integrity_ok else 'BLOCKED'
    report['review_state'] = ('READY_FOR_REVIEW' if review_ready else 'PARTIAL') if package_result else 'NOT_ASSESSED'
    report['status'] = 'VALID_FOR_REVIEW' if integrity_ok and review_ready else 'VALID_PARTIAL' if integrity_ok else 'BLOCKED'
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(encoded + '\n', encoding='utf-8')
    print(encoded)
    return 0 if integrity_ok else 2


if __name__ == '__main__':
    sys.exit(main())
