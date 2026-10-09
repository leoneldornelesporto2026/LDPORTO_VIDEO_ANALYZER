"""Offline synthetic fixtures; no ASR, vision or live Ollama calls."""
from copy import deepcopy
import json

import pytest

from ldporto import semantic
from ldporto.understanding import build_main_moments, build_story_arcs
from test_v42_editorial import model_fixture, semantic_context


@pytest.mark.parametrize('failure', ['invalid_json', 'failed_repair', 'partial_json'])
def test_chunk_failure_keeps_healthy_candidates_and_source_caches(tmp_path, monkeypatch, failure):
    ctx, transcript = semantic_context(tmp_path, monkeypatch)
    ctx.config['semantic_analysis']['chunk_seconds'] = 30
    transcript['segments'] = [
        {'segment_id': 'S', 'start': 0, 'end': 10, 'speaker': 'A',
         'text': 'Como foi feita a gravacao?'},
        {'segment_id': 'S2', 'start': 10, 'end': 20, 'speaker': 'B',
         'text': 'A gravacao foi feita no estudio com instrumentos.'},
        {'segment_id': 'S2b', 'start': 20, 'end': 30, 'speaker': 'B',
         'text': 'Os instrumentos foram gravados juntos no estudio.'},
        {'segment_id': 'S3', 'start': 40, 'end': 50, 'speaker': 'A',
         'text': 'A carreira musical mudou com a gravacao.'},
    ]
    raw = tmp_path / 'raw_transcript.json'
    raw.write_text(json.dumps(transcript, ensure_ascii=False), encoding='utf-8')
    vision = ctx.cache / 'vision' / 'synthetic.json'
    vision.parent.mkdir(parents=True, exist_ok=True)
    vision.write_bytes(b'{"frames":[],"observed":null}')
    before = deepcopy(transcript), raw.read_bytes(), vision.read_bytes()
    calls = []

    def call(cfg, group):
        calls.append(group[0]['segment_id'])
        data = model_fixture()
        for key in ('topics', 'moments'):
            data[key][0]['segment_ids'] = [s['segment_id'] for s in group]
        if group[0]['segment_id'] == 'S':
            if failure == 'invalid_json':
                raise json.JSONDecodeError('synthetic invalid JSON', '{', 1)
            data['topics'] = [None, {'segment_ids': ['ABSENT']}]
            if failure == 'partial_json':
                data['moments'].extend([None, [], 'invalid row'])
        return data, {}

    def repair(*args):
        # Replaces initial evidence with a worse reply before grounding fails.
        return {'locale': 'pt-BR', 'topics': [], 'moments': []}, {}

    monkeypatch.setattr(semantic, 'call_ollama', call)
    monkeypatch.setattr(semantic, 'repair_ollama_output', repair)
    envelope = semantic.SemanticEngine().run(ctx, transcript)
    data = envelope['data']
    assert envelope['status'] == 'partial'
    healthy = next(m for m in data['moments'] if m['evidence_segment_ids'] == ['S3'])
    assert healthy['moment_id'] == 'MOMENT_00001_0000'
    assert not healthy.get('degraded_reason')
    assert calls == ['S', 'S3']
    if failure != 'invalid_json':
        preserved = next(m for m in data['moments'] if m['method'] == 'ollama' and 'S' in m['evidence_segment_ids'])
        assert preserved['text'] == ' '.join(s['text'] for s in transcript['segments'][:3])
        assert preserved['degraded_reason']
        assert all(v is None for v in preserved['editorial'].values())
    assert all(t.get('degraded_reason') for t in data['topics'] if 'S' in t['evidence_segment_ids'])
    assert all(not t.get('degraded_reason') for t in data['topics'] if 'S3' in t['evidence_segment_ids'])
    assert data['questions_answers'][0]['degraded_reason']
    arcs = build_story_arcs(transcript, data['topics'], data['questions_answers'])
    assert arcs and all(a.get('degraded_reason') for a in arcs)
    candidates = build_main_moments(transcript, data['topics'], data['moments'], data['questions_answers'], arcs, [])
    assert any(c.get('degraded_reason') for c in candidates)
    assert any('S3' in c['core_evidence_segment_ids'] and not c.get('degraded_reason') for c in candidates)
    assert before == (transcript, raw.read_bytes(), vision.read_bytes())
    # Healthy cache is reused even while the failed chunk is retried.
    again = semantic.SemanticEngine().run(ctx, transcript)['data']
    assert calls == ['S', 'S3', 'S']
    assert again['semantic_chunk_profile'][1]['cache_hit']
    assert before == (transcript, raw.read_bytes(), vision.read_bytes())


def test_recovery_deterministic_and_rejects_ungrounded_components():
    group = [{'segment_id': 'S', 'start': 0, 'end': 10, 'speaker': None,
              'text': 'A gravacao foi feita no estudio.'}]
    initial = model_fixture()
    initial['topics'].extend([None, {'segment_ids': ['ABSENT']}])
    initial['moments'].extend([None, [], {'segment_ids': ['ABSENT']}])
    repair = {'locale': 'pt-BR', 'topics': [], 'moments': []}
    originals = deepcopy([initial, repair, group])
    first = semantic.recover_semantic_evidence([initial, repair], group, 0)
    assert first == semantic.recover_semantic_evidence([initial, repair], group, 0)
    assert first[1]['preserved_moment_count'] == 1
    assert first[1]['preserved_topic_count'] == 1
    assert [initial, repair, group] == originals


@pytest.mark.parametrize('missing', ['topics', 'moments'])
def test_partial_collection_repairs_only_missing_evidence(monkeypatch, missing):
    from ldporto.config import load_config
    group = [{'segment_id': 'S', 'start': 0, 'end': 10, 'speaker': None,
              'text': 'A gravacao foi feita no estudio.'}]
    initial = model_fixture()
    initial.pop(missing)
    before = deepcopy(initial)
    reply = model_fixture()
    reply['moments'][0]['reason'] = 'Uma alteracao indevida no candidato anterior.'
    reply['topics'][0]['summary'] = 'Uma alteracao indevida no topico anterior.'
    monkeypatch.setattr(semantic, 'ollama_chat', lambda *args: (reply, {}))
    result, meta = semantic.repair_ollama_output(load_config()['semantic_analysis'], group, initial, ValueError('partial JSON'))
    sibling = 'moments' if missing == 'topics' else 'topics'
    assert result[sibling] == before[sibling]
    assert meta['preserved_item_count'] == 1
    assert initial == before
    assert semantic.ground_model_output(result, group, 0)
