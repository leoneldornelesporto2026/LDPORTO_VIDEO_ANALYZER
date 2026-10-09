"""Read historical ZIP members, verify references, and produce a new listening audit.

Run from project root with PYTHONPATH=src. No extraction or audio processing.
"""
import hashlib
import json
from pathlib import Path
import zipfile
from ldporto.uncertain_words_audit import audit_uncertain_words, write_listening_audit


def main():
    source = Path('automacao/evidencias/CHATGPT_REVIEW.zip')
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with zipfile.ZipFile(source) as archive:
        member = next(n for n in archive.namelist() if n.endswith('/analysis.json'))
        analysis_bytes = archive.read(member)
        analysis = json.loads(analysis_bytes)
        parent = member.rsplit('/', 1)[0]
        refs = {}
        def collection(key):
            ref = analysis[key + '_ref']
            path = parent + '/' + ref['path']
            payload = archive.read(path)
            actual = hashlib.sha256(payload).hexdigest()
            if actual != ref['sha256']:
                raise ValueError(f'Hash mismatch: {path}')
            rows = json.loads(payload)
            if len(rows) != ref['record_count']:
                raise ValueError(f'Count mismatch: {path}')
            refs[key] = {'member': path, 'sha256': actual, 'record_count': len(rows)}
            return rows
        data = {'words': collection('words'), 'segments': collection('transcript_segments'),
                'speech_overlaps': collection('speech_overlaps'),
                'unaligned_segments': analysis.get('unaligned_segments', [])}
        report = audit_uncertain_words(data, threshold=.6)
        report['source'] = {'zip': str(source), 'sha256': source_hash, 'analysis_member': member,
                            'analysis_sha256': hashlib.sha256(analysis_bytes).hexdigest(),
                            'collections': refs,
                            'build_label': analysis.get('provenance', {}).get('build_label'),
                            'producer_version': analysis.get('provenance', {}).get('producer_version'),
                            'scope': 'historical_S4_evidence_not_current_pipeline_execution',
                            'threshold_basis': 'current_config_default_0.6_not_proven_historical_setting',
                            'historical_quality_metrics': analysis.get('transcription_quality', {}),
                            'prompt_baseline_fraction': .1933,
                            'prompt_baseline_reproduced': round(report['original_flagged_fraction'], 4) == .1933}
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    write_listening_audit(report, 'automacao/execucao/etapa19_audit')
    print(json.dumps({k: report[k] for k in ('word_count', 'original_flagged_count',
                                           'original_flagged_fraction', 'categories',
                                           'flagged_signature_partition', 'samples')}, ensure_ascii=True))


if __name__ == '__main__':
    main()
