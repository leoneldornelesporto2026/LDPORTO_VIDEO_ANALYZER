"""R4: contract closure, social gates and read-only legacy Curator bridge."""
from copy import deepcopy
import json
import zipfile
from pathlib import Path

import pytest

from ldporto.curator_bridge import audit_second_curation_package, export_legacy_curator_bridge
from ldporto.second_curation_export import (build_core_package, generate_visuals_on_demand,
                                            validate_core_package, _final_commercial_classification)
from test_v43_handoff import analysis_fixture


def _fake_contact_sheet(source, candidate, output, timeline=None):
    import cv2
    import numpy as np
    output.parent.mkdir(parents=True, exist_ok=True)
    ok, jpg = cv2.imencode('.jpg', np.full((64, 90, 3), 145, dtype=np.uint8))
    assert ok
    output.write_bytes(jpg.tobytes())
    return {'status': 'ok', 'frame_count': 6}


def _make_ready(tmp_path, monkeypatch):
    monkeypatch.setattr('ldporto.second_curation_export.build_contact_sheet', _fake_contact_sheet)
    analysis = analysis_fixture()
    analysis['metadata']['source'].update(id='r4_fixture', url='https://www.youtube.com/watch?v=r4_fixture')
    analysis['social_output'] = {'story_readiness': 'READY', 'stories': [
        {'story_id': 'STORY_001', 'candidate_id': 'M1', 'title': 'Carreira'}],
        'title_suggestions': [{'story_id': 'STORY_001', 'title': 'Carreira'}],
        'caption_style_recommendations': [{'story_id': 'STORY_001', 'preset': 'clean_bold'}]}
    result = build_core_package(analysis, source=tmp_path/'source.avi', output_dir=tmp_path/'packages')
    assert result['state'] == 'READY'
    return Path(result['path'])


def test_export_never_overwrites_propagated_commercial_block_exclusion():
    candidate = {'transcript_literal': 'Estávamos conversando sobre uma poltrona antiga.',
                 'segment_ids': ['S1'], 'commercial_classification': {
                     'content_type': 'advertisement', 'commercial_score': 0.92, 'eligibility': 'excluded',
                     'block_propagated': True}}
    result = _final_commercial_classification(candidate)
    assert result['eligibility'] == 'excluded' and result['block_propagated']
    assert result['export_reclassification'] == 'upstream_exclusion_preserved'


def test_export_rechecks_stories_after_final_commercial_gate(tmp_path, monkeypatch):
    monkeypatch.setattr('ldporto.second_curation_export.build_contact_sheet', _fake_contact_sheet)
    analysis = analysis_fixture()
    second = deepcopy(analysis['main_moments'][0])
    second['moment_id'] = 'AD'
    second['ideal_start'] = 0
    second['ideal_end'] = 30
    second['commercial_classification'] = {'content_type': 'advertisement', 'commercial_score': .9,
                                           'eligibility': 'excluded', 'block_propagated': True}
    analysis['main_moments'].append(second)
    analysis['editorial_shortlist'].append('AD')
    analysis['social_output'] = {'story_readiness': 'READY', 'stories': [
        {'story_id': 'STORY_001', 'candidate_id': 'M1'},
        {'story_id': 'STORY_002', 'candidate_id': 'AD'}],
        'title_suggestions': [{'story_id': 'STORY_001'}, {'story_id': 'STORY_002'}],
        'caption_style_recommendations': [{'story_id': 'STORY_001'}, {'story_id': 'STORY_002'}]}
    result = build_core_package(analysis, source=tmp_path/'source.avi', output_dir=tmp_path/'packages')
    assert validate_core_package(result['path'])['status'] == 'valid'
    with zipfile.ZipFile(result['path']) as z:
        catalog = {r['candidate_id']: r for r in json.loads(z.read('editorial/candidate_catalog.json'))['candidates']}
        stories = json.loads(z.read('social/stories_manifest.json'))
        shortlist = json.loads(z.read('editorial/default_shortlist.json'))['candidate_ids']
        assert catalog['AD']['commercial_classification']['eligibility'] == 'excluded'
        assert not catalog['AD']['default_shortlist_eligible']
        assert shortlist == ['M1']
        assert [r['candidate_id'] for r in stories['stories']] == ['M1']
        assert stories['story_readiness'] == 'REVIEW_REQUIRED'
        assert stories['publication_ready'] is False
        assert len(stories['removed_stories_by_final_gate']) == 1
        assert len(stories['title_suggestions']) == 1


def test_bridge_rejects_partial_and_does_not_create_folder(tmp_path):
    result = build_core_package(analysis_fixture(), output_dir=tmp_path/'packages')
    audit = audit_second_curation_package(result['path'])
    assert not audit['bridge_possible'] and 'visual_ready_false' in audit['blockers']
    with pytest.raises(ValueError, match='bridge blocked'):
        export_legacy_curator_bridge(result['path'], tmp_path/'out')
    assert not list((tmp_path/'out').glob('*'))


def test_ready_curator_bridge_emits_compatible_legacy_contract(tmp_path, monkeypatch):
    src = _make_ready(tmp_path, monkeypatch)
    audit = audit_second_curation_package(src)
    assert audit['bridge_possible'] and audit['publication_ready'] is False
    result = export_legacy_curator_bridge(src, tmp_path/'legacy')
    directory = Path(result['path'])
    analysis = json.loads((directory/'analysis.json').read_text(encoding='utf-8'))
    assert analysis['metadata']['source']['id'] == 'r4_fixture'
    assert analysis['curator_bridge']['publication_ready'] is False
    assert len(json.loads((directory/'editorial_moments.json').read_text())) == 1
    assert len(json.loads((directory/'caption_segments.json').read_text())) == 3
    assert not json.loads((directory/'people_observations.json').read_text())
    assert json.loads((directory/'BRIDGE_PROVENANCE.json').read_text())['final_render_validated'] is False
    with pytest.raises(FileExistsError):
        export_legacy_curator_bridge(src, tmp_path/'legacy')


def test_on_demand_visuals_recomputes_consistent_readiness(tmp_path, monkeypatch):
    from ldporto.core import file_hash
    source = tmp_path/'source_video.mp4'
    source.write_bytes(b'mock video source checksum only')
    analysis = analysis_fixture()
    analysis['metadata']['sha256'] = file_hash(source)
    partial = build_core_package(analysis, output_dir=tmp_path/'package')
    assert partial['state'] == 'PARTIAL'
    monkeypatch.setattr('ldporto.second_curation_export.build_contact_sheet', _fake_contact_sheet)
    visualized = generate_visuals_on_demand(partial['path'], source, ['M1'], tmp_path/'visuals')
    assert validate_core_package(visualized['path'])['status'] == 'valid'
    with zipfile.ZipFile(visualized['path']) as z:
        manifest = json.loads(z.read('SECOND_CURATION_MANIFEST.json'))
        index = json.loads(z.read('CURATION_INDEX.json'))
        brief = json.loads(z.read('SECOND_CURATOR_BRIEF.json'))
        assert manifest['readiness']['visual_ready'] is True
        assert index['second_curation_readiness'] == manifest['readiness'] == brief['capabilities']
        assert audit_second_curation_package(visualized['path'])['bridge_possible']
