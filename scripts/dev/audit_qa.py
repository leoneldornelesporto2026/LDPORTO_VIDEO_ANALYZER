"""Read historical evidence ZIPs without extraction, media processing or mutation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ldporto.qa_audit import audit_qa, qa_audit_markdown


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-zip', type=Path, required=True)
    parser.add_argument('--curation-zip', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    evidence_root = Path('automacao/evidencias').resolve()
    output = args.output_dir.resolve()
    if output == evidence_root or evidence_root in output.parents:
        parser.error('Output must not modify automacao/evidencias')
    with ZipFile(args.review_zip) as archive:
        def read(name):
            matches = [n for n in archive.namelist() if n == name or n.endswith('/' + name)]
            if len(matches) != 1:
                raise ValueError(f'Expected one {name}, got {len(matches)}')
            return json.loads(archive.read(matches[0]))
        analysis = {name: read(name + '.json') for name in (
            'questions_answers', 'question_candidates', 'question_answer_pairs', 'transcript_segments')}
        declared = read('qa_summary.json')
    with ZipFile(args.curation_zip) as archive:
        exported = json.loads(archive.read('editorial/qa_pairs.json'))
        candidates = json.loads(archive.read('editorial/candidate_catalog.json'))['candidates']
    result = audit_qa(analysis, exported_rows=exported, candidates=candidates)
    result['provenance'] = {'scope': 'historical_Joao_Gordo_R4.9-S4_not_current_code_execution',
        'sources': [{'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                    for path in (args.review_zip, args.curation_zip)], 'declared_qa_metrics': declared}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'QA_AUDIT_ETAPA_07.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / 'QA_AUDIT_ETAPA_07.md').write_text(qa_audit_markdown(result), encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('counts', 'rates', 'category_counts',
        'reason_counts', 'suspect_pair_sample')}, ensure_ascii=True))


if __name__ == '__main__':
    main()
