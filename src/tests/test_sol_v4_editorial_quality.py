"""Synthetic editorial triage cases; no claim of human quality or media inference."""
from copy import deepcopy

import pytest

from ldporto.editorial_review import editorial_potential, boundary_review_proposals, review_milestones
from ldporto.integrity_contracts import human_review_queue
from test_sol_v4_post_editorial import review_candidate


def candidate(text, cid='STORY', score=.3, start=10):
    return {**review_candidate(cid, start, score), 'transcript_literal': text}


def test_cta_no_longer_precedes_story_despite_higher_historical_score():
    cta = candidate('Se inscreve, comenta e compartilha!', 'CTA', .99, 100)
    story = candidate('Uma vez tentei rádio. Recusaram, mas depois fiz meu podcast.', score=.4)
    rows = [cta, story]
    before = deepcopy(rows)
    assert human_review_queue(rows, schema_version='1.1')['candidate_ids'] == ['CTA', 'STORY']
    queue = human_review_queue(rows)
    assert queue['schema_version'] == '1.2' and queue['candidate_ids'] == ['STORY', 'CTA']
    assert rows == before and queue['entries'][1]['editorial_score_final'] == .99
    assert queue['entries'][0]['editorial_potential']['story_supported'] is None
    assert not queue['entries'][0]['official_shortlist_selected']
    assert not queue['entries'][0]['review_milestones']['human_review_completed']


@pytest.mark.parametrize('text,kind', [
    ('Se inscreve e comenta.', 'CTA_HOUSEKEEPING'),
    ('Se inscreve. Obrigado e até o próximo episódio.', 'CTA_HOUSEKEEPING'),
    ('Uma vez ele pediu: se inscreve, comenta.', 'CONTENT_REVIEW'),
    ('Ela falava: se inscreve, comenta.', 'UNRESOLVED'),
    ('Não se inscreve. Nunca comenta.', 'UNRESOLVED'),
    ('Tem uma história. Se inscreve e comenta.', 'MIXED_CTA_CONTENT'),
    ('Texto rotineiro.', 'UNRESOLVED'),
])
def test_contextual_cta_negatives_and_mixed_content(text, kind):
    row = candidate(text)
    row['categories'] = ['storytelling', 'humor']
    proof = editorial_potential(row)
    assert proof['classification'] == kind
    assert proof['humor_confirmed'] is None and proof['human_quality_verified'] is None
    for cue in proof['literal_cues']:
        assert text[cue['start_char']:cue['end_char']] == cue['literal']


def test_deduplication_preserves_alternative_ids_without_approving_either():
    a = candidate('Tem uma história.', 'A')
    b = {**a, 'candidate_id': 'B', 'alternate_of': 'A', 'rank': 2}
    q = human_review_queue([a, b])
    assert q['candidate_ids'] == ['A'] and q['entries'][0]['alternative_ids'] == ['B']
    assert not q['publication_ready']


def test_milestones_keep_interest_separate_from_eligibility_and_approval():
    row = candidate('Tem uma história.')
    row.update(eligible_for_human_review=False, human_approved=True, preview_approved=True)
    states = review_milestones(row)
    assert states['interest_state'] == 'INTERESTING_CANDIDATE'
    assert states['eligibility_state'] == 'NOT_ELIGIBLE_FOR_REVIEW'
    assert states['human_review_state'] == 'HUMAN_REVIEW_PENDING'
    assert states['human_review_completed'] is False and states['preview_approved'] is False
    assert states['publish_ready'] is False and states['speaker_identity_verified'] is None


def test_queue_cue_offsets_remain_reproducible_after_existing_privacy_redaction():
    from ldporto.export_privacy import sanitize_export
    row = candidate('Uma vez abri C:\\Users\\private\\notes.txt e ouvi: se inscreve, comenta.')
    assert sanitize_export(human_review_queue([row])) == human_review_queue(sanitize_export([row]))


def boundary_fixture():
    rows = [{'segment_id': 'S1', 'start': 8, 'end': 10, 'text': 'O que aconteceu?'},
            {'segment_id': 'S2', 'start': 10, 'end': 20, 'text': 'Então tentei rádio...'},
            {'segment_id': 'S3', 'start': 20, 'end': 24, 'text': 'Recusaram.'}]
    c = {**candidate(rows[1]['text']), 'end': 20, 'segment_ids': ['S2'],
         'clean_opening': False, 'clean_ending': False}
    return c, rows, [{'topic_id': 'T1', 'evidence_segment_ids': ['S1', 'S2', 'S3']}]


def test_boundary_proposals_bind_canonical_ids_but_never_assert_completion():
    c, rows, topics = boundary_fixture()
    before = deepcopy((c, rows, topics))
    proposals = boundary_review_proposals(c, rows, topics)
    assert {r['kind'] for r in proposals} == {
        'canonical_segment_edges', 'inspect_preceding_context', 'inspect_following_continuation'}
    extension = next(r for r in proposals if r['kind'] == 'inspect_following_continuation')
    assert extension['end'] == 24 and extension['last_literal'] == 'Recusaram.'
    assert extension['semantic_completion_verified'] is None and extension['applied'] is False
    assert extension['duration_contract']['target_min_seconds'] == 30  # Not silently satisfied.
    assert (c, rows, topics) == before


@pytest.mark.parametrize('change', ['other_topic', 'unknown_topic', 'gap', 'overlap', 'hard_max'])
def test_contradictory_discontinuous_or_overlong_context_is_not_joined(change):
    c, rows, topics = boundary_fixture()
    if change == 'other_topic':
        topics[0]['evidence_segment_ids'].remove('S3')
        topics.append({'topic_id': 'UNRELATED', 'evidence_segment_ids': ['S3']})
    elif change == 'unknown_topic':
        topics = []
    elif change == 'gap':
        rows[-1].update(start=27, end=30)
    elif change == 'overlap':
        rows[-1]['start'] = 19
    else:
        c['duration_contract'] = {**c['duration_contract'], 'hard_max_seconds': 10}
    assert 'inspect_following_continuation' not in {
        r['kind'] for r in boundary_review_proposals(c, rows, topics)}


@pytest.mark.parametrize('change', ['duplicate_id', 'missing_id', 'detached_interval', 'below_hard_min'])
def test_invalid_source_binding_produces_no_boundary_proposal(change):
    c, rows, topics = boundary_fixture()
    if change == 'duplicate_id':
        rows.append(dict(rows[0]))
    elif change == 'missing_id':
        c['segment_ids'] = ['ABSENT']
    elif change == 'detached_interval':
        c.update(start=100, end=140)
    else:
        c['duration_contract'] = {**c['duration_contract'], 'hard_min_seconds': 50}
    assert boundary_review_proposals(c, rows, topics) == []
