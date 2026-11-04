"""Export offline round62 evidence; never run models, render or create ZIPs."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.round62_audit import build_report, junit_summary, reference, SNAPSHOT_TEST


def read_json(path):
    raw = Path(path).read_bytes()
    # Windows PowerShell native redirection writes UTF-16 BOM; Python writes UTF-8.
    return json.loads(raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    read = lambda name: read_json(args.evidence_dir / name)
    runs = []
    for name in ('regression', 'focused_verified'):
        run = junit_summary(args.evidence_dir / f'{name}.xml',
                            int((args.evidence_dir / f'{name}_exit.txt').read_text(encoding='utf-8-sig')))
        run.update(junit=reference(ROOT, (args.evidence_dir / f'{name}.xml').resolve().relative_to(ROOT).as_posix()),
                   log=reference(ROOT, (args.evidence_dir / f'{name}.log').resolve().relative_to(ROOT).as_posix()),
                   scope='broad_regression_with_declared_exclusion' if name == 'regression' else 'focused_round53_62',
                   deselected=[SNAPSHOT_TEST] if name == 'regression' else [])
        runs.append(run)
    report = build_report(ROOT, runs, read('ocr_readiness.json'), read('commercial_synthetic.json'))
    import jsonschema
    jsonschema.validate(report, json.loads((ROOT / 'schemas/round62_homologation.schema.json').read_text(encoding='utf-8')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'technical_tests_passed': report['technical_tests_passed'],
                      'real_media_homologated': False, 'publication_approved': False}))
    return 0 if report['technical_tests_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
