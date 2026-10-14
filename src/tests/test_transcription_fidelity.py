"""Synthetic backend/contract tests; no acoustic accuracy or GPU claims."""
from copy import deepcopy
import logging
from types import SimpleNamespace

import pytest

from ldporto.config import load_config, validate
from ldporto.core import Context
from ldporto.diarization import align_speakers
from ldporto import transcription


def context(tmp_path):
    cfg = load_config()
    cfg.update(device='cpu', offline=True)
    return Context(tmp_path / 'absent.mp4', tmp_path, cfg, 'synthetic', logging.getLogger('asr-fidelity'))


def backend(text, language, probability=.95, segment_language=None):
    word = SimpleNamespace(word=' ' + text, start=0., end=1., probability=.99)
    segment = SimpleNamespace(start=0., end=1., text=text, words=[word], avg_logprob=-.1, no_speech_prob=.01)
    if segment_language:
        segment.language = segment_language
    info = SimpleNamespace(language=language, language_probability=probability, duration_after_vad=1.,
                           all_language_probs=[(language, probability)])
    return iter([segment]), info


@pytest.mark.parametrize('text,language', [('Hello elephants.', 'en'), ('Ola elefantes.', 'pt'),
                                         ('Hello, bom dia.', 'en')])
def test_automatic_original_language_and_explicit_task(tmp_path, text, language):
    ctx = context(tmp_path)
    source = tmp_path / 'synthetic.wav'
    source.write_bytes(b'synthetic placeholder, not acoustic evidence')
    calls = []
    engine = transcription.TranscriptionEngine(ctx)
    engine.model = SimpleNamespace(transcribe=lambda path, **options:
                                  (calls.append(options) or backend(text, language)))
    result = engine.recognize(source)
    assert calls[0]['task'] == 'transcribe' and calls[0]['language'] is None
    assert calls[0]['multilingual'] is True
    assert result['words'][0]['word'] == text and result['segments'][0]['text'] == text
    assert result['language_hint'] == language and result['language_mode'] == 'automatic_multilingual'
    # Current faster-whisper does not expose each multilingual segment's language.
    assert result['words'][0]['language'] is None
    assert result['words'][0]['language_probability'] is None
    assert result['words'][0]['language_detection_scope'] == 'chunk_initial_hint'
    assert result['provenance']['task'] == 'transcribe'
    assert len(result['provenance']['audio_sha256']) == 64
    assert result['words'][0]['hypothesis_id'] == result['hypothesis_id']
    assert not result['provenance']['independent_audio_verification']


def test_explicit_language_is_configured_not_detected(tmp_path):
    ctx = context(tmp_path)
    ctx.config['language'] = 'pt'
    source = tmp_path / 'fake.wav'
    source.write_bytes(b'fixture')
    engine = transcription.TranscriptionEngine(ctx)
    sent = []
    engine.model = SimpleNamespace(transcribe=lambda path, **options:
                                  (sent.append(options) or backend('Original.', 'pt', 1.)))
    result = engine.recognize(source)
    assert sent[0]['language'] == 'pt' and sent[0]['multilingual'] is False
    assert result['language_probability'] is None
    assert result['words'][0]['language_detection_scope'] == 'configured_language'
    assert result['words'][0]['language'] == 'pt'


def test_low_language_probability_propagates_without_rewriting(tmp_path):
    ctx = context(tmp_path)
    source = tmp_path / 'fake.wav'
    source.write_bytes(b'fixture')
    engine = transcription.TranscriptionEngine(ctx)
    engine.model = SimpleNamespace(transcribe=lambda *args, **options: backend('Uncertain original.', 'en', .3))
    data = engine.recognize(source)
    data['words'][0]['word_id'] = 'W'
    data['segments'] = transcription.regroup_words(data['words'])
    transcription.annotate_review(data, .6)
    aligned = align_speakers(data, {})
    assert aligned['words'][0]['word'] == 'Uncertain original.'
    segment = aligned['segments'][0]
    assert segment['needs_review'] and segment['uncertain_word_ids'] == ['W']
    assert 'language_detection_uncertain' in segment['review_reasons']
    assert segment['language'] is None and segment['language_hint'] == 'en'
    assert segment['hypothesis_ids'] == [data['hypothesis_id']]


def test_mixed_language_hints_never_become_a_fabricated_segment_language():
    words = [{'word': 'Hello', 'raw': 'Hello', 'start': 0., 'end': 1., 'confidence': .9,
              'word_id': 'W1', 'language': None, 'language_hint': 'en', 'hypothesis_id': 'EN'},
             {'word': 'bom dia.', 'raw': ', bom dia.', 'start': 1., 'end': 2., 'confidence': .9,
              'word_id': 'W2', 'language': None, 'language_hint': 'pt', 'hypothesis_id': 'PT'}]
    segments = transcription.regroup_words(words)
    assert segments[0]['text'] == 'Hello, bom dia.'
    assert segments[0]['language'] is None and segments[0]['language_hint'] is None
    assert segments[0]['language_hints'] == ['en', 'pt']
    assert segments[0]['hypothesis_ids'] == ['EN', 'PT']


def imported():
    return {'words': [{'word': 'Elephants.', 'start': 0, 'end': 1, 'confidence': .9, 'segment_id': 'EN'}],
            'segments': [{'segment_id': 'EN', 'start': 0, 'end': 1, 'text': 'Elephants.', 'language': 'en'}],
            'translations': [{'segment_id': 'EN', 'text': 'Elefantes.', 'target_language': 'pt'}],
            'provenance': {'source': 'synthetic_import'}}


def test_import_is_immutable_and_translation_is_a_separate_artifact():
    original = imported()
    before = deepcopy(original)
    data = transcription.validate_import(original, 2)
    assert original == before
    assert data['words'][0]['word'] == 'Elephants.'
    assert data['segments'][0]['text'] == 'Elephants.'
    assert data['translations'][0]['text'] == 'Elefantes.'
    assert data['translations'][0]['text_kind'] == 'translation'
    aligned = align_speakers(data, {})
    assert aligned['original_import_segments'][0]['segment_id'] == 'EN'
    assert aligned['translations'][0]['segment_id'] == 'EN'
    assert aligned['segments'][0]['language'] == 'en'
    assert aligned['import_provenance'] == before['provenance']


@pytest.mark.parametrize('level,key,value', [('root', 'task', 'translate'),
    ('word', 'text_kind', 'semantic_rewrite'), ('segment', 'text_kind', 'translation'),
    ('word', 'is_translation', True), ('segment', 'asr_task', 'translate')])
def test_explicit_translation_and_semantic_rewrite_cannot_be_canonical(level, key, value):
    data = imported()
    row = data if level == 'root' else data['words' if level == 'word' else 'segments'][0]
    row[key] = value
    with pytest.raises(ValueError, match='original'):
        transcription.validate_import(data, 2)


@pytest.mark.parametrize('changes', [{'segment_id': 'ABSENT'}, {'target_language': ''}, {'text': None}])
def test_separate_translation_must_reference_an_original_segment(changes):
    data = imported()
    data['translations'][0].update(changes)
    with pytest.raises(ValueError, match='Traducao'):
        transcription.validate_import(data, 2)


def test_acoustic_disagreement_propagates_but_never_replaces_original():
    data = {'words': [{'word': 'trunks.', 'start': 0., 'end': 1., 'confidence': .99, 'word_id': 'W'}],
            'transcription_alternatives': [{'start': 0., 'end': 1., 'selected_text': 'trunks.',
                                            'alternatives': [{'text': 'frutas.'}], 'replacement_applied': False}]}
    data['segments'] = transcription.regroup_words(data['words'])
    transcription.flag_alternative_disagreements(data)
    transcription.annotate_review(data, .6)
    assert data['words'][0]['word'] == 'trunks.'
    assert data['segments'][0]['needs_review']
    assert 'acoustic_hypotheses_disagree' in data['segments'][0]['review_reasons']
    assert not data['transcription_alternatives'][0]['replacement_applied']


@pytest.mark.parametrize('calls,seconds,expected', [(0, 180, 0), (1, 180, 1), (16, 1, 0)])
def test_multipass_limits_calls_and_audio_seconds(tmp_path, monkeypatch, calls, seconds, expected):
    ctx = context(tmp_path)
    ctx.config['transcription'].update(max_review_calls=calls, max_review_audio_seconds=seconds)
    data = {'source': 'original', 'words': [{'word': 'Original.', 'start': 3., 'end': 4., 'confidence': .1}],
            'low_confidence_words': [{'start': 3., 'end': 4.}]}
    engine = transcription.TranscriptionEngine(ctx)
    actual = []
    monkeypatch.setattr(transcription, 'ffmpeg_audio', lambda *args, **kwargs: None)
    engine.recognize = lambda *args: (actual.append(True) or {'words': [
        {'word': 'Alternative.', 'start': 3., 'end': 4., 'confidence': .99}]})
    before = deepcopy(data['words'])
    rows = engine.review(data, {'mono': 'original', 'speech_clean': 'clean', 'speech_isolated': 'isolated'}, 10)
    assert len(actual) == expected and data['review_budget']['asr_calls'] == expected
    assert data['review_budget']['processed_audio_seconds'] <= seconds
    assert data['words'] == before and all(not row['replacement_applied'] for row in rows)
    assert data['review_budget']['deferred']


@pytest.mark.parametrize('key,value', [('max_review_calls', True), ('max_review_calls', -1),
    ('max_review_audio_seconds', float('inf')), ('language_confidence_threshold', 1.1), ('multilingual', 'yes')])
def test_fidelity_budget_configuration_rejects_invalid_values(key, value):
    config = load_config()
    config['transcription'][key] = value
    with pytest.raises(ValueError):
        validate(config)


@pytest.mark.parametrize('clean_language', ['pt', 'en'])
def test_cleaned_source_cannot_override_language_or_text_disagreement(tmp_path, monkeypatch, clean_language):
    engine = transcription.TranscriptionEngine(context(tmp_path))
    monkeypatch.setattr(transcription, 'ffmpeg_audio', lambda *args, **kwargs: None)
    def recognize(path, offset):
        clean = 'speech_clean' in path.name
        return {'words': [{'word': 'frutas' if clean else 'trunks', 'confidence': .99 if clean else .8}],
                'language_hint': clean_language if clean else 'en'}
    engine.recognize = recognize
    selected, comparisons, label = engine.select_source({'mono': 'original', 'speech_clean': 'clean'},
        {'quality_windows': [{'start': 0., 'end': 5., 'rms_dbfs': -20.}]}, 5.)
    assert selected == 'original' and label == 'original'
    assert comparisons[0]['hypotheses']['speech_clean']['language_hint'] == clean_language
    assert comparisons[0]['needs_review']
    assert comparisons[0]['language_disagreement'] == (clean_language != 'en')


def test_hypothesis_identity_binds_actual_decoding_settings(tmp_path):
    ctx = context(tmp_path)
    source = tmp_path / 'fake.wav'
    source.write_bytes(b'fixture')
    engine = transcription.TranscriptionEngine(ctx)
    engine.model = SimpleNamespace(transcribe=lambda *args, **options: backend('Literal.', 'en'))
    first = engine.recognize(source)
    ctx.config['transcription']['beam_size'] += 1
    second = engine.recognize(source)
    assert first['hypothesis_id'] != second['hypothesis_id']
    assert first['provenance']['decoding']['beam_size'] != second['provenance']['decoding']['beam_size']
    assert first['provenance']['code_sha256'] and first['provenance']['backend_versions']
    assert 'provenance' not in first['words'][0]


def test_import_disagreement_is_preserved_and_flagged_without_guessing():
    original = imported()
    original['words'][0]['raw'] = ' Fruit.'
    original['segments'][0]['text'] = 'Different original hypothesis.'
    before = deepcopy(original)
    data = transcription.validate_import(original, 2)
    transcription.annotate_review(data, .6)
    assert original == before
    assert data['words'][0]['word'] == 'Elephants.' and data['words'][0]['raw'] == ' Fruit.'
    assert data['segments'][0]['text'] == 'Different original hypothesis.'
    assert data['original_import_segments'][0]['text'] == 'Different original hypothesis.'
    assert data['segments'][0]['needs_review']
    assert set(data['segments'][0]['review_reasons']) == {
        'imported_word_raw_disagreement', 'imported_segment_word_disagreement'}


def test_import_bounded_timestamp_keeps_raw_evidence():
    data = imported()
    data['words'][0]['end'] = data['segments'][0]['end'] = 2.05
    result = transcription.validate_import(data, 2)
    assert result['words'][0]['end'] == 2 and result['words'][0]['raw_end'] == 2.05
    assert result['original_import_segments'][0]['raw_end'] == 2.05
    assert result['words'][0]['timestamp_repaired']


def test_import_auto_configuration_is_not_a_detected_speech_language():
    data = imported()
    data['language'] = 'auto'
    data['segments'][0].pop('language')
    result = transcription.validate_import(data, 2)
    assert result['words'][0]['language'] is None
    assert result['words'][0]['language_hint'] is None


def test_full_asr_run_propagates_high_confidence_source_disagreement(tmp_path, monkeypatch):
    ctx = context(tmp_path)
    ctx.config['transcription']['multipass'] = False
    source = tmp_path / 'fake.wav'
    source.write_bytes(b'fixture')
    engine = transcription.TranscriptionEngine(ctx)
    engine.select_source = lambda *args: (source, [{'start': 0., 'end': 1., 'needs_review': True}], 'original')
    engine.recognize = lambda *args: {'words': [{'word': 'trunks.', 'start': 0., 'end': 1., 'confidence': .99}],
                                   'segments': [{'start': 0., 'end': 1., 'words': [True]}]}
    monkeypatch.setattr(transcription, 'ffmpeg_audio', lambda *args, **options: None)
    result = engine.run({'mono': source}, {}, {'duration': 2})
    assert result['status'] == 'partial'
    data = result['data']
    assert data['words'][0]['word'] == 'trunks.'
    assert data['segments'][0]['needs_review']
    assert 'source_hypotheses_disagree' in data['segments'][0]['review_reasons']


def test_reconstructed_candidate_keeps_uncertainty_added_by_boundary_expansion():
    from ldporto.understanding import build_main_moments
    from ldporto.editorial_outcome import classify_editorial_outcome
    from test_stage12_candidate_recovery import seg, core
    source = [seg('S', 0, 30, 'Nunca contei o segredo porque'),
              {**seg('D', 30, 35, 'a maquina era um prototipo experimental.'),
               'needs_review': True, 'review_reasons': ['language_detection_uncertain'], 'uncertain_word_ids': ['W']}]
    moment = core(end=30, text=source[0]['text'])
    moment.update(source_transcript_needs_review=False, uncertain_segment_ids=[])
    saved = deepcopy((source, moment))
    candidates = build_main_moments({'segments': source}, [], [moment], [], [], [])
    candidate = candidates[0]
    assert candidate['ideal_end'] == 35 and 'D' in candidate['evidence_segment_ids']
    assert candidate['source_transcript_needs_review'] and candidate['uncertain_segment_ids'] == ['D']
    assert candidate['needs_review'] and (source, moment) == saved
    diagnosis = classify_editorial_outcome({'metadata': {'duration': 90}, 'main_moments': candidates,
        'transcript_segments': source, 'editorial_shortlist': []})
    assert diagnosis['state'] == 'insufficient_evidence'
