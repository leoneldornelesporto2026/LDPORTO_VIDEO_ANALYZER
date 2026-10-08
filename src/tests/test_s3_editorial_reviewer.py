"""Reviewer cannot promote a provisional input to editorial readiness."""
from scripts.dev.review_editorial_s3 import evaluate


def test_offline_review_blocks_provisional_source():
    segment = {'segment_id': 'S0', 'start': 0, 'end': 45, 'speaker': 'A',
               'text': 'Um relato completo e compreensivel.'}
    candidate = {'moment_id': 'M1', 'ideal_start': 0, 'ideal_end': 45,
                 'evidence_segment_ids': ['S0'], 'editorial_score_final': .91,
                 'default_shortlist_eligible': True, 'clean_opening': True,
                 'clean_ending': True, 'topic_id': 'T', 'core_moment': {'text': segment['text']}}
    blocked = evaluate([candidate], [segment], [], [], False)
    assert blocked['status'] == 'PROVISIONAL_UPSTREAM_INCOMPLETE'
    assert blocked['shortlist_ids'] == []
    assert blocked['hypothetical_diagnostic_ids_not_shortlist'] == ['M1']
    review = evaluate([candidate], [segment], [], [], True)
    assert review['status'] == 'REVIEW_REQUIRED'
    assert review['shortlist_ids'] == ['M1']


def test_offline_review_does_not_force_36_provisional_candidates():
    rows = [{'moment_id': 'M' + str(i), 'ideal_start': i*50, 'ideal_end': i*50+45,
             'evidence_segment_ids': ['S' + str(i)], 'topic_id': 'T' + str(i % 4),
             'default_shortlist_eligible': i < 6,
             'editorial_score_final': .8 if i < 6 else .15,
             'core_moment': {'text': 'Tema ' + str(i) + ' com desfecho isolado.'}}
            for i in range(36)]
    segments = [{'segment_id': 'S'+str(i), 'start': i*50, 'end': i*50+45,
                 'speaker': 'A', 'text': 'Tema ' + str(i) + ' com desfecho isolado.'}
                for i in range(36)]
    result = evaluate(rows, segments, [], [], True)
    assert result['input_candidate_count'] == 36
    assert len(result['shortlist_ids']) == 6
    assert result['selection']['fixed_quota'] is False
