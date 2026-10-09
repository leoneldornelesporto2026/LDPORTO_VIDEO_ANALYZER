from copy import deepcopy
import csv
import json
import pytest
from ldporto.uncertain_words_audit import audit_uncertain_words, write_listening_audit
from ldporto.diarization import overlap_intervals


def test_categories_partition_flags_without_claiming_errors():
    words = [
        {'word': 'mano', 'confidence': .2, 'needs_review': True},
        {'word': 'João,', 'confidence': .9, 'needs_review': False},
        {'word': '[inaudível]', 'confidence': None, 'needs_review': True},
        {'word': '...', 'confidence': .9, 'needs_review': True},
        {'word': 'ca-', 'confidence': .9, 'timestamp_repaired': True, 'needs_review': True},
        {'word': '[risos]', 'confidence': .9, 'needs_review': False},
        {'word': 'literal', 'confidence': .9, 'needs_review': True},
    ]
    for i, w in enumerate(words):
        w.update(start=i, end=i+1, word_id=f'W{i}', segment_id='S')
    data = {'words': words, 'segments': [{'segment_id': 'S', 'start': 0, 'end': 7,
                                         'text': 'mano João, [inaudível] ... ca- [risos] literal'}]}
    before = deepcopy(data)
    report = audit_uncertain_words(data, overlaps=[{'start': 1, 'end': 2}])
    assert data == before
    assert report['word_count'] == 7 and report['original_flagged_count'] == 5
    assert sum(report['flagged_signature_partition'].values()) == 5
    assert report['categories']['asr_confidence']['flagged_count'] == 2
    assert report['categories']['punctuation']['observed_count'] == 1
    assert report['categories']['truncation']['observed_count'] == 1
    assert report['categories']['timestamps']['observed_count'] == 1
    assert report['categories']['unexplained_flag']['observed_count'] == 1
    assert report['categories']['overlapping_speech']['flagged_count'] == 0
    assert report['samples']['slang_candidate']['word_indices'] == [0]
    assert report['samples']['name_candidate']['word_indices'] == [1]
    assert report['samples']['laughter_marker']['word_indices'] == [5]
    assert report['segments'][0]['flagged_word_count'] == 5
    assert all(r['corrected_word'] is None and r['confirmed_error'] is None for r in report['words'])
    assert report['transcription_error_rate'] is None and not report['publication_ready']


def test_overlap_sweep_and_word_boundaries_do_not_infer_inaudible_words():
    turns = [{'start': 0, 'end': 3, 'speaker': 'A'},
             {'start': 1, 'end': 2, 'speaker': 'B'},
             {'start': 2, 'end': 4, 'speaker': 'C'}]
    intervals = overlap_intervals(turns)
    assert [(r['start'], r['end'], r['speakers']) for r in intervals] == [(1, 2, ['A', 'B']), (2, 3, ['A', 'C'])]
    words = [{'word': '[inaudível]', 'start': 0, 'end': 1, 'confidence': None},
             {'word': 'texto', 'start': 1.5, 'end': 2.5, 'confidence': .9},
             {'word': 'literal', 'start': 3, 'end': 4, 'confidence': .9}]
    report = audit_uncertain_words({'words': words}, overlaps=intervals)
    assert report['categories']['overlapping_speech']['observed_count'] == 1
    assert report['words'][1]['overlap_intersections'] == [{'start': 1.5, 'end': 2}, {'start': 2, 'end': 2.5}]
    assert report['words'][0]['word'] == '[inaudível]'
    assert report['words'][0]['corrected_word'] is None


def test_empty_and_text_only_segments_have_no_fabricated_denominator():
    report = audit_uncertain_words({'words': [], 'segments': [{'segment_id': 'S', 'text': '[inaudível]'}],
                                    'unaligned_words': [{'word': 'hipótese'}]})
    assert report['word_count'] == 0 and report['original_flagged_fraction'] is None
    assert report['unaligned_word_count'] == 1 and report['text_only_segment_count'] == 1
    assert report['words'] == [] and report['segments'][0]['corrected_text'] is None
    assert all(c['fraction_all_words'] is None for c in report['categories'].values())


def test_listening_tables_preserve_literal_source_and_refuse_overwrite(tmp_path):
    data = {'words': [{'word': 'nome, literal', 'start': 2, 'end': 3, 'confidence': .9,
                       'segment_id': 'S', 'needs_review': True}],
            'segments': [{'segment_id': 'S', 'text': 'nome, literal', 'start': 2, 'end': 3}]}
    report = audit_uncertain_words(data)
    out = tmp_path / 'new_audit'
    write_listening_audit(report, out)
    assert json.loads((out / 'audit.json').read_text(encoding='utf-8')) == report
    with (out / 'listening_words.csv').open(encoding='utf-8-sig', newline='') as f:
        row = next(csv.DictReader(f))
    assert row['word'] == 'nome, literal' and row['start'] == '2' and row['corrected_word'] == ''
    with pytest.raises(FileExistsError):
        write_listening_audit(report, out)


@pytest.mark.parametrize('probability', [float('nan'), True, -1, 2, 'unknown'])
def test_invalid_confidence_is_missing_evidence(probability):
    report = audit_uncertain_words({'words': [{'word': 'literal', 'confidence': probability}]})
    assert report['categories']['asr_confidence']['observed_count'] == 1
    assert report['categories']['timestamps']['observed_count'] == 1
    assert report['confirmed_corrections'] is None


def test_historical_flags_are_not_the_prompt_percentage():
    import hashlib
    from pathlib import Path
    import zipfile
    source = Path(__file__).resolve().parents[2] / 'automacao/evidencias/CHATGPT_REVIEW.zip'
    with zipfile.ZipFile(source) as archive:
        member = next(n for n in archive.namelist() if n.endswith('/analysis.json'))
        analysis = json.loads(archive.read(member))
        parent = member.rsplit('/', 1)[0]
        def read_collection(key):
            ref = analysis[key + '_ref']
            payload = archive.read(parent + '/' + ref['path'])
            assert hashlib.sha256(payload).hexdigest() == ref['sha256']
            records = json.loads(payload)
            assert len(records) == ref['record_count']
            return records
        words = read_collection('words')
        before = deepcopy(words)
        report = audit_uncertain_words({'words': words, 'segments': read_collection('transcript_segments')},
                                        overlaps=read_collection('speech_overlaps'))
    assert words == before
    assert analysis['provenance']['build_label'] == 'R4.9-S4-TRACKING-FACIAL'
    assert report['word_count'] == 6840 and report['original_flagged_count'] == 534
    assert report['categories']['asr_confidence']['observed_count'] == 529
    assert report['flagged_signature_partition'] == {'asr_confidence': 401,
        'asr_confidence+overlapping_speech': 128, 'hallucination_proxy': 1,
        'overlapping_speech+timestamps': 1, 'timestamps': 3}
    assert round(report['original_flagged_fraction'], 4) != .1933
    assert report['samples']['laughter_marker']['eligible_count'] == 0
