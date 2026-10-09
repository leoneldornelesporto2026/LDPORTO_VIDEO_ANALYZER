"""Offline causal replay fixtures; no model, media or approval evidence."""
import pytest

from ldporto.config import load_config
from ldporto.core import file_hash, read_json, write_json
from ldporto import replay
from ldporto.run_status import DEPENDENCIES, descendants
from test_v43_runtime import replay_fixture


def test_replay_hits_and_selectively_invalidates(tmp_path, monkeypatch):
    folder = replay_fixture(tmp_path)
    cfg = load_config()
    cfg['camera_director']['enabled'] = False
    cfg['preview']['enabled'] = False
    # Exercise the real replay and Context cache, suppress package writing only.
    monkeypatch.setattr(replay.ReportEngine, 'run', lambda *args: None)
    def forbidden(*args, **kwargs):
        raise AssertionError('heavy inference requested by ranking replay')
    monkeypatch.setattr(replay.SemanticEngine, 'run', forbidden)
    from ldporto.transcription import TranscriptionEngine
    from ldporto.vision import VisionEngine
    monkeypatch.setattr(TranscriptionEngine, 'run', forbidden)
    monkeypatch.setattr(VisionEngine, 'run', forbidden)
    original = replay.run_understanding
    calls = []
    def counted(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(replay, 'run_understanding', counted)
    output = tmp_path / 'replayed'
    def run():
        return replay.replay_analysis(folder, cfg, 'ranking', output)[1]
    first = run()
    assert len(calls) == 1
    second = run()
    assert second['stage_runtime']['16_understanding']['cache_hit']
    assert len(calls) == 1

    def replace(name, data):
        write_json(folder / name, data)
        manifest = read_json(folder / 'manifest.json')
        manifest['artifact_checksums'][name] = file_hash(folder / name)
        write_json(folder / 'manifest.json', manifest)

    # A verified preview diagnostic is exported but isn't editorial input.
    replace('analysis_quality.json', {'preview_technical_verified': False})
    third = run()
    assert third['stage_runtime']['16_understanding']['cache_hit']
    assert len(calls) == 1
    assert third['replay_provenance']['source_artifact_checksums'] != first['replay_provenance']['source_artifact_checksums']

    cfg['understanding']['min_editorial_score'] = .99
    ranked = run()
    assert len(calls) == 2
    assert not ranked['stage_runtime']['16_understanding']['cache_hit']
    assert not ranked['replay_provenance']['asr_rerun']
    assert not ranked['replay_provenance']['vision_rerun']
    assert not ranked['replay_provenance']['llm_rerun']
    assert run()['stage_runtime']['16_understanding']['cache_hit']

    moments = read_json(folder / 'editorial_moments.json')
    moments[0]['editorial']['clarity'] = .1
    replace('editorial_moments.json', moments)
    assert not run()['stage_runtime']['16_understanding']['cache_hit']
    assert len(calls) == 3

    # A real ranking implementation fingerprint change must reach its owner.
    from ldporto import core
    actual_hash = core.file_hash
    monkeypatch.setattr(core, 'file_hash', lambda path: 'changed-fixture-code' if str(path).endswith('editorial_intelligence.py') else actual_hash(path))
    assert not run()['stage_runtime']['16_understanding']['cache_hit']
    assert len(calls) == 4

    # No relaxation of artifact integrity to obtain these hits.
    write_json(folder / 'editorial_moments.json', [])
    with pytest.raises(ValueError, match='checksum mismatch'):
        run()


def test_computed_inputs_are_part_of_editorial_key():
    args = [{}, {}, {}, {}, {}, {}, {'moments': []}, []]
    before = replay.understanding_replay_params(*args)
    args[6] = {'moments': [{'moment_id': 'synthetic'}]}
    assert replay.understanding_replay_params(*args) != before
    args[6] = {'moments': []}
    args[5] = {'mapping_summary': [{'person_id': None}]}
    assert replay.understanding_replay_params(*args) != before


def test_ranking_change_hits_asr_and_facial_caches(tmp_path):
    import logging
    from ldporto.core import Context, ok
    cfg = load_config()
    def context():
        return Context(tmp_path / 'absent.mp4', tmp_path, cfg, 'synthetic-source', logging.getLogger('stage05'))
    stages = ['04_transcription', '07_people_tracking', '08_person_reid', '15_semantic']
    first = context()
    expected = {'embedding': [1., 0.], 'person_id': None, 'fixture_only': True}
    for stage in stages:
        first.step(stage, {}, lambda: ok(expected), code_files=['config.py'])
    first.step('16_understanding', {'ranking': 'old'}, lambda: ok({'rank': 1}), code_files=['editorial_intelligence.py'])
    second = context()
    def forbidden():
        raise AssertionError('unrelated producer recomputed')
    for stage in stages:
        assert second.step(stage, {}, forbidden, code_files=['config.py']) == expected
        assert second.stage_metrics[stage]['cache_hit']
        assert second.states[stage]['key'] == first.states[stage]['key']
    assert second.step('16_understanding', {'ranking': 'new'}, lambda: ok({'rank': 2}), code_files=['editorial_intelligence.py']) == {'rank': 2}
    assert not second.stage_metrics['16_understanding']['cache_hit']


def test_graph_and_replay_scope_preserve_expensive_producers():
    affected = descendants('16_understanding')
    assert {'17b_broadcast_graphics', '17c_commercial_visual', '17d_targeted_asr',
            '17e_subtitle_review_s7', '19_camera_director', '21_second_curation_handoff'} <= set(affected)
    assert not {'04_transcription', '07_people_tracking', '08_person_reid', '15_semantic'} & set(affected)
    for stage in DEPENDENCIES:
        assert stage not in descendants(stage), 'dependency cycle'
    plan = replay.replay_plan('ranking')
    assert '15_semantic' not in plan['stages_to_check']
    assert plan['cache_hits'] is None and not plan['approval_inherited']
    assert '15_semantic' in replay.replay_plan('semantic')['stages_to_check']
    assert '16_understanding' not in replay.replay_plan('handoff')['stages_to_check']
    with pytest.raises(ValueError):
        replay.replay_plan('invalid')
