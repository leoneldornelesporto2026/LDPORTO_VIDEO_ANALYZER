"""CPU fixtures only: no Ollama, ASR, model load or audiovisual pipeline."""
from copy import deepcopy
import hashlib
import json
import zipfile

import pytest

from ldporto.config import DEFAULTS
from ldporto.editorial_outcome import classify_editorial_outcome
from ldporto.ollama_local import chat, OllamaContentError, profile_options
from ldporto.progress import STAGE_WEIGHTS, WeightedProgress
from ldporto.semantic import inference_cost_summary, semantic_cache_key, semantic_source_items


def test_ollama_measures_separated_costs_without_reducing_max(monkeypatch):
    requests = []
    def request(*args, **kwargs):
        requests.append(kwargs['payload'])
        return {'message': {'content': '{}'}, 'total_duration': 10e9, 'load_duration': 2e9,
                'prompt_eval_duration': 3e9, 'eval_duration': 5e9,
                'prompt_eval_count': 300, 'eval_count': 100}
    monkeypatch.setattr('ldporto.ollama_local._request_json', request)
    data, metadata = chat('http://localhost:11434', 'synthetic-model',
                          [{'role': 'user', 'content': 'Fixture com acento: á'}], {}, DEFAULTS['semantic_analysis'])
    assert data == {}
    assert metadata['load_seconds'] == 2 and metadata['prompt_seconds'] == 3 and metadata['generation_seconds'] == 5
    assert metadata['prompt_tokens_per_second'] == 100 and metadata['generation_tokens_per_second'] == 20
    assert metadata['request_bytes'] == len(json.dumps(requests[0], ensure_ascii=False).encode('utf-8'))
    assert requests[0]['options'] == profile_options(DEFAULTS['semantic_analysis'])
    assert requests[0]['options']['num_ctx'] == 32768 and requests[0]['options']['num_predict'] == 6144
    assert 'Fixture' not in json.dumps(metadata)


@pytest.mark.parametrize('value', [None, True, -1, float('nan'), float('inf')])
def test_missing_invalid_server_measurements_remain_unknown(monkeypatch, value):
    monkeypatch.setattr('ldporto.ollama_local._request_json', lambda *a, **kw:
                        {'message': {'content': '{}'}, 'eval_duration': value, 'eval_count': value})
    _, meta = chat('http://localhost:11434', 'synthetic', [], {}, {})
    assert meta['eval_duration_ns'] is None and meta['generation_tokens_per_second'] is None
    summary = inference_cost_summary([meta])
    assert summary['semantic_generated_tokens'] is None and summary['semantic_generation_seconds'] is None


def test_transport_failure_keeps_type_and_elapsed_cost(monkeypatch):
    def request(*args, **kwargs):
        raise TimeoutError('synthetic timeout')
    monkeypatch.setattr('ldporto.ollama_local._request_json', request)
    with pytest.raises(TimeoutError) as error:
        chat('http://localhost:11434', 'synthetic', [], {}, {})
    assert error.value.metadata['duration_seconds'] >= 0
    assert error.value.metadata['failure_category'] == 'transport_error'


def test_failed_repair_preserves_initial_and_failed_call_cost(tmp_path, monkeypatch):
    from ldporto import semantic
    from test_v42_editorial import model_fixture, semantic_context
    ctx, transcript = semantic_context(tmp_path, monkeypatch)
    invalid = model_fixture()
    invalid['topics'][0]['segment_ids'] = ['BAD']
    initial = {'request_id': 'initial', 'eval_count': 100, 'eval_duration_ns': 1e9, 'duration_seconds': 1}
    failed = {'request_id': 'repair', 'eval_count': 40, 'eval_duration_ns': 2e9, 'duration_seconds': 2}
    monkeypatch.setattr(semantic, 'call_ollama', lambda *a: (invalid, initial))
    def repair(*args):
        raise OllamaContentError('empty repair', failed)
    monkeypatch.setattr(semantic, 'repair_ollama_output', repair)
    result = semantic.SemanticEngine().run(ctx, transcript)['data']
    assert result['ollama_calls'][0]['call'] == initial
    assert result['ollama_calls'][0]['repair_call'] == failed
    assert result['semantic_metrics']['semantic_generated_tokens'] == 140
    assert result['semantic_metrics']['semantic_tokens_per_second'] == pytest.approx(140 / 3)
    assert result['semantic_metrics']['semantic_repair_cost_seconds'] == 2


def test_throughput_uses_only_pairs_with_measured_tokens_and_time():
    summary = inference_cost_summary([{'eval_count': 10, 'eval_duration_ns': 2e9},
                                      {'eval_count': None, 'eval_duration_ns': 100e9},
                                      {'eval_count': 200, 'eval_duration_ns': None}])
    assert summary['semantic_tokens_per_second'] == 5
    assert summary['generation_throughput_measured_call_count'] == 1
    assert summary['semantic_generation_seconds'] == 102


def test_derived_telemetry_overflow_remains_unknown():
    from ldporto.ollama_local import inference_measurements
    assert inference_measurements({'eval_count': 1e308, 'eval_duration': 1e-299})['generation_tokens_per_second'] is None
    assert inference_cost_summary([{'eval_count': 1e308}, {'eval_count': 1e308}])['semantic_generated_tokens'] is None


def test_integer_counter_too_large_for_finite_conversion_remains_unknown():
    from ldporto.ollama_local import measured_number
    assert measured_number(10 ** 1000) is None


def test_global_local_validation_failure_is_not_a_fictional_inference(tmp_path, monkeypatch):
    from ldporto import semantic
    from test_v42_editorial import model_fixture, semantic_context
    ctx, transcript = semantic_context(tmp_path, monkeypatch)
    ctx.config['semantic_analysis'].update(global_review=True, global_max_chars=100)
    monkeypatch.setattr(semantic, 'call_ollama', lambda *a: (model_fixture(),
                        {'request_id': 'initial', 'eval_count': 10, 'eval_duration_ns': 2e9}))
    monkeypatch.setattr(semantic, 'ollama_chat', lambda *a: pytest.fail('input budget must fail before any global call'))
    result = semantic.SemanticEngine().run(ctx, transcript)['data']
    assert result['global_review_call']['inference_attempt_count'] == 0
    assert result['semantic_metrics']['total_inference_call_count'] == 1
    assert result['semantic_metrics']['inference_metadata_record_count'] == 1


def test_canonical_uncertainty_reaches_prompt_cache_and_grounded_results(monkeypatch):
    from ldporto import semantic
    from test_v42_editorial import model_fixture
    group = [{'segment_id': 'S', 'start': 0, 'end': 10, 'speaker': None,
              'text': 'The elephants have long trunks.', 'language': 'en', 'needs_review': True,
              'review_reasons': ['low_asr_confidence'], 'uncertain_word_ids': ['W1']}]
    captured = []
    monkeypatch.setattr(semantic, 'ollama_chat', lambda *args: (captured.append(args[2]) or model_fixture(), {}))
    semantic.call_ollama(DEFAULTS['semantic_analysis'], group)
    assert json.loads(captured[0][1]['content'])['transcript_data'][0]['text'] == group[0]['text']
    assert json.loads(captured[0][1]['content'])['transcript_data'][0]['uncertain_word_ids'] == ['W1']
    changed = deepcopy(group); changed[0]['needs_review'] = False
    assert semantic_cache_key(DEFAULTS['semantic_analysis'], group, 'synthetic') != semantic_cache_key(DEFAULTS['semantic_analysis'], changed, 'synthetic')
    result = semantic.ground_model_output(model_fixture(), group, 0)
    assert result['moments'][0]['text'] == group[0]['text']
    assert result['moments'][0]['source_transcript_needs_review'] is True
    assert result['moments'][0]['uncertain_segment_ids'] == ['S']
    assert semantic_source_items(group)[0]['language'] == 'en'


def test_completion_is_reserved_for_confirmed_finalization():
    model = WeightedProgress(clock=lambda: 0)
    for stage in STAGE_WEIGHTS:
        model.update({'stage': stage, 'status': 'ok', 'current': 1, 'total': 1})
    before = model.snapshot()
    assert before['overall_fraction'] == .95 and before['finalization_pending']
    assert before['completion_reserved_fraction'] == .05
    failed = model.update({'event': 'run_failed'})
    assert failed['overall_fraction'] == .95
    completed = WeightedProgress(clock=lambda: 0).update({'event': 'run_completed'})
    assert completed['overall_fraction'] == 1


def test_topic_merging_retains_uncertainty_from_later_original_segments(tmp_path, monkeypatch):
    from ldporto import semantic
    from test_v42_editorial import model_fixture, semantic_context
    ctx, transcript = semantic_context(tmp_path, monkeypatch)
    transcript['segments'] = [{'segment_id': 'S1', 'start': 0, 'end': 5, 'speaker': None, 'text': 'A gravacao foi feita no estudio.'},
                              {'segment_id': 'S2', 'start': 5, 'end': 10, 'speaker': None, 'text': 'Outro detalhe da gravacao.',
                               'needs_review': True, 'uncertain_word_ids': ['W2']}]
    first = model_fixture(); first['topics'][0]['segment_ids'] = ['S1']
    second = deepcopy(first['topics'][0]); second['segment_ids'] = ['S2']
    first['topics'].append(second); first['moments'] = []
    monkeypatch.setattr(semantic, 'call_ollama', lambda *a: (first, {}))
    result = semantic.SemanticEngine().run(ctx, transcript)['data']
    assert len(result['topics']) == 1
    for row in [*result['topics'], *result['program_sections'], result['primary_editorial_theme']]:
        assert row['source_transcript_needs_review'] is True and row['uncertain_segment_ids'] == ['S2']


def test_semantic_review_does_not_reuse_chunk_eta_or_show_100_percent():
    model = WeightedProgress({'15_semantic': 100, '20_handoff': 1}, clock=lambda: 0)
    for current in range(5):
        model.update({'stage': '15_semantic', 'status': 'running', 'current': current, 'total': 5,
                      'elapsed_seconds': current * 10, 'substage': 'local_grounded_extraction',
                      'progress_fraction': .9 * current / 5})
    assert model.snapshot()['stage_eta_seconds'] == 10
    review = model.update({'stage': '15_semantic', 'status': 'running', 'current': None, 'total': None,
                           'substage': 'global_review', 'progress_fraction': .9})
    assert review['stage_fraction'] == .9 and review['stage_eta_seconds'] is None
    assert review['eta_sample_count'] == 0
    assert review['overall_fraction'] < .95


@pytest.mark.parametrize('section,key,value', [('semantic_analysis', 'num_ctx', 8192),
    ('semantic_analysis', 'think', True), ('semantic_analysis', 'compact_prompt', True),
    ('semantic_analysis', 'global_review', False), ('transcription', 'beam_size', 1),
    ('diarization', 'enabled', False)])
def test_eta_history_requires_equivalent_config(monkeypatch, section, key, value):
    from ldporto.runtime_metrics import history_fingerprint
    monkeypatch.setattr('ldporto.runtime_metrics.gpu_history_profile', lambda: [])
    original = deepcopy(DEFAULTS); changed = deepcopy(original); changed[section][key] = value
    assert history_fingerprint({'duration': 19}, original) != history_fingerprint({'duration': 19}, changed)


def editorial_fixture():
    return {'metadata': {'duration': 90}, 'transcript_segments': [{'segment_id': 'S', 'text': 'Fala observada.'}],
            'main_moments': [{'moment_id': 'M', 'evidence_segment_ids': ['S'], 'editorial_score_final': .8}],
            'editorial_shortlist': [], 'stage_status': {}}


@pytest.mark.parametrize('change,state', [({}, 'no_eligible_cuts'),
    ({'transcript_segments': []}, 'insufficient_evidence'),
    ({'metadata': {'duration': 19}}, 'video_too_short'),
    ({'stage_status': {'16_understanding': {'status': 'failed'}}}, 'technical_error'),
    ({'main_moments': [{'moment_id': 'M', 'evidence_segment_ids': ['S'], 'editorial_score_final': .2}]}, 'low_quality_candidates'),
    ({'editorial_shortlist': ['M']}, 'selected')])
def test_editorial_outcomes_preserve_input_and_selection_policy(change, state):
    analysis = {**editorial_fixture(), **change}; before = deepcopy(analysis)
    result = classify_editorial_outcome(analysis)
    assert result['state'] == state and result['selection_policy_changed'] is False
    assert analysis == before and result['publication_ready'] is False


def test_unmeasured_quality_is_insufficient_not_low_quality():
    analysis = editorial_fixture(); analysis['main_moments'][0]['editorial_score_final'] = None
    assert classify_editorial_outcome(analysis)['state'] == 'insufficient_evidence'


def test_missing_candidate_uncertainty_flags_do_not_hide_source_uncertainty():
    analysis = editorial_fixture(); analysis['transcript_segments'][0]['needs_review'] = True
    assert classify_editorial_outcome(analysis)['state'] == 'insufficient_evidence'


def test_stale_shortlist_does_not_hide_required_technical_failure():
    analysis = editorial_fixture()
    analysis.update(editorial_shortlist=['M'], stage_status={'15_semantic': {'status': 'failed'}})
    assert classify_editorial_outcome(analysis)['state'] == 'technical_error'


def fidelity_package(tmp_path):
    from test_v43_handoff import analysis_fixture
    from ldporto.second_curation_export import build_core_package
    analysis = analysis_fixture()
    analysis['transcript_segments'][1].update(text='The elephants have long trunks.', language='en',
        language_hint='en', language_is_segment_verified=False, needs_review=True,
        review_reasons=['low_asr_confidence'], uncertain_word_ids=['W1'], hypothesis_ids=['H1'])
    analysis['transcript_original_import_segments'] = [{'segment_id': 'ORIGINAL1', 'start': 30, 'end': 90,
                                                       'text': 'The elephants have long trunks.'}]
    analysis['transcript_translations'] = [{'segment_id': 'ORIGINAL1', 'text': 'Os elefantes têm trombas longas.',
                                           'target_language': 'pt', 'source_language': 'en',
                                           'provenance': {'method': 'synthetic_import_fixture'}}]
    analysis['transcription_provenance'] = {'task': 'transcribe', 'configured_language': None}
    analysis['transcription_language_hypotheses'] = [{'hypothesis_id': 'H1', 'language_hint': 'en'}]
    analysis['transcription_alternatives'] = [{'window_id': 'R1', 'hypotheses': [{'text': 'long trunks'}]}]
    return build_core_package(analysis, output_dir=tmp_path)


def test_second_curation_preserves_original_language_uncertainty_and_separate_translation(tmp_path):
    from ldporto.second_curation_export import validate_core_package
    package = fidelity_package(tmp_path)
    assert validate_core_package(package['path'])['status'] == 'valid'
    with zipfile.ZipFile(package['path']) as archive:
        segments = [json.loads(line) for line in archive.read('transcript/relevant_segments.jsonl').decode().splitlines()]
        assert segments[1]['language'] == 'en' and segments[1]['uncertain_word_ids'] == ['W1']
        assert 'The elephants' in archive.read('transcript/transcript.txt').decode()
        assert 'Os elefantes' not in archive.read('transcript/transcript.srt').decode()
        translations = json.loads(archive.read('transcript/translations.json'))
        assert translations[0]['segment_id'] == 'ORIGINAL1'
        assert json.loads(archive.read('transcript/transcription_alternatives.json'))[0]['window_id'] == 'R1'
        manifest = json.loads(archive.read('SECOND_CURATION_MANIFEST.json'))
        assert manifest['transcript_contract']['translation_is_canonical'] is False
        assert manifest['editorial_result'] == package['editorial_result']


def test_legacy_word_projection_keeps_raw_fallback_usable(tmp_path):
    from test_v43_handoff import analysis_fixture
    from ldporto.second_curation_export import build_core_package
    from ldporto.transcription import word_text
    analysis = analysis_fixture()
    analysis['transcript_segments'][1]['text'] = 'Original legacy token.'
    analysis['words'] = [{'word_id': 'W1', 'segment_id': 'S1', 'word': 'Original legacy token.',
                          'start': 30, 'end': 90, 'speaker': 'SP1', 'confidence': .95}]
    package = build_core_package(analysis, output_dir=tmp_path)
    with zipfile.ZipFile(package['path']) as archive:
        words = [json.loads(line) for line in archive.read('transcript/relevant_words.jsonl').decode().splitlines()]
    assert 'raw' not in words[0]
    assert word_text(words) == 'Original legacy token.'


@pytest.mark.parametrize('member', ['transcript/translations.json', 'transcript/transcript.srt'])
def test_signed_package_rejects_invalid_translation_ids_and_original_rewrites(tmp_path, member):
    from ldporto.second_curation_export import validate_core_package
    package = fidelity_package(tmp_path)
    with zipfile.ZipFile(package['path']) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    if member.endswith('.json'):
        rows = json.loads(files[member]); rows[0]['segment_id'] = 'INVENTED'
        files[member] = json.dumps(rows, ensure_ascii=False).encode('utf-8')
    else:
        files[member] = files[member].replace(b'The elephants have long trunks.', b'Invented translation.')
    manifest = json.loads(files['SECOND_CURATION_MANIFEST.json'])
    entry = next(row for row in manifest['files'] if row['path'] == member)
    entry.update(bytes=len(files[member]), sha256=hashlib.sha256(files[member]).hexdigest())
    files['SECOND_CURATION_MANIFEST.json'] = json.dumps(manifest).encode('utf-8')
    modified = tmp_path / 'signed_but_semantically_invalid.zip'
    with zipfile.ZipFile(modified, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    validation = validate_core_package(modified)
    assert validation['status'] == 'failed'
    assert any(error.startswith('transcript_contract:') for error in validation['errors'])


@pytest.mark.parametrize('marker', [{'text_kind': 'semantic_rewrite'}, {'task': 'translate'},
                                  {'asr_task': 'translate'}, {'is_translation': True}, {'source': 'translation'}])
def test_package_rejects_explicit_nonoriginal_canonical_markers(tmp_path, marker):
    from test_v43_handoff import analysis_fixture
    from ldporto.second_curation_export import build_core_package
    analysis = analysis_fixture(); analysis['transcript_segments'][0].update(marker)
    with pytest.raises(ValueError, match='canonical_translation_or_rewrite'):
        build_core_package(analysis, output_dir=tmp_path)


def test_rehashed_editorial_result_disagreement_fails_package_validation(tmp_path):
    from ldporto.second_curation_export import validate_core_package
    package = fidelity_package(tmp_path)
    with zipfile.ZipFile(package['path']) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    summary = json.loads(files['summary/analysis_summary.json'])
    summary['editorial_result']['state'] = 'technical_error' if summary['editorial_result']['state'] == 'selected' else 'selected'
    files['summary/analysis_summary.json'] = json.dumps(summary).encode()
    manifest = json.loads(files['SECOND_CURATION_MANIFEST.json'])
    entry = next(row for row in manifest['files'] if row['path'] == 'summary/analysis_summary.json')
    entry.update(bytes=len(files[entry['path']]), sha256=hashlib.sha256(files[entry['path']]).hexdigest())
    files['SECOND_CURATION_MANIFEST.json'] = json.dumps(manifest).encode()
    modified = tmp_path / 'editorial_disagreement.zip'
    with zipfile.ZipFile(modified, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    validation = validate_core_package(modified)
    assert validation['status'] == 'failed'
    assert 'editorial_result:manifest_index_brief_summary_disagreement' in validation['errors']
