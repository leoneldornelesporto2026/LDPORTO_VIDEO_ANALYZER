from copy import deepcopy
import json
from ldporto import semantic
from ldporto.config import load_config
from ldporto.understanding import build_story_arcs


def test_bad_range_does_not_send_valid_component_for_repair(monkeypatch):
    from test_v42_editorial import model_fixture
    group = [{'segment_id': 'S', 'start': 0, 'end': 10, 'text': 'Uma explicação sobre gravação.', 'speaker': 'A'}]
    data = model_fixture()
    for key in ('topics', 'moments'):
        for row in data[key]:
            row.pop('segment_ids')
            row.update(start_segment_id='S', end_segment_id='S')
    data['moments'][0]['end_segment_id'] = 'ABSENT'
    calls = []
    def chat(*args):
        payload = json.loads(args[2][-1]['content'])
        calls.append(payload)
        return {'locale': 'pt-BR', 'topics': [], 'moments': model_fixture()['moments']}, {}
    monkeypatch.setattr(semantic, 'ollama_chat', chat)
    repaired, meta = semantic.repair_ollama_output(load_config()['semantic_analysis'], group, data, ValueError('range'))
    assert calls[0]['invalid_output']['topics'] == []
    assert repaired['topics'][0]['segment_ids'] == ['S']
    assert meta['preserved_item_count'] == 1
    assert semantic.ground_model_output(repaired, group, 0)


def test_story_resumes_across_topic_and_brief_interruption_without_inventing_payoff():
    segments = [
        {'segment_id': 'S1', 'start': 0, 'end': 12, 'speaker': 'A', 'text': 'Quando me chamaram, eu subi no palco para dar a palestra.'},
        {'segment_id': 'S2', 'start': 12, 'end': 24, 'speaker': 'A', 'text': 'Eu só tinha duas alternativas, ou saía correndo ou morria atirando. Não tenho saída.'},
        {'segment_id': 'S3', 'start': 24, 'end': 26, 'speaker': 'B', 'text': 'Nossa!'},
        {'segment_id': 'S4', 'start': 26, 'end': 40, 'speaker': 'A', 'text': 'Eu continuei a palestra e falei tudo.'},
        {'segment_id': 'S5', 'start': 40, 'end': 52, 'speaker': 'A', 'text': 'Quando terminou, os oito mil de pé aplaudindo.'},
    ]
    topics = [{'topic_id': 'T1', 'start': 0, 'end': 26, 'topic': 'O medo', 'summary': '', 'evidence_segment_ids': ['S1', 'S2', 'S3']},
              {'topic_id': 'T2', 'start': 26, 'end': 52, 'topic': 'A palestra', 'summary': '', 'evidence_segment_ids': ['S4', 'S5']}]
    arcs = build_story_arcs({'segments': segments}, topics)
    complete = [a for a in arcs if a['kind'] == 'complete_story']
    assert complete
    arc = complete[0]
    assert arc['payoff']['text'] == segments[-1]['text']
    assert arc['payoff']['segment_ids'] == ['S5']
    assert set(arc['topic_ids']) == {'T1', 'T2'}
    assert arc['interruption_segment_ids'] == ['S3']
    assert not any(a['kind'] == 'complete_story' for a in build_story_arcs({'segments': segments[:-1]}, topics))


def test_generic_discussion_does_not_become_story():
    segments = [{'segment_id': f'S{i}', 'start': i * 10, 'end': (i + 1) * 10, 'speaker': 'A', 'text': text}
                for i, text in enumerate(['Quando o preço sobe, o mercado responde.', 'Mas o resultado é variável.', 'No fim é uma questão econômica.'])]
    arcs = build_story_arcs({'segments': segments}, [])
    assert not any(a['kind'] == 'complete_story' for a in arcs)


def test_failed_repair_preserves_valid_semantic_moment(tmp_path, monkeypatch):
    from test_v42_editorial import semantic_context, model_fixture
    ctx, transcript = semantic_context(tmp_path, monkeypatch)
    data = model_fixture()
    data['topics'][0]['segment_ids'] = ['ABSENT']
    monkeypatch.setattr(semantic, 'call_ollama', lambda *args: (deepcopy(data), {}))
    def fail(*args):
        raise ValueError('targeted repair failed')
    monkeypatch.setattr(semantic, 'repair_ollama_output', fail)
    result = semantic.SemanticEngine().run(ctx, transcript)['data']
    assert any(row['method'] == 'ollama' for row in result['moments'])
    assert result['semantic_chunk_profile'][0]['preserved_moment_count'] == 1
    assert result['semantic_metrics']['semantic_fallback_ratio'] == 1


def test_coverage_gap_repairs_only_gap_preserving_valid_topics(monkeypatch):
    from test_v42_editorial import model_fixture
    group = [{'segment_id': f'S{i}', 'start': i * 10, 'end': (i + 1) * 10, 'text': 'Uma explicação de gravação.', 'speaker': 'A'} for i in range(3)]
    topic = model_fixture()['topics'][0]
    first, last = {**topic, 'segment_ids': ['S0']}, {**topic, 'segment_ids': ['S2']}
    data = {'locale': 'pt-BR', 'topics': [first, last], 'moments': []}
    calls = []
    def chat(*args):
        calls.append(json.loads(args[2][-1]['content']))
        return {'locale': 'pt-BR', 'topics': [{**topic, 'segment_ids': ['S1']}], 'moments': []}, {}
    monkeypatch.setattr(semantic, 'ollama_chat', chat)
    result, meta = semantic.repair_ollama_output(load_config()['semantic_analysis'], group, data, ValueError('coverage'))
    assert result['topics'] == [first, {**topic, 'segment_ids': ['S1']}, last]
    assert len(calls[0]['invalid_output']['topics']) == 1
    assert meta['preserved_item_count'] == 2
    assert semantic.ground_model_output(result, group, 0)
