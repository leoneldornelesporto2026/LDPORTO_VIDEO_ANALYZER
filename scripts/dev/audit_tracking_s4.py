"""S4: diagnose raw embedding gaps, generate human goldset and evaluate labels.

Examples:
  python scripts/dev/audit_tracking_s4.py C:/analysis --output C:/s4_audit
  python scripts/dev/audit_tracking_s4.py C:/analysis --output C:/s4_audit --video C:/video.mp4
  python scripts/dev/audit_tracking_s4.py C:/analysis --output C:/s4_audit --evaluate C:/s4_audit/identity_annotations.csv
"""
import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src'))
from ldporto.person_reid import build_person_identities
from ldporto.config import DEFAULTS
from ldporto.visual_identity_audit import audit_embedding_gaps, compare_embedding_recovery
from ldporto.core import file_hash
from ldporto.identity_goldset import (sample_tracklets, write_annotation_csv,
                                      read_annotation_csv, evaluate_annotations, write_contact_sheet,
                                      sample_reid_pairs, compare_identity_annotations)


def read_artifact(source, filename):
    source = Path(source)
    if source.is_dir():
        # Files from a full run or nested review ZIP staging.
        matches = list(source.rglob(filename))
        if matches:
            return json.loads(matches[0].read_text(encoding='utf-8-sig'))
    elif source.suffix.lower() == '.zip':
        with zipfile.ZipFile(source) as z:
            matches = [name for name in z.namelist() if name.endswith('/'+filename) or name == filename]
            if matches:
                return json.loads(z.read(matches[0]))
    elif source.name == filename:
        return json.loads(source.read_text(encoding='utf-8-sig'))
    return None


def analyze(source, *, sample_limit=96):
    payload = read_artifact(source, '07_people_tracking.json')
    if payload is None:
        raise FileNotFoundError('07_people_tracking.json ausente na fonte.')
    vision = payload.get('data', payload)
    if not isinstance(vision, dict) or not isinstance(vision.get('observations'), list):
        raise ValueError('07_people_tracking.json nao contem observations validas.')
    existing = read_artifact(source, '08_person_reid.json')
    if existing:
        reid = existing.get('data', existing)
    else:
        reid = build_person_identities(vision, DEFAULTS['vision'])['data']
    report = audit_embedding_gaps(vision, reid)
    summary = read_artifact(source, 'analysis_summary.json') or {}
    report['source_sha256'] = (summary.get('metadata') or {}).get('sha256')
    report['producer_version'] = summary.get('producer_version')
    report['reid_review_pairs'] = sample_reid_pairs(reid, limit=sample_limit)
    return report, sample_tracklets(vision, reid, limit=sample_limit)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('source', type=Path, help='Diretorio ou ZIP com 07_people_tracking.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--video', type=Path, help='Fonte local para quadros de revisao visual (opcional)')
    parser.add_argument('--evaluate', type=Path, help='CSV revisado manualmente, annotation_status=verified')
    parser.add_argument('--sample-limit', type=int, default=96)
    parser.add_argument('--comparison-records', type=Path,
                        help='JSON com before/after: hashes da fonte/protocolo/amostra e verified_quality humana')
    parser.add_argument('--identity-comparison-records', type=Path,
                        help='JSON before/after com source_sha256, protocol_sha256 e annotations verificadas')
    args = parser.parse_args()
    if not 1 <= args.sample_limit <= 500:
        parser.error('--sample-limit deve estar entre 1 e 500')
    report, samples = analyze(args.source, sample_limit=args.sample_limit)
    if args.video:
        expected_hash = report.get('source_sha256')
        if not expected_hash or file_hash(args.video) != expected_hash:
            raise ValueError('Fonte do contact sheet nao comprovada pelo SHA256 da analise.')
    if args.comparison_records:
        records = json.loads(args.comparison_records.read_text(encoding='utf-8-sig'))
        report['comparability'] = compare_embedding_recovery(records['before'], records['after'])
        report['comparability']['scope'] = 'supplied_comparison_records_only'
    if args.identity_comparison_records:
        records = json.loads(args.identity_comparison_records.read_text(encoding='utf-8-sig'))
        report['identity_comparison'] = compare_identity_annotations(records['before'], records['after'])
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'tracking_s4_report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    csv_path = args.output/'identity_annotations.csv'
    if csv_path.exists():
        old_ids = {str(row['track_id']) for row in read_annotation_csv(csv_path)}
        new_ids = {str(row['track_id']) for row in samples}
        if old_ids != new_ids:
            raise ValueError('CSV de anotacoes preexistente pertence a outra amostra. '
                             'Use --output em outra pasta para preservar a revisao original.')
    else:
        write_annotation_csv(samples, csv_path)
    if args.video:
        write_contact_sheet(samples, args.video, args.output/'identity_contact_sheet.jpg')
    if args.evaluate:
        annotated = read_annotation_csv(args.evaluate)
        expected_ids = {str(row['track_id']) for row in samples}
        if not {str(row['track_id']) for row in annotated}.issubset(expected_ids):
            raise ValueError('Arquivo de anotacoes contem track_ids alheios a este run.')
        result = evaluate_annotations(annotated)
        (args.output/'identity_goldset_metrics.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report,ensure_ascii=False,indent=2))
    print(f'Anotacao: {csv_path}')


if __name__=='__main__':
    main()
