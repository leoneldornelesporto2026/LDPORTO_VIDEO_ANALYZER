"""One explicitly authorized 10–30s local canary. No ASR, ZIP, batch or publish."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ldporto.curator_delivery import load_json
from ldporto.curation_canary import run_real_canary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', required=True, help='Existing short-media evidence JSON, exact source hash')
    parser.add_argument('--source', required=True)
    parser.add_argument('--candidate-id', required=True)
    parser.add_argument('--output', required=True, help='New directory; never overwritten')
    parser.add_argument('--authorize-short-media', action='store_true')
    parser.add_argument('--ocr-languages', default='por+eng')
    args = parser.parse_args()
    report = run_real_canary(load_json(args.analysis), args.source, args.candidate_id, args.output,
        authorized=args.authorize_short_media, ocr_config={'languages': args.ocr_languages})
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report['real_canary_status'] == 'real_canary_pass' else 2


if __name__ == '__main__':
    raise SystemExit(main())
