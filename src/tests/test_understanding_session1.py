"""Session 1 regression: real replay proof IDs, malformed arcs, no invented evidence."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from ldporto.config import DEFAULTS
from ldporto.editorial import _complete_story, assess_duration, rank_candidate
from ldporto.understanding import _validate_story_arcs_contract

FIXTURES = Path(__file__).parent / 'fixtures'


def _real_case(name):
    payload = json.loads((FIXTURES / ('s1_' + name + '_proof.json')).read_text('utf-8'))
    assert payload['source_segments'] > 0
    return payload['cases'][0]


def _candidate_from_source(source):
    return {**deepcopy(source), 'core_moment': {'text': 'Trecho de entrevista.'},
            'text': 'Trecho de entrevista.', 'evidence_segment_ids': source['boundary_segment_ids'],
            'information_score': .8}


def test_clovis_real_duration_exception_survives_ranking_without_type_error():
    """Clovis Oct/2026 replay produced a genuine 122.2s complete story.

    It crashed in the old rank_candidate because the real proof components
    were ID lists and _complete_story called .get() on each list.
    """
    source = _real_case('clovis')
    assert source['moment_id'] == 'MOMENT_00043_0007'
    assert source['duration_exception'] is True
    assert source['ideal_end'] - source['ideal_start'] > 90
    result = rank_candidate(_candidate_from_source(source), deepcopy(DEFAULTS['understanding']))
    assert result['duration_exception'] is True
    assert result['duration_exception_evidence'] == source['duration_exception_evidence']
    assert result['duration_exception_proof_rejected'] is False


def test_emerson_real_candidate_has_no_fabricated_exception():
    source = _real_case('emerson')
    result = rank_candidate(_candidate_from_source(source), deepcopy(DEFAULTS['understanding']))
    assert result['moment_id'] == source['moment_id']
    assert not result['duration_exception']
    assert result['duration_exception_evidence'] is None


@pytest.mark.parametrize('broken', [
    {'setup': ['S0'], 'development': ['S1'], 'payoff': ['NEVER_OBSERVED']},
    {'setup': ['S2'], 'development': ['S1'], 'payoff': ['S0']},
    {'setup': ['S0'], 'development': [], 'payoff': ['S2']},
    {'setup': ['S0'], 'development': ['S1'], 'payoff': [{'segment_ids': ['S2']}]},
    {'setup': ['S0'], 'development': ['S1'], 'payoff': 'S2'},
    {'setup': ['S0'], 'development': ['S0'], 'payoff': ['S2']},
])
def test_invalid_story_proofs_cannot_become_duration_exceptions(broken):
    row = {'ideal_start': 0, 'ideal_end': 120, 'duration_exception': True,
           'duration_exception_evidence': broken,
           'boundary_segment_ids': ['S0', 'S1', 'S2'],
           'text': 'Uma história sem prova completa.'}
    result = rank_candidate(row, deepcopy(DEFAULTS['understanding']))
    assert result['duration_exception'] is False
    assert result['duration_exception_evidence'] is None
    assert result['duration_exception_proof_rejected'] is True
    assert result['duration_default_eligible'] is False


def test_proof_from_assess_duration_is_compatible_with_rank_candidate():
    story = {'kind': 'complete_story', 'completeness': 'supported_setup_development_payoff',
             'setup': {'segment_ids': ['S0']}, 'development': {'segment_ids': ['S1']},
             'payoff': {'segment_ids': ['S2']}}
    ids = ['S0', 'S1', 'S2']
    duration = assess_duration(0, 120, deepcopy(DEFAULTS['understanding']), story, ids)
    assert duration['duration_exception']
    ranked = rank_candidate({'ideal_start': 0, 'ideal_end': 120,
                             'boundary_segment_ids': ids, 'text': 'História testemunhada.',
                             **duration}, deepcopy(DEFAULTS['understanding']))
    assert ranked['duration_exception']
    assert ranked['duration_exception_evidence'] == duration['duration_exception_evidence']


def test_malformed_story_objects_return_false_without_exception():
    for story in ([], 'wrong', {'kind': 'complete_story', 'setup': [{}]},
                  {'kind': 'unresolved'}, None):
        assert _complete_story(story, ['S0', 'S1', 'S2']) is False


def test_story_arc_contract_uses_only_source_ids_and_downgrades_bad_arc():
    segments = [{'segment_id': sid} for sid in ('S0', 'S1', 'S2')]
    valid = {'kind': 'complete_story', 'evidence_segment_ids': ['S0', 'S1', 'S2'],
             'setup': ['S0'], 'development': ['S1'], 'payoff': ['S2']}
    bad = {**valid, 'payoff': ['MISSING'], 'standalone_score': 1.0}
    rows, events = _validate_story_arcs_contract([valid, bad], segments)
    assert rows[0]['kind'] == 'complete_story'
    assert rows[0]['setup'] == {'segment_ids': ['S0']}
    assert rows[1]['kind'] == 'partial_story'
    assert rows[1]['payoff'] is None
    assert rows[1]['standalone_score'] is None
    assert rows[1]['needs_review'] is True
    assert any(e['path'] == 'story_arcs[1].payoff' for e in events)
    assert any(e['action'] == 'downgraded_to_partial_story' for e in events)
