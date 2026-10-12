"""Synthetic audio bytes, mocked extraction/ASR; no listening or model execution."""
from copy import deepcopy
import csv
import logging

import pytest

from ldporto.config import load_config
from ldporto.core import Context, file_hash, read_json
from ldporto.targeted_asr import run_on_demand_review
from ldporto.subtitle_review import (review_selected_clips, write_review_kit,
    apply_human_subtitle_review, approve_reviewed_subtitles, subtitle_finalization_gate)


def setup_review(tmp_path, monkeypatch, **settings):
    from ldporto import targeted_asr
    source = tmp_path / 'fake.wav'
    source.write_bytes(b'FAKE: no acoustic evidence')
    cfg = load_config()
    cfg['transcription'].update(targeted_review_opt_in=True,
        targeted_review_candidate_ids=['QUEUED'], targeted_source_sha256=file_hash(source),
        targeted_max_regions=3, targeted_max_audio_seconds=9)
    cfg['transcription'].update(settings)
    ctx = Context(tmp_path/'source.mp4', tmp_path/'out', cfg, 'SYNTHETIC', logging.getLogger('s49'))
    calls = []
    def extract(src, destination, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b'FAKE WINDOW')
    def recognize(path, offset):
        calls.append(offset)
        return {'words': [{'word': 'Alternativa, PT-BR.', 'start': offset, 'end': offset+.5,
                           'confidence': .999}]}
    monkeypatch.setattr(targeted_asr, 'ffmpeg_audio', extract)
    candidates = [{'candidate_id': 'QUEUED', 'start': 10, 'end': 20},
                  {'candidate_id': 'NOT_QUEUED', 'start': 30, 'end': 50}]
    transcript = {'words': [{'word_id': 'W', 'word': 'Original, né?', 'raw': 'Original, né?',
        'start': 14, 'end': 15, 'needs_review': True, 'speech_overlap': True},
        {'word_id': 'OUT', 'word': 'Fora.', 'start': 35, 'end': 36, 'needs_review': True}]}
    def run(**extra):
        return run_on_demand_review(ctx, {'mono': str(source)}, transcript, candidates, [], [], 60,
                                   recognize=recognize, **extra)
    return ctx, source, transcript, candidates, calls, run


def test_exact_eligible_windows_cost_and_preserved_original(tmp_path, monkeypatch):
    ctx, source, transcript, candidates, calls, run = setup_review(tmp_path, monkeypatch)
    before = deepcopy(transcript)
    report = run()
    assert sorted((w['start'], w['end']) for w in report['windows']) == [(10, 12), (12, 17), (18, 20)]
    assert sorted(calls) == [10, 12, 18]
    assert report['source_sha256_validated'] is True
    assert report['audio_seconds'] == report['manual_review']['budget']['planned_audio_seconds'] == 9
    assert report['manual_review']['budget']['window_seconds_p95'] == 5
    assert report['manual_review']['budget']['asr_calls'] == 3
    metrics = report['manual_review']['candidate_metrics']['QUEUED']
    assert metrics['flagged_fraction'] == 1 and metrics['incorrect_word_fraction'] is None
    assert all(r['candidate_id'] == 'QUEUED' for r in report['manual_review']['windows'])
    assert any(r['ORIGINAL'] == [before['words'][0]] for r in report['manual_review']['windows'])
    assert transcript == before
    for row in report['manual_review']['windows']:
        assert row['needs_review'] and row['verified_by_audio'] is None
        assert not row['correction_approved'] and not row['subtitle_publish_ready']
        assert len(row['review_sha256']) == 64 and row['alternatives']
    assert not report['original_audio_verified'] and not report['publication_ready']


@pytest.mark.parametrize('settings,reason', [
    ({'targeted_review_opt_in': False}, 'targeted_review_not_requested'),
    ({'targeted_review_candidate_ids': []}, 'human_review_queue_empty'),
    ({'targeted_source_sha256': None}, 'expected_source_sha256_required'),
    ({'targeted_source_sha256': '0'*64}, 'source_sha256_mismatch'),
])
def test_source_or_opt_in_failure_never_consumes_asr(tmp_path, monkeypatch, settings, reason):
    ctx, source, transcript, candidates, calls, run = setup_review(tmp_path, monkeypatch, **settings)
    from ldporto import targeted_asr
    monkeypatch.setattr(targeted_asr, 'ffmpeg_audio', lambda *_args, **_kw: pytest.fail('extraction forbidden'))
    report = run()
    assert report['pending_reason'] == reason and calls == []
    assert report['manual_review']['budget']['asr_calls'] == 0
    assert report['alternatives'] == [] and report['audio_seconds'] == 0


def test_missing_source_does_not_consume_asr(tmp_path, monkeypatch):
    ctx, source, transcript, candidates, calls, run = setup_review(tmp_path, monkeypatch)
    source.unlink()
    assert run()['pending_reason'] == 'original_audio_unavailable'
    assert calls == []


def test_cache_invalidates_model_config_and_canonical_evidence(tmp_path, monkeypatch):
    ctx, source, transcript, candidates, calls, run = setup_review(tmp_path, monkeypatch)
    first = run()
    second = run()
    assert len(calls) == 3 and second['cache_hits'] == 3
    assert second['manual_review']['budget']['asr_calls'] == 0
    ctx.config['transcription']['targeted_model_version'] = 'synthetic-v2'
    assert run()['cache_hits'] == 0 and len(calls) == 6
    transcript['words'][0]['word'] = 'Outro original.'
    transcript['words'][0]['raw'] = 'Outro original.'
    third = run()
    assert third['cache_hits'] == 0 and len(calls) == 9
    assert any(r['selected_text'] == 'Outro original.' for r in third['alternatives'])
    source.write_bytes(b'CHANGED FAKE')
    assert run()['pending_reason'] == 'source_sha256_mismatch' and len(calls) == 9


def test_zero_budget_and_noise_discrepancy_are_reviewable(tmp_path, monkeypatch):
    ctx, source, transcript, candidates, calls, run = setup_review(tmp_path, monkeypatch,
                                                               targeted_max_regions=0)
    assert run()['status'] == 'pending' and calls == []
    ctx.config['transcription'].update(targeted_max_regions=4, targeted_max_audio_seconds=20)
    transcript['words'][0].update(needs_review=False, speech_overlap=False, asr_discrepancy=True)
    report = run(events=[{'kind': 'noise', 'start': 17, 'end': 18}])
    assert {w['priority_reason'] for w in report['windows']} == {
        'SHORTLIST_HOOK', 'SHORTLIST_PAYOFF', 'CANDIDATE_HOOK', 'NOISE_REVIEW'}
    assert all(10 <= w['start'] < w['end'] <= 20 for w in report['windows'])
    assert any('asr_discrepancy' in r['reasons'] for r in report['manual_review']['windows'])


def test_export_json_audio_interval_hash_and_no_forged_manual_review(tmp_path, monkeypatch):
    ctx, source, transcript, candidates, calls, run = setup_review(tmp_path, monkeypatch)
    targeted = run()
    dossier = review_selected_clips(transcript['words'], candidates, ['QUEUED'],
        alternatives=targeted['alternatives'], targeted_report=targeted)
    kit = tmp_path/'kit'
    write_review_kit(kit, dossier)
    manual = read_json(kit/'targeted_manual_review.json')
    assert manual['windows'] == targeted['manual_review']['windows']
    assert manual['windows'][0]['audio_sha256'] == file_hash(source)
    assert manual['source_report_sha256'] == file_hash(kit/'subtitle_review_s7.json')
    assert dossier['candidates']['QUEUED']['verified_by_audio'] is None
    with pytest.raises(ValueError):
        apply_human_subtitle_review(kit, kit/'subtitle_human_review.csv', tmp_path/'approved')
    assert not (tmp_path/'approved').exists()


def test_review_states_are_separate_and_hash_approval_expires(tmp_path):
    dossier = review_selected_clips([{'word': 'Olá, né?', 'start': 1, 'end': 2, 'confidence': .99}],
        [{'candidate_id': 'CUT', 'start': 0, 'end': 3}], ['CUT'])
    kit, out = tmp_path/'kit', tmp_path/'reviewed'
    write_review_kit(kit, dossier)
    csv_path = kit/'subtitle_human_review.csv'
    with csv_path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    rows[0].update(verified_text='Olá, né?', verified_start='1', verified_end='2',
                   reviewer='SYNTHETIC reviewer', audio_listened='YES', decision='APPROVED')
    with csv_path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    apply_human_subtitle_review(kit, csv_path, out)
    provenance = read_json(out/'REVIEW_PROVENANCE.json')
    assert provenance['verified_by_audio'] is True and not provenance['correction_approved']
    approval = approve_reviewed_subtitles(out, 'CUT', expected_sha256=file_hash(out/'CUT.human_reviewed.srt'),
        reviewer='SYNTHETIC reviewer', audio_listened=True)
    assert approval['correction_approved'] and not approval['subtitle_publish_ready']
    assert subtitle_finalization_gate(out, 'CUT')['correction_approved']
    (out/'CUT.human_reviewed.srt').write_text('changed', encoding='utf-8')
    assert subtitle_finalization_gate(out, 'CUT')['verified_by_audio'] is None
    assert not subtitle_finalization_gate(out, 'CUT')['correction_approved']


def test_prior_discrepancies_preserved_without_automatic_correction(tmp_path, monkeypatch):
    ctx, source, transcript, candidates, calls, run = setup_review(tmp_path, monkeypatch,
        targeted_max_regions=3, targeted_max_audio_seconds=20)
    transcript['words'][0].update(needs_review=False, speech_overlap=False)
    prior = {'start': 13, 'end': 16, 'selected_text': 'Original, né?',
             'alternatives': [{'text': 'Outro, né?', 'source': 'synthetic_multipass'}],
             'replacement_applied': False}
    transcript['transcription_alternatives'] = [prior]
    before = deepcopy(transcript)
    report = run()
    assert len(calls) == 3
    assert 'ASR_DISCREPANCY' in {w['priority_reason'] for w in report['windows']}
    assert any(r['prior_alternatives'] == [prior] for r in report['manual_review']['windows'])
    assert transcript == before and not report['original_audio_verified']


def test_outer_cache_source_fingerprint_and_default_opt_in(tmp_path, monkeypatch):
    from ldporto.targeted_asr import on_demand_source_fingerprint
    assert load_config()['transcription']['targeted_review_opt_in'] is False
    ctx, source, transcript, candidates, calls, run = setup_review(tmp_path, monkeypatch)
    before = on_demand_source_fingerprint(ctx.config, {'mono': str(source)})
    source.write_bytes(b'CHANGED')
    assert on_demand_source_fingerprint(ctx.config, {'mono': str(source)}) != before
    ctx.config['transcription']['targeted_review_opt_in'] = False
    assert on_demand_source_fingerprint(ctx.config, {'mono': str(source)}) is None
