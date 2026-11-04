"""Compact PDF atlas contracts from explicitly synthetic source/indexed pixels."""
from copy import deepcopy
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from ldporto.compact_atlas import build_compact_atlas
from ldporto.core import file_hash
from test_r6_project_export import _pdf_text


SOURCE_HASH = 'a' * 64


def atlas_fixture(tmp_path):
    def write(reference, value):
        path = tmp_path / reference
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    def jpeg(reference, tone):
        path = tmp_path / reference
        path.parent.mkdir(parents=True, exist_ok=True)
        image = np.full((90, 160, 3), tone, dtype=np.uint8)
        cv2.rectangle(image, (40, 10), (100, 75), (90, 180, 220), -1)
        got, encoded = cv2.imencode('.jpg', image)
        assert got
        encoded.tofile(str(path))
        return {'path': reference, 'sha256': file_hash(path), 'width': 160, 'height': 90}
    f1 = {'frame_id': 'FRAME_FIXTURE_01', 'source_time_s': 1., 'source_sha256': SOURCE_HASH,
          **jpeg('06_VISUAL_ATLAS/frames/f1.jpg', 30)}
    f2 = {'frame_id': 'FRAME_FIXTURE_02', 'source_time_s': 7., 'source_sha256': SOURCE_HASH,
          **jpeg('06_VISUAL_ATLAS/frames/f2.jpg', 60)}
    sheet = {'sheet_id': 'SHEET_SYNTHETIC_01', 'frame_ids': [f1['frame_id'], f2['frame_id']],
        'scene_ids': ['SCENE_SYNTHETIC_01', 'SCENE_SYNTHETIC_02'],
        **jpeg('06_VISUAL_ATLAS/contact_sheets/s1.jpg', 80)}
    segments = [{'segment_id': 'SEG_FIXTURE_01', 'start': 0., 'end': 4., 'text': 'Ação canônica disponível na fixture.'},
                {'segment_id': 'SEG_FIXTURE_02', 'start': 6., 'end': 9., 'text': 'Outra frase literal, sem inferência.'}]
    write('02_TRANSCRIPT/transcript_segments.json', {'segments': segments})
    scenes = [{'scene_id': 'SCENE_SYNTHETIC_01', 'start': 0., 'end': 5., 'shot_type': 'UNKNOWN',
        'person_ids': ['PERSON_ANONYMOUS'], 'frame_ids': [f1['frame_id']], 'geometry_state': 'OBSERVED', 'missing_evidence': ['instrument_geometry_unknown']},
        {'scene_id': 'SCENE_SYNTHETIC_02', 'start': 5., 'end': 10., 'shot_type': 'UNKNOWN',
        'person_ids': [], 'frame_ids': [f2['frame_id']], 'geometry_state': 'UNKNOWN'},
        {'scene_id': 'SCENE_SYNTHETIC_03_NO_IMAGE', 'start': 10., 'end': 12., 'shot_type': 'UNKNOWN',
         'person_ids': [], 'frame_ids': [], 'geometry_state': 'UNKNOWN'}]
    def piece(ident, kind):
        prefix = ('04_REELS/' if kind == 'REEL' else '05_STORIES/') + ident + '/'
        write(prefix + 'editorial.json', {'summary': None, 'hook': None, 'title_proposals': [],
            'original_scores': {'fixture_score': None}, 'review_status': 'PARTIAL_STORY'})
        write(prefix + 'visual_storyboard.json', {'beats': [{'observed_action': None}]})
        write(prefix + 'camera_geometry.json', {'geometry_state': 'UNKNOWN', 'missing_evidence': ['head_extent_unknown']})
        write(prefix + 'caption_evidence.json', {'status': 'ALIGNMENT_REVIEW_REQUIRED'})
        return {('candidate_id' if kind == 'REEL' else 'story_id'): ident,
            'source_intervals': [{'start': 0., 'end': 9.}], 'rank_original': 1,
            'editorial_ref': prefix + 'editorial.json', 'visual_storyboard_ref': prefix + 'visual_storyboard.json',
            'camera_geometry_ref': prefix + 'camera_geometry.json', 'caption_evidence_ref': prefix + 'caption_evidence.json',
            'frame_ids': [f1['frame_id'], f2['frame_id']], 'scene_ids': ['SCENE_SYNTHETIC_01', 'SCENE_SYNTHETIC_02'],
            'transcript_segment_ids': ['SEG_FIXTURE_01', 'SEG_FIXTURE_02']}
    reels, stories = [piece('REEL_FIXTURE_01', 'REEL')], [piece('STORY_FIXTURE_01', 'STORY')]
    stories[0]['series_ids'] = ['SERIES_FIXTURE_01']
    return {'root': tmp_path, 'metadata': {'sha256': SOURCE_HASH, 'duration': 12., 'width': 160, 'height': 90,
            'source': {'id': 'SYNTHETIC_SOURCE_ONLY', 'title': 'Atlas sintético de contrato'}},
        'scenes': scenes, 'reels': reels, 'stories': stories,
        'series': [{'series_id': 'SERIES_FIXTURE_01', 'title': None,
            'part_ids': ['STORY_FIXTURE_01'], 'continuity_status': 'CONTINUITY_UNVERIFIED'}],
        'atlas_index': {'frames': [f1, f2], 'contact_sheets': [sheet]},
        'coverage': {'scene_count': 3, 'scenes_with_frames': 2, 'continuous_visual_coverage': None},
        'limitations': {'instrument_geometry': 'UNKNOWN', 'identity_confirmed': False}, 'revision': 'SYNTHETIC_R63'}


def test_compact_atlas_is_searchable_preserves_all_ids_and_reuses_shared_bitmap(tmp_path):
    inputs = atlas_fixture(tmp_path)
    before = deepcopy({key: value for key, value in inputs.items() if key != 'root'})
    result = build_compact_atlas(**inputs)
    path = tmp_path / result['pdf_ref']
    data, text = path.read_bytes(), _pdf_text(path.read_bytes())
    assert result['searchable'] is True
    assert file_hash(path) == result['pdf_sha256']
    assert result['scene_count'] == 3 and result['reel_count'] == 1 and result['story_count'] == 1
    for ident in ('SCENE_SYNTHETIC_01', 'SCENE_SYNTHETIC_02', 'SCENE_SYNTHETIC_03_NO_IMAGE',
                  'REEL_FIXTURE_01', 'STORY_FIXTURE_01', 'SERIES_FIXTURE_01', SOURCE_HASH):
        assert ident in text
    assert 'Ação canônica disponível na fixture.' in text
    assert 'Outra frase literal, sem inferência.' in text
    assert 'CONTINUITY_UNVERIFIED' in text and 'ALIGNMENT_REVIEW_REQUIRED' in text
    assert result['scenes_without_frames'] == ['SCENE_SYNTHETIC_03_NO_IMAGE']
    # One shared contact sheet appears globally and for both pieces, with one
    # actual bitmap object in the PDF and three references to that same object.
    assert result['unique_embedded_images'] == data.count(b'/Subtype /Image') == 1
    assert result['shared_image_reuses'] == 2
    assert data.count(b'/ToUnicode') >= 1 and b'/Outlines' in data
    assert result['editorial_state'] == 'PARTIAL'
    assert result['preview_approved'] is result['publication_ready'] is False
    assert {key: value for key, value in inputs.items() if key != 'root'} == before


def test_missing_refs_are_explicit_and_never_create_frames_or_text(tmp_path):
    inputs = atlas_fixture(tmp_path)
    inputs['reels'][0]['frame_ids'] = ['FRAME_NOT_AVAILABLE']
    inputs['reels'][0]['transcript_segment_ids'] = ['SEG_NOT_AVAILABLE']
    inputs['series'][0]['part_ids'].append('STORY_NOT_AVAILABLE')
    result = build_compact_atlas(**inputs)
    text = _pdf_text((tmp_path / result['pdf_ref']).read_bytes())
    assert result['missing_frame_references'] == [{'owner_id': 'REEL_FIXTURE_01', 'frame_id': 'FRAME_NOT_AVAILABLE'}]
    assert result['missing_transcript_references'] == [{'owner_id': 'REEL_FIXTURE_01', 'segment_id': 'SEG_NOT_AVAILABLE'}]
    assert result['missing_story_references'] == [{'series_id': 'SERIES_FIXTURE_01', 'story_id': 'STORY_NOT_AVAILABLE'}]
    assert 'SEM IMAGEM ASSOCIADA' in text and 'referência sem segmento disponível.' in text


@pytest.mark.parametrize('kind', ['foreign_source', 'bad_hash', 'unsafe_path', 'bad_time'])
def test_atlas_rejects_foreign_or_modified_assets_and_invalid_times(tmp_path, kind):
    inputs = atlas_fixture(tmp_path)
    frame = inputs['atlas_index']['frames'][0]
    if kind == 'foreign_source':
        frame['source_sha256'] = 'b' * 64
    elif kind == 'bad_hash':
        frame['sha256'] = 'b' * 64
    elif kind == 'unsafe_path':
        frame['path'] = '../outside.jpg'
    else:
        frame['source_time_s'] = 12.
    with pytest.raises(ValueError):
        build_compact_atlas(**inputs)
    assert not (tmp_path / '08_REPORTS/VISUAL_ATLAS.pdf').exists()


def test_atlas_does_not_overwrite_an_existing_revision(tmp_path):
    inputs = atlas_fixture(tmp_path)
    first = build_compact_atlas(**inputs)
    with pytest.raises(FileExistsError):
        build_compact_atlas(**inputs)
    assert file_hash(tmp_path / first['pdf_ref']) == first['pdf_sha256']


def test_piece_presence_uses_interval_filtered_people_and_camera_proposals_are_labeled(tmp_path):
    inputs=atlas_fixture(tmp_path)
    inputs['scenes'][0]['person_ids']=['PERSON_ONLY_ELSEWHERE_IN_SCENE']
    inputs['reels'][0]['person_ids']=[]
    camera=tmp_path/inputs['reels'][0]['camera_geometry_ref']
    camera.write_text(json.dumps({'decision_ids':['D1'],'trajectory_ids':['T1'],
        'sufficiency':'NEEDS_SOURCE_INSPECTION'}),encoding='utf-8')
    decisions=tmp_path/'07_CAMERA/camera_decisions.json';decisions.parent.mkdir()
    decisions.write_text(json.dumps({'decisions':[{'decision_id':'D1','mode':'FOCUS_PERSON_9X16',
        'target_person_ids':['PROPOSED_ANONYMOUS_TARGET']}]}),encoding='utf-8')
    result=build_compact_atlas(**inputs)
    text=_pdf_text((tmp_path/result['pdf_ref']).read_bytes())
    reel=text.rsplit('Reel · REEL_FIXTURE_01',1)[1].split('Story · STORY_FIXTURE_01')[0]
    assert 'PERSON_ONLY_ELSEWHERE_IN_SCENE' not in reel
    assert 'FOCUS_PERSON_9X16' in reel and 'NEEDS_SOURCE_INSPECTION' in reel
    assert 'Alvos propostos, sem identidade nominal' in reel
