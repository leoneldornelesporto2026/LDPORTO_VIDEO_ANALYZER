from ldporto.targeted_asr import select_repair_windows, run_targeted_repair
from ldporto.config import load_config
from ldporto.core import Context
import logging
import numpy as np
import soundfile as sf


def test_payoff_and_hook_win_budget_over_early_low_priority_words():
    words = [{'word_id': f'W{i}', 'word': 'duvidosa', 'start': t, 'end': t + .3, 'needs_review': True} for i, t in enumerate([1, 10, 50, 100])]
    candidates = [{'moment_id': 'M', 'ideal_start': 50, 'ideal_end': 110, 'editorial_score': .95, 'default_shortlist_eligible': True}]
    arcs = [{'payoff': {'start': 99, 'end': 105, 'segment_ids': ['S1']}}]
    rows = select_repair_windows(words, candidates, arcs, [], 120, max_regions=2, max_audio_seconds=20)
    assert rows[0]['priority_reason'] == 'STORY_PAYOFF'
    assert rows[1]['priority_reason'] == 'CANDIDATE_HOOK'
    assert sum(r['end'] - r['start'] for r in rows) <= 20


def test_short_real_audio_extraction_is_cached_and_never_replaces_raw(tmp_path):
    cfg = load_config()
    ctx = Context(tmp_path / 'source.mp4', tmp_path / 'output', cfg, 'HASH', logging.getLogger('targeted-asr'))
    wav = tmp_path / 'short.wav'
    sf.write(wav, np.zeros(16000 * 4), 16000)
    words = [{'word_id': 'W', 'word': 'duvidosa', 'start': 1, 'end': 2, 'needs_review': True, 'confidence': .3}]
    transcript = {'words': words, 'segments': []}
    calls = []
    def recognize(path, offset):
        audio, rate = sf.read(path)
        assert rate == 16000 and len(audio) <= 64000
        calls.append(offset)
        return {'words': [{'word': 'alternativa', 'start': offset, 'end': offset + 1, 'confidence': .9}]}
    first = run_targeted_repair(ctx, {'mono': str(wav)}, transcript, [], [], [], 4, recognize=recognize)
    second = run_targeted_repair(ctx, {'mono': str(wav)}, transcript, [], [], [], 4, recognize=recognize)
    assert len(calls) == 1
    assert first['alternatives'][0]['replacement_applied'] is False
    assert second['cache_hits'] == 1
    assert words[0]['word'] == 'duvidosa'


def test_targeted_gpu_asr_releases_its_finished_local_llm_before_loading(tmp_path, monkeypatch):
    from ldporto import targeted_asr, ollama_local
    cfg = load_config()
    cfg['device'] = 'auto'
    cfg['semantic_analysis'].update(backend='ollama', ollama_url='http://localhost:11434')
    ctx = Context(tmp_path / 'source.mp4', tmp_path / 'output', cfg, 'HASH', logging.getLogger('targeted-asr'))
    wav = tmp_path / 'short.wav'
    sf.write(wav, np.zeros(16000 * 4), 16000)
    order = []
    def request(url, endpoint, payload=None, **kwargs):
        assert endpoint == '/api/generate'
        assert payload['model'] == cfg['semantic_analysis']['model']
        assert payload['keep_alive'] == 0 and payload['prompt'] == ''
        order.append('release')
        return {'done': True}
    monkeypatch.setattr(ollama_local, '_request_json', request)
    class Engine:
        model = None
        def __init__(self, ctx):
            pass
        def _load(self):
            order.append('load_asr')
        def recognize(self, path, offset):
            return {'words': []}
    monkeypatch.setattr(targeted_asr, 'TranscriptionEngine', Engine)
    transcript = {'words': [{'word': 'dúvida', 'start': 1, 'end': 2, 'needs_review': True}]}
    run_targeted_repair(ctx, {'mono': str(wav)}, transcript, [], [], [], 4)
    assert order == ['release', 'load_asr']
    run_targeted_repair(ctx, {'mono': str(wav)}, transcript, [], [], [], 4)
    assert order == ['release', 'load_asr']
