"""Synthetic metadata contracts; never semantic/audio/visual human approval."""
from copy import deepcopy

import jsonschema
import pytest

from ldporto.core import digest
from ldporto.story_visual_handoff import (ARTIFACTS, SERIES_REF,
    _check_copy, build_story_visual_handoff, title_response_schema, validate_story_visual_handoff)


def fixture():
    rows = [
        {'segment_id': 'S0', 'start': 0, 'end': 4, 'speaker': 'ACOUSTIC_A',
         'text': 'A ponte fechou após uma falha.', 'needs_review': True,
         'uncertain_word_ids': ['W_S0_1']},
        {'segment_id': 'S1', 'start': 4, 'end': 8, 'speaker': 'ACOUSTIC_A',
         'text': 'A equipe reparou a ponte.', 'needs_review': False},
        {'segment_id': 'S2', 'start': 20, 'end': 24, 'speaker': None,
         'text': 'A ponte abriu depois do reparo.', 'needs_review': False},
    ]
    words = []
    for row in rows:
        tokens = row['text'].split()
        for i, token in enumerate(tokens):
            words.append({'word_id': f'W_{row["segment_id"]}_{i}', 'word': token,
                'segment_id': row['segment_id'], 'speaker': row['speaker'],
                'start': row['start'] + i * (row['end']-row['start']) / len(tokens),
                'end': row['end'] if i == len(tokens)-1 else row['start'] + (i+1)*(row['end']-row['start'])/len(tokens),
                'needs_review': i == 1 and row['segment_id'] == 'S0', 'confidence': None})
    legacy = {'source/metadata.json': {'sha256': 'a'*64, 'duration': 30,
        'source': {'id': 'SYNTHETIC_FIXTURE'}}, 'transcript/relevant_segments.jsonl': rows,
        'transcript/relevant_words.jsonl': words, 'editorial/story_units.json': {'units': [
            {'unit_id': 'U0', 'source_segment_ids': ['S0', 'S1']},
            {'unit_id': 'U1', 'source_segment_ids': ['S2']}]},
        'editorial/candidate_catalog.json': {'candidates': []},
        'editorial/default_shortlist.json': {'candidate_ids': []}}
    stories = []
    for index, ids in enumerate([['S0', 'S1'], ['S2']], 1):
        selected = [r for r in rows if r['segment_id'] in ids]
        stories.append({'story_id': f'STORY_{index}', 'series_id': 'SERIES_A',
            'sequence_position': index, 'sequence_total': 2,
            'source_segment_ids': ids, 'source_unit_ids': [f'U{index-1}'],
            'source_arc_ids': [f'ARC{index-1}'],
            'source_intervals': [{k: r[k] for k in ('segment_id', 'start', 'end')} for r in selected],
            'narrative_role': 'HOOK' if index == 1 else 'RESOLUTION',
            'summary': selected[0]['text'], 'context_required': [],
            'previous_story_dependency': None if index == 1 else 'STORY_1',
            'next_story_relationship': {'story_id': 'STORY_2', 'relationship': 'CONTINUES'} if index == 1 else None,
            'missing_information': [], 'estimated_source_duration': sum(r['end']-r['start'] for r in selected),
            'new_information': selected[-1]['text'], 'review_required': True, 'publication_ready': False})
    semantic = {SERIES_REF: {'schema_version': '1.0', 'series': [
        {'series_id': 'SERIES_A', 'sequence_id': 'SERIES_A', 'stories': stories}]}}
    return legacy, semantic


def valid_payload(context):
    data = context['data']; rows = data['segments']; first = rows[0]
    quote = {'segment_id': first['segment_id'], 'quote': first['text']}
    if first['segment_id'] == 'S0':
        texts = ['A falha que fechou a ponte', 'Por que a ponte fechou?', 'A ponte fechou após uma falha']
    else:
        texts = ['A ponte abriu depois do reparo', 'Como a ponte abriu depois do reparo?',
                 'Depois do reparo: a ponte abriu']
    def title(text, angle):
        return {'text': text, 'angle': angle, 'factual_claims': [text],
                'supporting_quotes': [quote], 'condensed_text': None}
    return {'primary_title': title(texts[0], 'FACTUAL'),
        'alternative_titles': [title(texts[1], 'CURIOSITY'), title(texts[2], 'EXPLANATORY')],
        'opening_hook_text': texts[0], 'hook_supporting_quotes': [quote],
        'social_caption': first['text'], 'caption_supporting_quotes': [quote],
        'engagement_question': None, 'cta': None,
        'keywords': [{'text': 'ponte', 'segment_id': first['segment_id'], 'reason': 'KEY_FACT'}],
        'abstention_reason': None}


def infer(task, context, schema):
    assert task.startswith('titles:')
    payload = valid_payload(context)
    jsonschema.Draft202012Validator(schema).validate(payload)
    return payload, {'model': 'SYNTHETIC_FIXTURE_ONLY', 'call_id': task,
                     'response_sha256': digest(payload), 'model_digest': 'b'*64}


def built():
    legacy, semantic = fixture()
    return legacy, semantic, build_story_visual_handoff(legacy, semantic, infer)


def stories(artifacts):
    return artifacts[ARTIFACTS['visual']]['series'][0]['stories']


def assert_invalid(artifacts, legacy, semantic):
    result = validate_story_visual_handoff(artifacts, legacy, semantic)
    assert result['status'] == 'invalid', result
    assert result['errors']


def test_complete_metadata_is_deterministic_isolated_and_consumer_valid_without_media():
    legacy, semantic = fixture(); original = deepcopy((legacy, semantic))
    first = build_story_visual_handoff(legacy, semantic, infer)
    second = build_story_visual_handoff(legacy, semantic, infer)
    assert first == second and (legacy, semantic) == original
    assert validate_story_visual_handoff(first, legacy, semantic)['status'] == 'valid'
    assert len(stories(first)) == 2
    for story in stories(first):
        assert story['metadata_status'] == 'COMPLETE_FOR_REVIEW'
        assert story['primary_title'] and len(story['alternative_titles']) == 2
        assert story['layout_constraints']['subject_regions_status'] == 'UNKNOWN'
        assert story['speech_subtitles']['alignment_granularity'] == 'word'
        assert story['review_required'] and not story['publication_ready']
    stories(first)[0]['source_intervals'][0]['start'] = 100
    assert (legacy, semantic) == original and first != second


def test_word_level_metadata_preserves_actual_timestamps_uncertainty_and_known_speaker_label():
    legacy, semantic, artifacts = built()
    story = stories(artifacts)[0]
    aligned = story['speech_subtitles']
    assert 'source_asr_review_pending' in story['blocking_issues']
    for word in aligned['source_words']:
        source = next(w for w in legacy['transcript/relevant_words.jsonl'] if w['word_id'] == word['word_id'])
        assert (word['word'], word['start'], word['end']) == (source['word'], source['start'], source['end'])
        assert word['alignment_source'] == 'persisted_asr_word_timestamps_not_independently_verified'
        assert word['relative_start'] is None and word['relative_end'] is None
        assert word['speaker'] == 'ACOUSTIC_A'
    assert stories(artifacts)[1]['speech_subtitles']['transcript_segments'][0]['speaker'] is None
    highlight = story['highlight_candidates'][0]
    assert highlight['word_ids'] == ['W_S0_1'] and highlight['precise_word_timing_available']
    assert not aligned['audio_verified'] and aligned['requires_alignment_review']


@pytest.mark.parametrize('problem', ['absent', 'outside', 'boolean', 'different_text', 'overlap', 'duplicate'])
def test_missing_or_unreliable_word_alignment_falls_back_to_source_segment(problem):
    legacy, semantic = fixture()
    words = legacy['transcript/relevant_words.jsonl']
    if problem == 'absent':
        legacy['transcript/relevant_words.jsonl'] = []
    elif problem == 'outside': words[0]['end'] = 80
    elif problem == 'boolean': words[0]['start'] = False
    elif problem == 'different_text': words[0]['word'] = 'Inventado'
    elif problem == 'overlap': words[1]['start'] = 0
    elif problem == 'duplicate': words[1]['word_id'] = words[0]['word_id']
    artifacts = build_story_visual_handoff(legacy, semantic, infer)
    alignment = stories(artifacts)[0]['speech_subtitles']
    assert alignment['alignment_granularity'] in {'segment', 'mixed'}
    assert not any(w['segment_id'] == 'S0' for w in alignment['source_words'])
    highlight = stories(artifacts)[0]['highlight_candidates'][0]
    assert not highlight['word_ids'] and highlight['alignment_granularity'] == 'segment'
    assert (highlight['start'], highlight['end']) == (0, 4)
    assert validate_story_visual_handoff(artifacts, legacy, semantic)['status'] == 'valid'


def test_discontinuous_intervals_keep_individual_source_mapping_and_no_fictional_relative_time():
    legacy, semantic = fixture()
    series = semantic[SERIES_REF]['series'][0]
    series['stories'] = [series['stories'][0]]
    story = series['stories'][0]
    story.update(source_segment_ids=['S0', 'S2'], source_unit_ids=['U0', 'U1'], sequence_total=1,
        next_story_relationship=None, source_intervals=[{'segment_id': 'S0', 'start': 0, 'end': 4},
            {'segment_id': 'S2', 'start': 20, 'end': 24}])
    artifacts = build_story_visual_handoff(legacy, semantic, infer)
    alignment = stories(artifacts)[0]['speech_subtitles']
    assert len(alignment['edit_mapping']) == 2
    assert alignment['edit_mapping'][1]['start'] == 20
    assert all(m['relative_start'] is None and m['relative_end'] is None and
               m['mapping_status'] == 'CURATOR_EDIT_REQUIRED' for m in alignment['edit_mapping'])
    assert validate_story_visual_handoff(artifacts, legacy, semantic)['status'] == 'valid'


@pytest.mark.parametrize('problem', ['number', 'entity', 'fact', 'quote', 'future', 'keyword', 'duplicate', 'truncated'])
def test_unfounded_model_copy_abstains_without_clearing_source_metadata(problem):
    legacy, semantic = fixture()
    def bad(task, context, schema):
        payload, model = infer(task, context, schema)
        if problem == 'number': payload['primary_title']['text'] = '999 falhas na ponte'
        elif problem == 'entity': payload['primary_title']['text'] = 'João fechou a ponte'
        elif problem == 'fact': payload['primary_title']['text'] = 'A ponte caiu'
        elif problem == 'quote': payload['primary_title']['supporting_quotes'][0]['quote'] = 'Citação inventada.'
        elif problem == 'future': payload['primary_title']['supporting_quotes'][0]['segment_id'] = 'ABSENT_OR_FUTURE'
        elif problem == 'keyword': payload['keywords'][0]['text'] = 'avião'
        elif problem == 'duplicate': payload['alternative_titles'][0] = deepcopy(payload['primary_title'])
        elif problem == 'truncated': payload['primary_title']['text'] = 'A ponte e'
        return payload, model
    artifacts = build_story_visual_handoff(legacy, semantic, bad)
    for story in stories(artifacts):
        assert story['primary_title'] is None and story['alternative_titles'] == []
        assert story['metadata_status'] == 'PARTIAL'
        assert story['speech_subtitles']['transcript_segments']
        assert not story['publication_ready']
    assert validate_story_visual_handoff(artifacts, legacy, semantic)['status'] == 'valid'


def test_model_timeout_is_explicit_partial_metadata_without_a_second_client():
    legacy, semantic = fixture()
    def unavailable(*args): raise TimeoutError('synthetic timeout')
    artifacts = build_story_visual_handoff(legacy, semantic, unavailable)
    assert all(s['metadata_status'] == 'PARTIAL' for s in stories(artifacts))
    assert all(p['abstention_reason'] for p in artifacts[ARTIFACTS['titles']]['pieces'])
    assert validate_story_visual_handoff(artifacts, legacy, semantic)['status'] == 'valid'


def test_zero_series_is_legitimate_and_never_calls_the_model():
    legacy, semantic = fixture(); semantic[SERIES_REF]['series'] = []
    def forbidden(*args): raise AssertionError('no piece should require inference')
    artifacts = build_story_visual_handoff(legacy, semantic, forbidden)
    assert artifacts[ARTIFACTS['visual']]['series'] == []
    assert artifacts[ARTIFACTS['completeness']]['story_count'] == 0
    assert validate_story_visual_handoff(artifacts, legacy, semantic)['status'] == 'valid'


@pytest.mark.parametrize('mutation', ['title_number', 'source_id', 'word_time', 'mapping', 'part',
    'false_region', 'crop', 'collision', 'publication', 'audio_verified', 'render', 'cover', 'dependency', 'schema'])
def test_consumer_validator_blocks_cross_artifact_or_visual_contract_forgery(mutation):
    legacy, semantic, artifacts = built(); story = stories(artifacts)[0]
    if mutation == 'title_number':
        story['primary_title']['text'] = '999 falhas na ponte'
        artifacts[ARTIFACTS['titles']]['pieces'][0]['primary_title']['text'] = '999 falhas na ponte'
    elif mutation == 'source_id': story['source_segment_ids'][0] = 'ABSENT'
    elif mutation == 'word_time': story['speech_subtitles']['source_words'][0]['end'] = 3.9
    elif mutation == 'mapping': story['speech_subtitles']['edit_mapping'][0]['relative_start'] = 0
    elif mutation == 'part': story['sequence_total'] = 99
    elif mutation == 'false_region': story['layout_constraints'].update(subject_regions_status='KNOWN', coordinates=[.1, .2])
    elif mutation == 'crop': story['layout_constraints']['crop_zoom_authorized'] = True
    elif mutation == 'collision': story['layout_constraints']['layout_collision_check_required'] = False
    elif mutation == 'publication': story['publication_ready'] = True
    elif mutation == 'audio_verified': story['speech_subtitles']['audio_verified'] = True
    elif mutation == 'render': artifacts[ARTIFACTS['visual']]['rendered_assets']['mp4'] = True
    elif mutation == 'cover': story['cover_concept']['image_generated'] = True
    elif mutation == 'dependency': story['previous_story_dependency'] = 'ABSENT_STORY'
    elif mutation == 'schema': artifacts[ARTIFACTS['schema']]['$schema'] = 'http[PRIVATE_PATH]'
    assert_invalid(artifacts, legacy, semantic)


def test_changing_one_title_keeps_all_alignment_and_visual_source_data_unchanged():
    legacy, semantic = fixture()
    first = build_story_visual_handoff(legacy, semantic, infer)
    def another(task, context, schema):
        payload, provenance = infer(task, context, schema)
        if task == 'titles:STORY_1':
            payload['primary_title']['text'] = 'Uma falha fechou a ponte'
            payload['primary_title']['factual_claims'] = ['Uma falha fechou a ponte']
        return payload, provenance
    second = build_story_visual_handoff(legacy, semantic, another)
    for before, after in zip(stories(first), stories(second)):
        assert before['speech_subtitles'] == after['speech_subtitles']
        assert before['source_intervals'] == after['source_intervals']
        assert before['layout_constraints'] == after['layout_constraints']
    assert stories(first)[1] == stories(second)[1]
    assert validate_story_visual_handoff(second, legacy, semantic)['status'] == 'valid'


def test_response_and_visual_schemas_are_valid_with_metadata_present():
    legacy, semantic, artifacts = built()
    jsonschema.Draft202012Validator.check_schema(title_response_schema())
    schema = artifacts[ARTIFACTS['schema']]
    assert schema['$schema'] == 'https://json-schema.org/draft/2020-12/schema'
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(artifacts[ARTIFACTS['visual']])


def test_negative_adjunct_does_not_negate_supported_positive_facts():
    text = ('Para não complicar muito, ao redor do mundo existem milhares de antenas '
            'que emitem sinais de rádio em frequências específicas, tá?')
    rows = {'S128': {'text': text}}
    _check_copy('Antenas e frequências de rádio', [{'segment_id': 'S128', 'quote': text}], {'S128'}, rows)


@pytest.mark.parametrize('source,claim', [
    ('O piloto não sintonizou a antena.', 'O piloto sintonizou a antena.'),
    ('O piloto sintonizou a antena.', 'O piloto não sintonizou a antena.'),
    ('A antena poderia ter evitado o acidente.', 'A antena evitou o acidente.'),
])
def test_factual_negation_and_counterfactual_guards_remain_conservative(source, claim):
    with pytest.raises(ValueError):
        _check_copy(claim, [{'segment_id': 'S', 'quote': source}], {'S'}, {'S': {'text': source}})


def test_neutral_engagement_is_not_misclassified_as_an_unsupported_factual_claim():
    legacy, semantic = fixture()
    def with_cta(task, context, schema):
        payload, provenance = infer(task, context, schema)
        payload['engagement_question'] = 'Qual a sua opinião?'
        payload['cta'] = 'Comente sua opinião.'
        return payload, provenance
    artifacts = build_story_visual_handoff(legacy, semantic, with_cta)
    assert all(s['suggested_cta'] == 'Comente sua opinião.' for s in stories(artifacts))
    assert validate_story_visual_handoff(artifacts, legacy, semantic)['status'] == 'valid'


def test_last_story_cannot_promise_a_nonexistent_next_part():
    legacy, semantic = fixture()
    def with_next(task, context, schema):
        payload, provenance = infer(task, context, schema)
        payload['cta'] = 'Veja a próxima parte.'
        return payload, provenance
    artifacts = build_story_visual_handoff(legacy, semantic, with_next)
    assert stories(artifacts)[0]['primary_title'] is not None
    assert stories(artifacts)[1]['primary_title'] is None
    assert validate_story_visual_handoff(artifacts, legacy, semantic)['status'] == 'valid'


def test_explicit_abstention_cannot_smuggle_unvalidated_highlights_or_caption():
    legacy, semantic = fixture()
    def abstain(task, context, schema):
        payload, model = infer(task, context, schema)
        payload.update(primary_title=None, abstention_reason='Evidence insufficient',
                       social_caption='999 vítimas inventadas.')
        payload['keywords'][0]['segment_id'] = 'ABSENT'
        return payload, model
    artifacts = build_story_visual_handoff(legacy, semantic, abstain)
    for story in stories(artifacts):
        assert story['primary_title'] is None and story['social_caption']['text'] is None
        assert story['highlight_candidates'] == []
    assert validate_story_visual_handoff(artifacts, legacy, semantic)['status'] == 'valid'


def test_relevant_reel_titles_follow_only_the_unchanged_canonical_shortlist():
    legacy, semantic = fixture()
    legacy['editorial/candidate_catalog.json']['candidates'] = [{
        'candidate_id': 'REEL_A', 'segment_ids': ['S0', 'S1'], 'start': 0, 'end': 8,
        'default_shortlist_eligible': True, 'publication_ready': False}]
    legacy['editorial/default_shortlist.json']['candidate_ids'] = ['REEL_A']
    original = deepcopy(legacy);calls = []
    def recording(task, context, schema):
        calls.append(task)
        return infer(task, context, schema)
    artifacts = build_story_visual_handoff(legacy, semantic, recording)
    reels = [p for p in artifacts[ARTIFACTS['titles']]['pieces'] if p['piece_type'] == 'REEL']
    assert len(reels) == 1 and reels[0]['candidate_id'] == 'REEL_A'
    assert reels[0]['primary_title'] and len(reels[0]['alternative_titles']) == 2
    assert 'titles:reel:REEL_A' in calls and legacy == original
    assert validate_story_visual_handoff(artifacts, legacy, semantic)['status'] == 'valid'


@pytest.mark.parametrize('target', ['cover_time', 'provenance', 'payload', 'piece_approval', 'report_approval',
    'weakened_schema', 'series_total', 'title_series', 'metrics'])
def test_validator_rejects_nested_projection_provenance_and_permission_forgery(target):
    legacy, semantic, artifacts = built();story = stories(artifacts)[0]
    if target == 'cover_time': story['cover_concept']['suggested_source_frame_interval']['end'] = 29
    elif target == 'provenance': story['provenance']['source_context_sha256'] = '0'*64
    elif target == 'payload': artifacts[ARTIFACTS['titles']]['pieces'][0]['validated_payload']['social_caption'] = 'Alterado.'
    elif target == 'piece_approval': artifacts[ARTIFACTS['titles']]['pieces'][0]['publication_ready'] = True
    elif target == 'report_approval': artifacts[ARTIFACTS['completeness']]['publication_ready'] = True
    elif target == 'weakened_schema': artifacts[ARTIFACTS['schema']]['$defs']['story']['required'] = []
    elif target == 'series_total': artifacts[ARTIFACTS['visual']]['series'][0]['sequence_total'] = 99
    elif target == 'title_series': artifacts[ARTIFACTS['titles']]['pieces'][0]['series_id'] = 'ABSENT'
    elif target == 'metrics': artifacts[ARTIFACTS['completeness']]['metadata_status_counts'] = {'COMPLETE_FOR_REVIEW': 999}
    assert_invalid(artifacts, legacy, semantic)


@pytest.mark.parametrize('problem', ['empty_timeout', 'invalid_model_provenance'])
def test_inference_failure_without_a_message_or_mapping_still_yields_valid_partial_metadata(problem):
    legacy, semantic = fixture()
    def broken(task, context, schema):
        if problem == 'empty_timeout': raise TimeoutError()
        return valid_payload(context), []
    artifacts = build_story_visual_handoff(legacy, semantic, broken)
    assert all(s['primary_title'] is None for s in stories(artifacts))
    assert validate_story_visual_handoff(artifacts, legacy, semantic)['status'] == 'valid'


def test_partial_reel_boundaries_abstain_before_inference_without_changing_shortlist():
    legacy, semantic = fixture()
    legacy['editorial/candidate_catalog.json']['candidates'] = [{
        'candidate_id': 'REEL_A', 'segment_ids': ['S0'], 'start': 1, 'end': 4,
        'default_shortlist_eligible': True, 'publication_ready': False}]
    legacy['editorial/default_shortlist.json']['candidate_ids'] = ['REEL_A']
    calls = []
    def recording(task, context, schema):
        calls.append(task)
        return infer(task, context, schema)
    artifacts = build_story_visual_handoff(legacy, semantic, recording)
    reel = next(p for p in artifacts[ARTIFACTS['titles']]['pieces'] if p['piece_type'] == 'REEL')
    assert reel['primary_title'] is None and reel['abstention_reason']
    assert 'titles:reel:REEL_A' not in calls
    assert legacy['editorial/default_shortlist.json']['candidate_ids'] == ['REEL_A']
    assert validate_story_visual_handoff(artifacts, legacy, semantic)['status'] == 'valid'
