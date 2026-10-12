"""Synthetic offline fixtures, including actual short encoding; no human truth."""
from copy import deepcopy
import json
import shutil
import subprocess
import zipfile

import pytest

from ldporto.core import file_hash
from ldporto.curation_canary import viewport_audit, run_real_canary
from ldporto.second_curation_export import build_core_package, validate_core_package
from ldporto.preview_renderer import render_preview
from ldporto.preview_verifier import verify_preview
from ldporto.curator_delivery import overlay_ass, verify_mp4
from test_stage43_capability_contract import disabled_analysis, read


def geometry():
    return {'metadata': {'width': 320, 'height': 180},
        'camera_director_timeline': [dict(director_id='SYNTHETIC_D61', start=0, end=2, layout='single_person',
            crop={'rect_end': dict(x=.342, y=0, width=.316, height=1)})],
        'people_observations': [dict(time=t, head_bbox=dict(x=.44,y=.20,width=.12,height=.25),
            eyes_bbox=dict(x=.46,y=.28,width=.08,height=.02)) for t in (.1, .9, 1.8)],
        'commercial_visual_s8': {'texts': [dict(observed_at=.9,
            bbox=dict(x=.44,y=.55,width=.12,height=.04))]},
        'broadcast_graphics': {'intervals': [dict(start=0,end=2,regions=[dict(observed_at=.9,
            bbox=dict(x=.45,y=.65,width=.1,height=.04))])]}}


def test_temporal_crop_safe_head_chin_eyes_text_gc_and_caption_space():
    report = viewport_audit(geometry(), dict(start=0,end=2))
    assert report['reason_codes'] == []
    assert len(report['samples']) == 8
    assert all(s['inside_safe_area'] and not s['caption_conflict'] for s in report['samples'])
    assert report['source_dimensions'] == [320,180] and report['output_dimensions'] == [1080,1920]
    assert report['preview_approved'] is None and not report['publish_ready']


@pytest.mark.parametrize('kind,code', [('head','FACE_OR_HEAD_CLIPPED'), ('text','TEXT_OR_GC_CLIPPED')])
def test_projection_cannot_hide_cut_boxes(kind, code):
    data = geometry()
    if kind == 'head':
        data['people_observations'][0]['head_bbox']['x'] = .30
    else:
        data['commercial_visual_s8']['texts'][0]['bbox']['x'] = .30
    report = viewport_audit(data, dict(start=0,end=2))
    assert code in report['reason_codes']
    assert any(s['output_box']['x'] < 0 for s in report['samples'])
    if kind == 'head':
        assert report['preview_approved'] is False


def test_unknown_geometry_stays_unmeasured():
    report = viewport_audit({}, dict(start=0,end=2))
    assert 'HEAD_NOT_MEASURED' in report['reason_codes']
    assert report['safe_area_approved'] is None


@pytest.mark.parametrize('case,code', [('authorization','SHORT_MEDIA_AUTHORIZATION_REQUIRED'),
    ('missing','SOURCE_MEDIA_MISSING'), ('hash','SOURCE_HASH_MISMATCH'),
    ('long','SHORT_SOURCE_AND_10_TO_30_SECONDS_REQUIRED')])
def test_preconditions_never_create_mp4(tmp_path, case, code):
    source = tmp_path/'source.mp4'
    source.write_bytes(b'synthetic_not_media')
    data = dict(metadata=dict(sha256=file_hash(source),duration=31),
                main_moments=[dict(moment_id='M1',ideal_start=0,ideal_end=10)])
    if case == 'hash':
        data['metadata']['sha256'] = '0'*64
    result = run_real_canary(data, tmp_path/'absent' if case == 'missing' else source,
        'M1', tmp_path/'out', authorized=case != 'authorization')
    assert result['real_canary_status'] == 'real_canary_not_run'
    assert result['reason_codes'] == [code]
    assert not (tmp_path/'out').exists() and not result['human_approved']


def test_real_route_ocr_missing_and_ffmpeg_failure_are_not_pass(tmp_path, monkeypatch):
    import ldporto.curation_canary as canary
    import ldporto.curator_delivery as delivery
    source = tmp_path/'synthetic.mp4'
    source.write_bytes(b'fixture_no_real_decode')
    data = disabled_analysis()
    data['metadata'].update(sha256=file_hash(source),duration=10)
    data['main_moments'][0].update(ideal_start=0,ideal_end=10)
    data['transcript_segments'] = [dict(segment_id='S1',start=0,end=10,text='Uma historia completa.')]
    monkeypatch.setattr(delivery, 'probe', lambda p: dict(duration=10,width=320,height=180))
    monkeypatch.setattr(canary, 'targeted_ocr', lambda *a, **k: dict(status='unavailable',texts=[],reason='optional_tesseract_missing'))
    monkeypatch.setattr(canary, 'render_preview', lambda *a: dict(status='ok', data={}))
    monkeypatch.setattr(canary, 'find_media_tool', lambda name: 'fixture_ffmpeg')
    monkeypatch.setattr(canary.subprocess, 'run', lambda *a, **k: type('Proc', (), {'returncode': 1})())
    result = run_real_canary(data, source, 'M1', tmp_path/'out', authorized=True)
    assert result['commercial']['eligibility'] == 'review'
    assert result['real_canary_status'] == 'real_canary_fail'
    assert result['reason_codes'] == ['FFMPEG_RENDER_FAILED']
    assert result['ffmpeg_exit_code'] == 1 and not result['publication_ready']
    assert json.loads((tmp_path/'out'/'CANARY61.json').read_text())['human_approved'] is False


def test_rendered_face_clipping_explicitly_rejects_preview(tmp_path, monkeypatch):
    import cv2
    import numpy as np
    import ldporto.preview_verifier as verifier
    path = tmp_path/'fixture.mp4'
    writer = cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),10,(160,90))
    assert writer.isOpened()
    for _ in range(10):
        writer.write(np.full((90,160,3),100,np.uint8))
    writer.release()
    class FixtureDetector:
        def empty(self):
            return False
        def detectMultiScale(self, *a, **k):
            return [(0,0,30,30)]
    monkeypatch.setattr(cv2,'CascadeClassifier',lambda *a: FixtureDetector())
    monkeypatch.setattr(verifier,'_ffprobe',lambda p: None)
    data = verify_preview(path)['data']
    assert data['preview_approved'] is False and not data['publish_ready']
    assert 'FACE_OR_HEAD_CLIPPED' in {i['issue_type'] for i in data['issues']}


@pytest.mark.parametrize('kind', ['hash','crc','traversal'])
def test_package_security_reuses_current_validator(tmp_path, kind):
    package = build_core_package(disabled_analysis(), output_dir=tmp_path/'original')
    target = tmp_path/'hostile.zip'
    with zipfile.ZipFile(package['path']) as original, zipfile.ZipFile(target,'w',compression=zipfile.ZIP_STORED) as out:
        for name in original.namelist():
            content = original.read(name)
            if kind == 'hash' and name == 'editorial/default_shortlist.json':
                content += b' '
            out.writestr(name,content)
        if kind == 'traversal':
            out.writestr('../escape.json',b'{}')
    if kind == 'crc':
        with zipfile.ZipFile(target) as z:
            entry = z.getinfo('editorial/default_shortlist.json')
            offset = entry.header_offset + 30 + len(entry.filename.encode()) + len(entry.extra)
        with target.open('r+b') as stream:
            stream.seek(offset)
            byte = stream.read(1)
            stream.seek(offset)
            stream.write(bytes([byte[0] ^ 1]))
    assert validate_core_package(target)['status'] == 'failed'


def test_truncated_zip_is_failure_report(tmp_path):
    target = tmp_path/'truncated.zip'
    target.write_bytes(b'PK\x03\x04')
    result = validate_core_package(target)
    assert result['status'] == 'failed' and not result['checksums_valid']
    assert result['errors'] == ['package_read_failure:BadZipFile']


def test_synthetic_candidate_queue_crop_captions_render_and_sha_export(tmp_path):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('Local FFmpeg/ffprobe required; fixture encoding only')
    source = tmp_path/'synthetic.mp4'
    proc = subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
        'testsrc2=size=320x180:rate=10','-f','lavfi','-i','sine=frequency=440',
        '-t','2','-c:v','libx264','-threads','2','-preset','ultrafast','-c:a','aac',str(source)],
        capture_output=True, timeout=30)
    assert proc.returncode == 0
    data = disabled_analysis()
    data['metadata'].update(sha256=file_hash(source),duration=2,width=320,height=180,fps=10)
    data['transcript_segments'] = [dict(segment_id='S1',start=0,end=1,text='Uma historia completa.'),
        dict(segment_id='AD',start=1,end=2,text='Compre agora na nossa loja por R$ 99, desconto exclusivo!')]
    first = data['main_moments'][0]
    first.update(ideal_start=0,ideal_end=1,core_moment=dict(start=0,end=1),evidence_segment_ids=['S1'])
    duplicate = deepcopy(first)
    duplicate['moment_id'] = 'M1_ALT'
    ad = deepcopy(first)
    ad.update(moment_id='AD1',ideal_start=1,ideal_end=2,evidence_segment_ids=['AD'])
    data['main_moments'] += [duplicate, ad]
    data['editorial_shortlist'] = ['M1','M1_ALT','AD1']
    geo = geometry()
    data.update({k:v for k,v in geo.items() if k != 'metadata' and k != 'commercial_visual_s8'})
    rendered = render_preview(source, data['camera_director_timeline'], data['metadata'],
        tmp_path/'camera.mp4', dict(start=0,end=2),1080,1920)
    assert rendered['status'] == 'ok' and rendered['data']['frames'] > 0
    overlay_ass(dict(duration=2,segments=[dict(start=0,end=1,text='LEGENDA SINTETICA')]),
                tmp_path/'captions.ass',include_draft=True)
    proc = subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i','camera.mp4',
        '-vf','ass=captions.ass','-c:v','libx264','-threads','2','-preset','ultrafast',
        '-c:a','aac','preview.mp4'],cwd=tmp_path,capture_output=True,timeout=60)
    assert proc.returncode == 0
    technical = verify_mp4(tmp_path/'preview.mp4',2)
    assert technical['status'] == 'TECHNICALLY_VALID_REQUIRES_HUMAN_REVIEW'
    assert technical['probe']['width'] == 1080 and technical['probe']['height'] == 1920
    assert technical['probe']['audio_count'] == 1 and technical['decode_verified']
    validation = verify_preview(tmp_path/'preview.mp4',dict(duration=2,source_width=320,source_height=180),
        data['camera_director_timeline'])
    assert validation['data']['verifier_uses_rendered_frames'] and validation['data']['sampled_frames'] > 0
    data['preview_canaries'] = [dict(canary_id='SYNTHETIC61',interval=dict(start=0,end=2),
                                    render=rendered['data'],validation=validation['data'])]
    package = build_core_package(data, source=source, output_dir=tmp_path/'packages')
    assert validate_core_package(package['path'])['status'] == 'valid'
    queue = read(package['path'],'editorial/human_review_queue.json')
    assert queue['candidate_ids'] == ['M1']
    assert queue['entries'][0]['alternative_ids'] == ['M1_ALT']
    assert read(package['path'],'editorial/default_shortlist.json')['candidate_ids'] == []
    assert [c['candidate_id'] for c in read(package['path'],'editorial/excluded_commercials.json')] == ['AD1']
    assert read(package['path'],'social/stories_manifest.json')['stories'] == []
    with zipfile.ZipFile(package['path']) as archive:
        assert archive.testzip() is None
    receipt = dict(evidence_kind='synthetic_fixture',unit_fixture_pass=True,
        real_canary_status='real_canary_not_run',preview_sha256=file_hash(tmp_path/'preview.mp4'),
        package_sha256=file_hash(package['path']),viewport=viewport_audit(geo,dict(start=0,end=2)),
        text_legibility_verified=None,listening_verified=None,human_approved=False,publication_ready=False)
    assert receipt['viewport']['reason_codes'] == []
    (tmp_path/'FIXTURE61.json').write_text(json.dumps(receipt),encoding='utf-8')
