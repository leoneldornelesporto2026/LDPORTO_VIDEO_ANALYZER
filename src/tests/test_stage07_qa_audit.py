"""Synthetic/offline Q&A evidence; no audio or inference is performed."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from ldporto.qa_audit import audit_qa, qa_audit_markdown
from ldporto.semantic import questions_answers, qa_contract


def segment(sid, text, speaker, start, end):
    return {'segment_id': sid, 'text': text, 'speaker': speaker, 'start': start, 'end': end}


def analysis(rows):
    records = questions_answers(rows)
    return {'transcript_segments': rows, 'questions_answers': records, **qa_contract(records)}


def legacy_analysis(rows, *, substantive=False):
    """Explicit synthetic legacy records: audit old output independently of the associator."""
    answer = rows[-1]
    records = []
    for index, question in enumerate(rows[:-1]):
        record = questions_answers([question])[0]
        record.update(answer=answer['text'], answer_start=answer['start'], answer_end=answer['end'],
            answer_segment_ids=[answer['segment_id']], answer_speaker=answer['speaker'],
            answer_status='linked_candidate', association_status='answered_candidate', unresolved_reason=None,
            answer_closes_itself=True, question_answer_complete=True,
            answer_relevance={'shared_terms': [] if substantive else ['comecou'],
                              'direct_response_marker': False,
                              'substantive_different_speaker_candidate': substantive},
            question_id=f'Q_{index:04}')
        records.append(record)
    return {'transcript_segments': rows, 'questions_answers': records, **qa_contract(records)}


@pytest.mark.parametrize('question', ['Como?', 'Quem?'])
def test_short_question_next_turn_and_completeness_requires_review(question):
    a = analysis([segment('S1', question, 'A', 0, 1),
                  segment('S2', 'Sim, eu comecei naquele festival.', 'B', 1.2, 4)])
    before = deepcopy(a)
    result = audit_qa(a)
    case = result['cases'][0]
    assert result['counts']['detected_question_ids'] == 1
    assert result['counts']['associated_pair_ids'] == 1
    assert result['counts']['heuristic_complete_pair_ids'] == 1
    assert case['requires_review'] is True and case['audio_verified_complete'] is None
    assert case['reasons'] == ['heuristic_completeness_not_audio_verified']
    assert case['segment_evidence']['answer'][0]['matches'] == [a['transcript_segments'][1]]
    assert result['counts']['exported_reference_ids'] is None
    assert a == before


def test_short_yes_no_ambiguity_does_not_increase_existing_counts():
    a = analysis([segment('S1', 'Você começou?', 'A', 0, 1),
                  segment('S2', 'Sim, eu comecei ontem.', 'B', 2, 4)])
    result = audit_qa(a)
    assert result['counts']['associated_pair_ids'] == 0
    assert result['counts']['expected_answer_candidate_ids'] == 0
    assert 'short_interrogative_classified_as_banter' in result['cases'][0]['reasons']


def test_question_sequence_reuses_answer_without_inflating_independent_spans():
    a = legacy_analysis([segment('S1', 'Quando começou?', 'A', 0, 1),
                  segment('S2', 'Onde começou?', 'A', 1, 2),
                  segment('S3', 'Eu comecei no festival de música.', 'B', 2.1, 5)])
    result = audit_qa(a)
    assert result['counts']['associated_pair_ids'] == 2
    assert result['counts']['distinct_associated_answer_spans'] == 1
    assert result['suspect_pair_sample'] == ['Q_0000', 'Q_0001']
    assert all('shared_answer_span' in c['reasons'] for c in result['cases'])
    assert result['rates']['association']['denominator'] == 2
    assert result['rates']['association']['question_ids'] == ['Q_0000', 'Q_0001']


def test_question_in_another_turn_is_not_an_answer():
    a = analysis([segment('S1', 'Onde começou?', 'A', 0, 1),
                  segment('S2', 'Como começou?', 'B', 1.1, 2)])
    result = audit_qa(a)
    assert result['counts']['associated_pair_ids'] == 0
    assert result['rates']['unresolved']['numerator'] == result['rates']['unresolved']['denominator'] == 2
    assert all('question_without_observed_answer_span' in c['categories'] for c in result['cases'])


@pytest.mark.parametrize(('question', 'category'), [
    ('Quem nunca?', 'rhetorical_question_candidate'),
    ('Ou melhor, onde começou?', 'reformulation_cue'),
    ('Qual foi a primeira vez que tu', 'truncated_phrase_cue'),
])
def test_review_categories_have_literal_cues(question, category):
    result = audit_qa(analysis([segment('S1', question, 'A', 0, 1)]))
    assert category in result['cases'][0]['categories']
    assert result['counts']['associated_pair_ids'] == 0


@pytest.mark.parametrize(('field', 'value', 'reason'), [
    ('answer_start', 99, 'answer_timestamp_mismatch'),
    ('answer_speaker', 'A', 'answer_speaker_mismatch'),
    ('answer_segment_ids', ['ABSENT'], 'answer_segment_missing'),
    ('answer', 'Texto adulterado.', 'answer_text_mismatch'),
])
def test_cross_checks_segment_timestamp_speaker_and_text(field, value, reason):
    a = analysis([segment('S1', 'Quando começou?', 'A', 0, 1),
                  segment('S2', 'Eu comecei ontem.', 'B', 2, 4)])
    for collection in ('questions_answers', 'question_candidates', 'question_answer_pairs'):
        a[collection] = deepcopy(a[collection])
        a[collection][0][field] = value
    result = audit_qa(a)
    assert reason in result['cases'][0]['reasons']
    assert result['suspect_pair_sample'] == ['Q_0000']


def test_substantive_unrelated_turn_is_sampled_as_suspect_not_confirmed_false():
    a = legacy_analysis([segment('S1', 'Qual disco lançou?', 'A', 0, 1),
                  segment('S2', 'A temperatura tropical trouxe ventos fortes na costa distante.', 'B', 2, 5)], substantive=True)
    result = audit_qa(a)
    assert result['counts']['associated_pair_ids'] == 1
    assert 'substantive_turn_only_relevance' in result['cases'][0]['reasons']
    assert result['suspect_pair_sample'] == ['Q_0000']
    assert result['verified_complete_count'] is None


def test_sources_exports_links_and_missing_evidence_are_distinct():
    a = analysis([segment('S1', 'Quem nunca?', 'A', 0, 1)])
    candidates = [{'candidate_id': 'C1', 'question_answer_linkage': ['Q_0000', 'Q_ABSENT', 'Q_ABSENT']}]
    exported = [deepcopy(a['questions_answers'][0]), {'question_id': 'Q_ABSENT'}]
    result = audit_qa(a, exported_rows=exported, candidates=candidates)
    assert result['counts']['detected_question_ids'] == 1
    assert result['counts']['non_answer_diagnostic_ids'] == 1
    assert result['counts']['exported_reference_ids'] == 2
    assert result['counts']['candidate_link_occurrences'] == 3
    assert result['counts']['candidate_link_ids'] == 2
    assert result['rates']['candidate_reference_export_coverage']['numerator'] == 2
    assert result['rates']['candidate_reference_export_coverage']['denominator'] == 2
    missing = result['cases'][1]
    assert missing['question_id'] == 'Q_ABSENT' and missing['question'] is None
    assert missing['associated_candidate'] is None
    assert missing['reasons'] == ['question_record_missing', 'question_text_unavailable']
    assert result['rates']['association']['value'] is None
    assert 'Q_ABSENT' in qa_audit_markdown(result)


def test_conflicting_sources_duplicate_export_and_dangling_link_are_reported():
    a = analysis([segment('S1', 'Como?', 'A', 0, 1)])
    a['question_candidates'] = deepcopy(a['question_candidates'])
    a['question_candidates'][0]['question_start'] = 99
    result = audit_qa(a, exported_rows=[{'question_id': 'Q_0000'}, {'question_id': 'Q_0000'}],
        candidates=[{'candidate_id': 'C1', 'question_answer_linkage': ['Q_MISSING']}])
    assert 'source_record_conflict' in result['cases'][0]['reasons']
    assert 'duplicate_export_id' in result['cases'][0]['reasons']
    assert 'candidate_reference_not_exported' in result['cases'][1]['reasons']
    assert result['counts']['detected_question_ids'] == 1
    assert result['counts']['exported_reference_ids'] == 1
    assert result['counts']['exported_reference_rows'] == 2
    assert result['rates']['candidate_reference_export_coverage']['numerator'] == 0


def test_report_engine_emits_audit_of_actual_final_reference_table(tmp_path):
    import json
    from zipfile import ZipFile
    from ldporto.reports import ReportEngine
    from test_stage06_report_coherence import fixture
    a = fixture()
    a.update(analysis([segment('S1', 'Como?', 'A', 0, 1),
                       segment('S2', 'Sim, eu comecei ontem.', 'B', 2, 4)]))
    ctx = SimpleNamespace(output=tmp_path / 'reports', signature='stage07-fixture',
        config={'strict': False, 'export': {'second_curation_output_dir': str(tmp_path / 'packages')}})
    ReportEngine().run(ctx, a, [])
    audit = json.loads((ctx.output / 'qa_audit.json').read_text(encoding='utf-8'))
    with ZipFile(a['second_curation_export']['path']) as archive:
        exported = json.loads(archive.read('editorial/qa_pairs.json'))
    assert audit['counts']['exported_reference_ids'] == len({r['question_id'] for r in exported})
    assert 'qa_audit.json' in json.loads((ctx.output / 'manifest.json').read_text(encoding='utf-8'))['files']
    assert a['final_package_gate']['publication_ready'] is False
