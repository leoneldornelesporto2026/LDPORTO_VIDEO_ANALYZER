"""ASR comparison fixtures: flags are observations, never acoustic correctness."""
from copy import deepcopy
import json
from pathlib import Path
import pytest

from ldporto.asr_comparison import compare_hypotheses, source_review_dossier, review_reason_metrics
from ldporto.transcription import annotate_review, flag_alternative_disagreements, regroup_words, word_text
from ldporto.targeted_asr import run_on_demand_review
from ldporto.subtitle_review import review_selected_clips


def words(tokens, start=0., step=.5):
    return [{'word': text, 'raw': ' '+text, 'word_id': f'W{i}', 'start': start+i*step,
             'end': start+(i+1)*step, 'confidence': .95} for i, text in enumerate(tokens)]


def alternative(tokens, **settings):
    rows = words(tokens, **settings)
    return {'text': word_text(rows), 'words': rows}


@pytest.mark.parametrize('tokens', [['HELLO,', 'WORLD!'], ['hello', 'world'], ['Hello...', 'world.']])
def test_case_punctuation_and_alignment_drift_are_not_lexical_errors(tokens):
    original = words(['Hello,', 'world.'])
    compared = compare_hypotheses(original, alternative(tokens, start=.05), 0., 2.)
    assert compared['status'] == 'equivalent'
    assert not compared['affected_word_ids'] and compared['lexical_difference_count'] == 0
    assert not compared['replacement_permitted']


def test_one_word_disagreement_does_not_flag_equivalent_phrase_context():
    original = words(['They', 'have', 'long', 'trunks.', 'And', "that's", 'cool.'])
    alternate = alternative(['They', 'have', 'long', 'front,', 'and', "that's", 'cool.'])
    data = {'words': original, 'segments': regroup_words(original), 'transcription_alternatives': [
        {'start': 0., 'end': 4., 'selected_text': word_text(original), 'alternatives': [alternate]}]}
    literal = [(word['word'], word['raw'], word['start'], word['end']) for word in original]
    flag_alternative_disagreements(data)
    annotate_review(data, .6)
    assert [w['word_id'] for w in original if w['needs_review']] == ['W3']
    assert [(w['word'], w['raw'], w['start'], w['end']) for w in original] == literal
    assert data['transcription_alternatives'][0]['hypotheses_disagree']


def test_repeated_tokens_use_temporal_anchor_for_one_inserted_word():
    original = words(['really,', 'really,', 'really', 'long', 'trunks.'])
    alternate = alternative(['really,', 'really,', 'really', 'really', 'long', 'trunks.'], start=0., step=.4)
    compared = compare_hypotheses(original, alternate, 0., 4.)
    assert compared['lexical_difference_count'] == 1
    assert len(compared['affected_word_ids']) <= 2
    assert 'W4' not in compared['affected_word_ids']
    assert [event['kind'] for event in compared['events']] == ['insert']


def test_clip_edge_omission_is_boundary_unknown_not_whole_phrase_disagreement():
    original = words(['that', 'they'], start=6.3, step=.48)
    compared = compare_hypotheses(original, alternative(['that...'], start=6.3, step=.48), 6., 7.04)
    assert compared['status'] == 'clip_boundary_unresolved'
    assert compared['lexical_difference_count'] == 0
    assert compared['affected_word_ids'] == [] and compared['boundary_word_ids'] == ['W1']


def test_timestamp_disagreement_is_distinct_from_lexical_change():
    original = words(['Literal.'])
    compared = compare_hypotheses(original, alternative(['Literal.'], start=1.2), 0., 3.)
    assert compared['status'] == 'timing_difference_only'
    assert compared['timestamp_difference_count'] == 1 and compared['lexical_difference_count'] == 0


def test_text_only_difference_retains_region_without_fabricated_word_mapping():
    original = words(['long', 'trunks.'])
    compared = compare_hypotheses(original, {'text': 'long fruit.'}, 0., 2.)
    assert compared['status'] == 'unlocalized_text_difference'
    assert compared['affected_word_ids'] == [] and compared['lexical_difference_count'] is None
    assert compared['unresolved_regions'][0]['reason'] == 'word_timestamps_unavailable'


def test_code_switch_and_different_accents_remain_literal_differences():
    original = words(['Hello,', 'bom', 'dia.', 'avó.'])
    compared = compare_hypotheses(original, alternative(['Hello!', 'bom', 'dia!', 'avô.']), 0., 3.)
    assert compared['affected_word_ids'] == ['W3']
    assert original[-1]['word'] == 'avó.'


def test_unmatched_silence_has_no_invented_canonical_words():
    compared = compare_hypotheses([], alternative(['unexpected.']), 0., 2.)
    assert compared['affected_word_ids'] == [] and compared['lexical_difference_count'] == 1
    assert compared['events'][0]['original_word'] is None


def test_recomputed_flags_preserve_external_and_model_uncertainty():
    original = words(['Literal.', 'Original.', 'Uncertain.'])
    for word in original:
        word.update(needs_review=True, asr_discrepancy=True, review_reasons=['acoustic_hypotheses_disagree'])
    original[0]['review_reasons'].append('human_marked_uncertain')
    original[1].update(confidence=.2, review_reasons=['source_hypotheses_disagree', 'missing_or_low_model_probability'])
    data = {'words': original, 'segments': regroup_words(original), 'transcription_alternatives': [
        {'start': 0., 'end': 2., 'selected_text': word_text(original), 'alternatives': [alternative(['Literal.', 'Original.', 'Uncertain.'])]}]}
    flag_alternative_disagreements(data, recompute=True)
    annotate_review(data, .6)
    assert original[0]['review_reasons'] == ['human_marked_uncertain']
    assert original[1]['review_reasons'] == ['missing_or_low_model_probability']
    assert not original[2]['needs_review']
    metrics = review_reason_metrics(original)
    assert sum(row['word_count'] for row in metrics['exclusive_reason_signatures']) == 2
    assert metrics['word_error_rate'] is None and metrics['verified_correct_word_count'] is None


def test_source_dossier_remains_actionable_without_any_candidate_or_new_model(tmp_path, monkeypatch):
    from test_stage49_on_demand_asr import setup_review
    ctx, source, transcript, candidates, calls, _ = setup_review(tmp_path, monkeypatch)
    ctx.config['transcription'].update(targeted_review_candidate_ids=[], targeted_review_opt_in=False)
    transcript['review_budget'] = {'asr_calls': 2, 'processed_audio_seconds': 18.334}
    transcript['words'][0]['review_reasons'] = ['missing_or_low_model_probability']
    original = deepcopy(transcript)
    report = run_on_demand_review(ctx, {'mono': source}, transcript, [], [], [], 60,
        recognize=lambda *args: pytest.fail('No additional ASR requested'))
    dossier = report['source_audio_review']
    assert report['pending_reason'] == 'human_review_queue_empty'
    assert dossier['windows'] and dossier['windows'][0]['candidate_id'] is None
    assert not dossier['requires_editorial_shortlist'] and dossier['new_asr_calls'] == 0
    assert dossier['acoustic_multipass']['asr_calls'] == 2
    assert not dossier['audio_verification_performed'] and not dossier['publication_ready']
    assert transcript == original and calls == []
    subtitles = review_selected_clips(transcript['words'], [], [], targeted_report=report)
    assert subtitles['source_audio_review']['windows'] and subtitles['selected_candidate_count'] == 0
    assert subtitles['human_audio_review_status'] == 'pending'


@pytest.mark.parametrize('regions,seconds', [(0, 180), (16, 1)])
def test_source_review_budget_does_not_discard_unresolved_regions(regions, seconds):
    source = words(['Original.'], start=3.)
    source[0].update(needs_review=True, review_reasons=['external_review_flag'])
    result = source_review_dossier({'words': source}, 20., max_regions=regions, max_audio_seconds=seconds)
    assert result['windows'] == [] and result['deferred']
    assert result['listening_budget']['planned_audio_seconds'] == 0
    assert result['status'] == 'pending_human_audio_review'


def test_english_long_trunks_regression_is_fixture_only():
    original = words(['really,', 'really,', 'really', 'long', 'trunks.'])
    saved = deepcopy(original)
    compared = compare_hypotheses(original, alternative(['really,', 'really,', 'really', 'long', 'front.']), 0., 4.)
    assert compared['affected_word_ids'] == ['W4']
    assert word_text(original) == 'really, really, really long trunks.' and original == saved


def test_historical_word_time_replay_reclassifies_flags_without_claiming_accuracy():
    data = json.loads((Path(__file__).parent / 'fixtures/sol_v3_asr_historical.json').read_text(encoding='utf-8'))
    original = deepcopy(data['words'])
    assert review_reason_metrics(original)['flagged_word_count'] == 36
    data['segments'] = regroup_words(data['words'])
    flag_alternative_disagreements(data, recompute=True)
    annotate_review(data, .6)
    metrics = review_reason_metrics(data['words'])
    assert metrics['flagged_word_count'] == 6 and metrics['word_count'] == 37
    assert metrics['word_error_rate'] is None and metrics['verified_correct_word_count'] is None
    assert 'really, really, really long trunks.' in word_text(data['words'])
    assert [(w['word'], w['start'], w['end'], w['confidence']) for w in data['words']] == [
        (w['word'], w['start'], w['end'], w['confidence']) for w in original]
    assert data['hypothesis_comparison']['unresolved_regions']  # Text-only pilots cannot invent timings.


def test_real_smoke_uses_inspect_wrapper_and_audio_api_without_model_inference(tmp_path, monkeypatch):
    import importlib.util
    from ldporto.core import ok
    import ldporto.audio
    import ldporto.media
    import ldporto.transcription
    source = tmp_path / 'synthetic.mp4'
    source.write_bytes(b'synthetic source placeholder')
    local = tmp_path / 'synthetic-local-model'
    local.mkdir()
    for filename in ('model.bin', 'config.json', 'tokenizer.json'):
        (local / filename).write_bytes(b'synthetic asset, not real model')
    monkeypatch.setattr(ldporto.media, 'inspect', lambda path: ok({'duration': 19.014,
        'audio_start_time': 0., 'video_start_time': 0.}))
    calls = []
    def extract(path, output, *, filters=None, sample_rate=16000, channels=1,
                start=None, duration=None, codec='pcm_s16le'):
        calls.append((sample_rate, channels, filters))
        Path(output).write_bytes(b'synthetic mono16k placeholder')
    monkeypatch.setattr(ldporto.audio, 'ffmpeg_audio', extract)
    def stop_before_loading(self, force_cpu=False):
        raise RuntimeError('synthetic_stop_before_model_load')
    monkeypatch.setattr(ldporto.transcription.TranscriptionEngine, '_load', stop_before_loading)
    script = Path(__file__).resolve().parents[2] / 'scripts/dev/smoke_source_asr.py'
    spec = importlib.util.spec_from_file_location('source_asr_cli_fixture', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / 'exclusive.json'
    assert module.main([str(source), '--output', str(output), '--model', str(local), '--device', 'cpu']) == 2
    recorded = json.loads(output.read_text(encoding='utf-8'))
    assert recorded['source_metadata']['duration'] == 19.014
    assert recorded['error'] == 'synthetic_stop_before_model_load' and not recorded['inference_executed']
    assert calls == [(16000, 1, 'asetpts=PTS-STARTPTS,apad,atrim=duration=19.014000000')]
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        module.main([str(source), '--output', str(output), '--model', str(local)])
    assert output.read_bytes() == before


def test_historical_unlocalized_region_survives_speaker_regrouping_without_word_flags():
    from ldporto.diarization import align_speakers
    data = json.loads((Path(__file__).parent / 'fixtures/sol_v3_asr_historical.json').read_text(encoding='utf-8'))
    data['segments'] = regroup_words(data['words'])
    flag_alternative_disagreements(data, recompute=True)
    annotate_review(data, .6)
    saved = deepcopy(data)
    flags = [(w['word_id'], w['needs_review'], w['review_reasons'], w['confidence']) for w in data['words']]
    aligned = align_speakers(data, {'turns': [{'start': 0., 'end': 19.014, 'speaker': 'SPEAKER_SYNTHETIC'}]})
    final = aligned['segments'][-1]
    assert final['text'] == "And that's pretty much all there is to say."
    assert final['needs_review'] and final['review_reasons'] == ['source_hypotheses_disagree']
    assert final['uncertain_word_ids'] == []  # Region has no honest word mapping.
    assert [(w['word_id'], w['needs_review'], w['review_reasons'], w['confidence']) for w in aligned['words']] == flags
    canonical = {w['word_id']: w for w in aligned['words']}
    assert len(aligned['low_confidence_words']) == 6
    for row in aligned['low_confidence_words']:
        assert row['segment_id'] == canonical[row['word_id']]['segment_id']
        assert row['speaker'] == canonical[row['word_id']]['speaker'] == 'SPEAKER_SYNTHETIC'
    assert data == saved


def test_unlocalized_region_uses_bounded_overlap_without_inventing_word_error():
    from ldporto.transcription import propagate_unlocalized_review
    segments = [{'segment_id': f'S{i}', 'start': float(i), 'end': float(i+1), 'text': 'Literal.',
                 'needs_review': False, 'review_reasons': []} for i in range(3)]
    data = {'segments': segments, 'words': words(['Literal.']), 'hypothesis_comparison': {'unresolved_regions': [
        {'start': 1., 'end': 2., 'reason': 'unlocalized_comparison'},
        {'start': float('nan'), 'end': 3., 'reason': 'invalid_region'}]}}
    original_words = deepcopy(data['words'])
    propagate_unlocalized_review(data)
    assert [s['needs_review'] for s in segments] == [False, True, False]
    assert segments[1]['review_reasons'] == ['unlocalized_comparison']
    assert data['words'] == original_words
