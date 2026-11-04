"""Source-contract canaries: no models, media, human accuracy or approvals."""
from copy import deepcopy

import pytest

from ldporto import narrative_handoff as narrative


def narrative_fixture():
    segments = [
        {'segment_id': 'S0', 'start': 0, 'end': 8, 'speaker': 'SP0',
         'text': 'A ponte antiga precisava de reparos.'},
        {'segment_id': 'S1', 'start': 8, 'end': 17, 'speaker': 'SP0',
         'text': 'Naquela manhã, a equipe encontrou uma falha na ponte.'},
        {'segment_id': 'S2', 'start': 17, 'end': 28, 'speaker': 'SP0',
         'text': 'Por isso, a equipe fechou a passagem para iniciar o conserto.'},
        {'segment_id': 'S3', 'start': 28, 'end': 38, 'speaker': 'SP0',
         'text': 'Depois do reparo, a ponte foi reaberta e todos atravessaram.'},
        {'segment_id': 'S4', 'start': 45, 'end': 55, 'speaker': 'SP0',
         'text': 'A tabela seguinte apresenta o número de viagens por mês.'},
    ]
    analysis = {
        'metadata': {'duration': 60, 'sha256': 'a' * 64,
                     'source': {'type': 'local', 'id': 'SYNTHETIC_ONLY'},
                     'analyzer_version': 'synthetic-test'},
        'run_manifest': {'run_id': 'SYNTHETIC_RUN'},
        'transcript_segments': segments,
        'story_arcs': [{
            'story_arc_id': 'ARC0', 'kind': 'partial_story',
            'start': 0, 'end': 38, 'evidence_segment_ids': ['S0', 'S1', 'S2', 'S3'],
            'setup': {'segment_ids': ['S0'], 'text': segments[0]['text'],
                      'start': 0, 'end': 8},
            'development': {'segment_ids': ['S1', 'S2'],
                            'text': ' '.join(s['text'] for s in segments[1:3]),
                            'start': 8, 'end': 28},
            'payoff': None, 'climax': None,
            'ending': {'segment_ids': ['S3'], 'text': segments[3]['text'],
                       'start': 28, 'end': 38},
            'narrative_supported': False,
            'support_diagnostics': {'ordered_setup_development_payoff': False,
                                    'missing_support_reasons': ['no_payoff']},
        }],
        'topics': [{'topic_id': 'T0', 'start': 0, 'end': 38,
                    'topic': 'Reparo de uma ponte',
                    'evidence_segment_ids': ['S0', 'S1', 'S2', 'S3']}],
        'program_sections': [], 'questions_answers': [], 'entities': [],
        'analysis_quality': {'active_speaker_coverage': None},
    }
    candidates = [{
        'candidate_id': 'C0', 'start': 8, 'end': 28,
        'segment_ids': ['S1', 'S2'],
        'transcript_literal': ' '.join(s['text'] for s in segments[1:3]),
        'default_shortlist_eligible': False, 'publication_ready': False,
        'commercial_classification': {'eligibility': 'review'},
    }]
    return analysis, candidates


def build_fixture():
    analysis, candidates = narrative_fixture()
    return analysis, candidates, narrative.build_narrative_handoff(analysis, candidates)


def artifact(bundle, kind):
    return bundle['artifacts'][narrative.ARTIFACTS[kind]]


def validate(bundle, analysis, candidates):
    return narrative.validate_narrative_handoff(
        bundle, analysis['transcript_segments'], candidates, analysis['metadata'])


def assert_invalid(bundle, analysis, candidates):
    result = validate(bundle, analysis, candidates)
    assert result['status'] == 'failed', result
    assert result['errors'], result


def test_builder_is_deterministic_and_does_not_mutate_canonical_inputs():
    analysis, candidates = narrative_fixture()
    original = deepcopy((analysis, candidates))
    first = narrative.build_narrative_handoff(analysis, candidates)
    second = narrative.build_narrative_handoff(analysis, candidates)
    assert first == second
    assert (analysis, candidates) == original
    assert first['handoff']['contract'] == 'ldporto.narrative_handoff'
    assert first['handoff']['schema_version'] == '1.0'
    assert set(first['handoff']['artifact_refs'].values()) <= set(first['artifacts'])
    assert validate(first, analysis, candidates)['status'] == 'valid'
    artifact(first, 'units')['units'][0]['source_intervals'][0]['start'] = 123
    assert (analysis, candidates) == original
    assert first != second


def test_units_preserve_literal_individual_source_intervals_and_candidate_gates():
    analysis, candidates, bundle = build_fixture()
    source = {s['segment_id']: s for s in analysis['transcript_segments']}
    units = artifact(bundle, 'units')['units']
    assert units
    assert any('C0' in unit['candidate_ids'] for unit in units)
    for unit in units:
        assert unit['literal_text'] == ' '.join(source[s]['text'] for s in unit['source_segment_ids'])
        assert unit['source_intervals'] == [
            {k: source[s][k] for k in ('segment_id', 'start', 'end')}
            for s in unit['source_segment_ids']]
        assert unit['requires_curator_review'] is True
        assert not unit['human_review_completed'] and not unit['preview_approved']
        assert not unit['publication_ready'] and unit['active_person'] is None
        assert unit['visual_mode'] == 'SOURCE_PRESERVE'
        assert not unit['visual_identity_inferred']
    assert candidates[0]['default_shortlist_eligible'] is False
    assert artifact(bundle, 'quality')['official_shortlist_changed'] is False


def test_missing_video_and_active_speaker_do_not_prevent_source_bound_review():
    analysis, candidates, bundle = build_fixture()
    assert 'active_speaker' not in analysis and 'video_analysis' not in analysis
    assert 'width' not in analysis['metadata']
    assert artifact(bundle, 'units')['units']
    assert validate(bundle, analysis, candidates)['status'] == 'valid'
    readiness = bundle['handoff']['readiness']
    assert readiness['transcription']['ready']
    assert not readiness['visual']['ready'] and not readiness['speaker']['ready']
    assert not readiness['publication']['ready']


def test_empty_arcs_produce_legitimate_zero_units_without_forcing_a_story():
    analysis, candidates = narrative_fixture()
    analysis['story_arcs'] = []
    bundle = narrative.build_narrative_handoff(analysis, candidates)
    assert artifact(bundle, 'units')['units'] == []
    assert artifact(bundle, 'sequences')['sequences'] == []
    assert artifact(bundle, 'titles')['titles'] == []
    assert artifact(bundle, 'quality')['unit_count'] == 0
    assert bundle['handoff']['status'] == 'SECOND_CURATION_PARTIAL'
    assert not bundle['handoff']['publication_ready']
    assert validate(bundle, analysis, candidates)['status'] == 'valid'


def test_private_path_prefix_keeps_title_offsets_tied_to_sanitized_literal():
    analysis, candidates = narrative_fixture()
    private_prefix = 'C:\\Users\\Synthetic\\recording.mp4'
    analysis['transcript_segments'][0]['text'] = (
        private_prefix + ' A ponte antiga precisava de reparos.')
    original = deepcopy(analysis)
    bundle = narrative.build_narrative_handoff(analysis, candidates)
    assert analysis == original
    unit = next(u for u in artifact(bundle, 'units')['units']
                if u['source_segment_ids'] == ['S0'])
    title = next(t for t in artifact(bundle, 'titles')['titles']
                 if t['unit_id'] == unit['unit_id'])
    assert private_prefix not in unit['literal_text']
    assert '[PRIVATE_PATH]' in unit['literal_text']
    for variant in title['suggested_titles']:
        assert variant['title'] == unit['literal_text'][variant['start_char']:variant['end_char']]
        assert private_prefix not in variant['title']
    assert title['hook_text'] == unit['literal_text']
    assert validate(bundle, analysis, candidates)['status'] == 'valid'


def test_discussion_keeps_review_units_without_claiming_narrative_completion():
    analysis, candidates = narrative_fixture()
    arc = analysis['story_arcs'][0]
    arc.update(kind='discussion_segment', setup=None, development=None, payoff=None)
    bundle = narrative.build_narrative_handoff(analysis, candidates)
    sequences = artifact(bundle, 'sequences')['sequences']
    assert sequences
    assert all(not s['complete_supported'] and
               s['completeness'] == 'discussion_without_narrative' for s in sequences)
    assert artifact(bundle, 'quality')['complete_supported_sequence_count'] == 0
    assert validate(bundle, analysis, candidates)['status'] == 'valid'


def test_ordered_source_grounded_components_can_be_complete_without_human_approval():
    analysis, candidates = narrative_fixture()
    arc = analysis['story_arcs'][0]
    arc.update(kind='complete_story', narrative_supported=True,
               payoff={'segment_ids': ['S3'], 'start': 28, 'end': 38,
                       'text': analysis['transcript_segments'][3]['text']},
               support_diagnostics={'ordered_setup_development_payoff': True,
                                    'missing_support_reasons': []})
    bundle = narrative.build_narrative_handoff(analysis, candidates)
    sequences = artifact(bundle, 'sequences')['sequences']
    assert len(sequences) == 1 and sequences[0]['complete_supported']
    assert not sequences[0]['publication_ready'] and not sequences[0]['preview_approved']
    assert sequences[0]['requires_curator_review']
    assert artifact(bundle, 'quality')['complete_supported_sequence_count'] == 1
    assert validate(bundle, analysis, candidates)['status'] == 'valid'


def test_nonadjacent_source_ids_are_split_instead_of_implying_a_contiguous_cut():
    analysis, candidates = narrative_fixture()
    arc = analysis['story_arcs'][0]
    arc.update(kind='discussion_segment', setup=None, development=None, payoff=None,
               evidence_segment_ids=['S0', 'S3'])
    bundle = narrative.build_narrative_handoff(analysis, candidates)
    units = artifact(bundle, 'units')['units']
    assert [u['source_segment_ids'] for u in units] == [['S0'], ['S3']]
    sequence = artifact(bundle, 'sequences')['sequences'][0]
    assert sequence['source_intervals'] == [
        {'segment_id': 'S0', 'start': 0, 'end': 8},
        {'segment_id': 'S3', 'start': 28, 'end': 38}]
    assert sequence['assembly_disclosure_required']
    assert not sequence['complete_supported']
    assert validate(bundle, analysis, candidates)['status'] == 'valid'


@pytest.mark.parametrize('kind', ['source_id', 'candidate_id', 'context_id', 'literal',
                                  'span_start', 'span_end', 'span_bool'])
def test_validator_rejects_corrupted_source_unit_provenance(kind):
    analysis, candidates, bundle = build_fixture()
    unit = artifact(bundle, 'units')['units'][0]
    if kind == 'source_id':
        unit['source_segment_ids'][0] = 'ABSENT_SOURCE'
    elif kind == 'candidate_id':
        unit['candidate_ids'].append('ABSENT_CANDIDATE')
    elif kind == 'context_id':
        unit['required_context_unit_ids'].append('ABSENT_UNIT')
    elif kind == 'literal':
        unit['literal_text'] = 'A ponte caiu e deixou cem vítimas.'
    elif kind == 'span_start':
        unit['source_intervals'][0]['start'] += .25
    elif kind == 'span_end':
        unit['source_intervals'][0]['end'] += .25
    elif kind == 'span_bool':
        unit['source_intervals'][0]['start'] = False
    assert_invalid(bundle, analysis, candidates)


@pytest.mark.parametrize('field', ['source_id', 'target_id'])
def test_validator_rejects_dangling_graph_edges(field):
    analysis, candidates, bundle = build_fixture()
    edge = artifact(bundle, 'graph')['edges'][0]
    edge[field] = 'ABSENT_GRAPH_NODE'
    assert_invalid(bundle, analysis, candidates)


def test_validator_rejects_cutting_required_context_out_of_a_sequence():
    analysis, candidates, bundle = build_fixture()
    units = artifact(bundle, 'units')['units']
    sequence = artifact(bundle, 'sequences')['sequences'][0]
    prerequisite = next(u for u in units if u['unit_id'] in sequence['required_context_unit_ids'])
    assert any(prerequisite['unit_id'] in u['required_context_unit_ids'] for u in units)
    sequence['unit_ids'].remove(prerequisite['unit_id'])
    removed_segments = set(prerequisite['source_segment_ids'])
    sequence['source_intervals'] = [
        s for s in sequence['source_intervals'] if s['segment_id'] not in removed_segments]
    assert_invalid(bundle, analysis, candidates)


def test_validator_rejects_erasing_sequence_context_declaration():
    analysis, candidates, bundle = build_fixture()
    sequence = artifact(bundle, 'sequences')['sequences'][0]
    assert sequence['required_context_unit_ids']
    sequence['required_context_unit_ids'] = []
    assert_invalid(bundle, analysis, candidates)


def test_validator_rejects_rewriting_source_presentation_order():
    analysis, candidates, bundle = build_fixture()
    sequence = artifact(bundle, 'sequences')['sequences'][0]
    assert len(sequence['unit_ids']) > 1
    sequence['unit_ids'].reverse()
    assert_invalid(bundle, analysis, candidates)


@pytest.mark.parametrize('part', ['title', 'factual_claims', 'hook_text'])
def test_validator_rejects_untraceable_title_or_hook_claims(part):
    analysis, candidates, bundle = build_fixture()
    title = artifact(bundle, 'titles')['titles'][0]
    invented = 'A ponte caiu e deixou cem vítimas.'
    if part == 'hook_text':
        title['hook_text'] = invented
    else:
        title['suggested_titles'][0][part] = [invented] if part == 'factual_claims' else invented
    assert_invalid(bundle, analysis, candidates)


@pytest.mark.parametrize('target,field,value', [
    ('handoff', 'publication_ready', True),
    ('handoff', 'preview_approved', True),
    ('handoff', 'requires_curator_review', False),
    ('unit', 'publication_ready', True),
    ('unit', 'human_review_completed', True),
    ('unit', 'requires_curator_review', False),
    ('sequence', 'publication_ready', True),
    ('sequence', 'preview_approved', True),
    ('sequence', 'human_review_completed', True),
    ('sequence', 'complete_supported', True),
    ('title', 'publication_ready', True),
])
def test_validator_rejects_injected_approvals_and_unproven_completeness(target, field, value):
    analysis, candidates, bundle = build_fixture()
    record = {'handoff': bundle['handoff'],
              'unit': artifact(bundle, 'units')['units'][0],
              'sequence': artifact(bundle, 'sequences')['sequences'][0],
              'title': artifact(bundle, 'titles')['titles'][0]}[target]
    record[field] = value
    if target == 'sequence' and field == 'complete_supported':
        # Keep the aggregate consistent so it cannot conceal a missing proof check.
        artifact(bundle, 'quality')['complete_supported_sequence_count'] = 1
    assert_invalid(bundle, analysis, candidates)


def test_validator_rejects_spoofed_source_identity():
    analysis, candidates, bundle = build_fixture()
    bundle['handoff']['source_sha256'] = 'b' * 64
    assert_invalid(bundle, analysis, candidates)


def test_validator_rejects_context_dependency_cycles():
    analysis, candidates, bundle = build_fixture()
    units = artifact(bundle, 'units')['units']
    assert len(units) > 1
    units[0]['required_context_unit_ids'] = [units[-1]['unit_id']]
    assert_invalid(bundle, analysis, candidates)
