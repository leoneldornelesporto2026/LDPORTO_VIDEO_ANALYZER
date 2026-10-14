"""Read-only historical package replay; no acoustic/model or human review."""
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys
import zipfile
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.asr_comparison import source_review_dossier, review_reason_metrics
from ldporto.transcription import flag_alternative_disagreements, annotate_review, word_text

source = ROOT / 'pacotes_para_enviar/SECOND_CURATION_PARTIAL_jNQXAC9IVRw_20261013_035536_877801_09f678.zip'
with zipfile.ZipFile(source) as archive:
    for name in archive.namelist():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or PureWindowsPath(name).drive or '\\' in name:
            raise ValueError('Unsafe archive member')
    manifest = json.loads(archive.read('SECOND_CURATION_MANIFEST.json'))
    for row in manifest['files']:
        payload = archive.read(row['path'])
        if hashlib.sha256(payload).hexdigest() != row['sha256']:
            raise ValueError('Historical package hash mismatch')
    data = {'words': [json.loads(line) for line in archive.read('transcript/relevant_words.jsonl').decode().splitlines()],
            'segments': [json.loads(line) for line in archive.read('transcript/relevant_segments.jsonl').decode().splitlines()],
            'transcription_alternatives': json.loads(archive.read('transcript/transcription_alternatives.json')),
            'source_comparisons': json.loads(archive.read('transcript/transcription_provenance.json'))['source_comparisons'],
            'review_budget': json.loads(archive.read('transcript/review_budget.json'))}
    translations = json.loads(archive.read('transcript/translations.json'))
    original_transcript = archive.read('transcript/transcript.txt').decode()
before = deepcopy(data)
word_keys = ('word_id', 'word', 'raw', 'start', 'end', 'confidence', 'needs_review', 'review_reasons',
             'asr_discrepancy', 'speech_overlap', 'segment_id')
compact = {'provenance': {'source_package': source.name,
                        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                        'kind': 'historical_real_asr_output_not_human_ground_truth'},
           'words': [{key: word.get(key) for key in word_keys if key in word} for word in before['words']],
           'transcription_alternatives': [{key: row.get(key) for key in ('start', 'end', 'selected_text', 'hypotheses_disagree')}
                | {'alternatives': [{'text': alt.get('text'), 'words': [{key: word.get(key) for key in
                         ('word', 'raw', 'start', 'end', 'confidence')} for word in alt.get('words', [])]}
                    for alt in row.get('alternatives', [])]} for row in before['transcription_alternatives']],
           'source_comparisons': [{key: row.get(key) for key in ('start', 'end', 'needs_review')}
                | {'hypotheses': {label: {'text': hypothesis.get('text')}
                                 for label, hypothesis in row['hypotheses'].items()}} for row in before['source_comparisons']]}
(ROOT / 'src/tests/fixtures/sol_v3_asr_historical.json').write_text(
    json.dumps(compact, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
flag_alternative_disagreements(data, recompute=True)
annotate_review(data, .6)
dossier = source_review_dossier(data, 19.014)
literal_fields = lambda rows: [{key: row.get(key) for key in ('word_id', 'word', 'raw', 'start', 'end', 'confidence')} for row in rows]
assert literal_fields(before['words']) == literal_fields(data['words'])
result = {'schema_version': '1.0', 'validation_kind': 'integration_local_historical_json_reclassification',
    'source_package': source.name, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'internal_hashes_verified': len(manifest['files']), 'source_duration_seconds': 19.014,
    'before': review_reason_metrics(before['words']), 'after': review_reason_metrics(data['words']),
    'original_transcript': original_transcript, 'canonical_text': word_text(data['words']), 'translations': translations,
    'original_word_text_timing_probability_preserved': True, 'new_model_inference_calls': 0,
    'historical_multipass': before['review_budget'], 'source_audio_review': dossier,
    'hypothesis_comparison': data['hypothesis_comparison'],
    'flagged_after': [{key: row.get(key) for key in ('word_id', 'word', 'start', 'end', 'review_reasons')}
                      for row in data['words'] if row.get('needs_review')],
    'comparisons': [{key: row.get(key) for key in ('start', 'end', 'hypotheses_disagree', 'text_differs',
                                                 'affected_word_ids', 'boundary_word_ids', 'local_comparison')}
                    for row in data['transcription_alternatives']],
    'human_review': False, 'verified_correct_word_count': None, 'word_error_rate': None, 'publication_ready': False,
    'before_package_available_at_expected_location': (ROOT / 'pacotes_para_enviar/SECOND_CURATION_PARTIAL_jNQXAC9IVRw_20261012_232326_642182_7f5d97.zip').is_file()}
destination = Path(__file__).with_name('asr_historical_replay.json')
destination.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
print(json.dumps({key: result[key] for key in ('validation_kind', 'source_package', 'internal_hashes_verified',
                                              'new_model_inference_calls', 'flagged_after')}, ensure_ascii=False))
print('FLAGGED_BEFORE', result['before']['flagged_word_count'], 'FLAGGED_AFTER', result['after']['flagged_word_count'])
