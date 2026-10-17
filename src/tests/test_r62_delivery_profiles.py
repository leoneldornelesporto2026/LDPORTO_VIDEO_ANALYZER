"""Two real package archives with explicitly synthetic pixels; no local show/media."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import zipfile

import cv2
import numpy as np
import pytest

from ldporto import compact_artifacts, visual_frame_handoff
from ldporto.core import digest, file_hash
from ldporto.r62_delivery import build_visual_delivery, verify_full_audit
from ldporto.second_curation_export import build_core_package, validate_core_package
from test_v43_handoff import analysis_fixture


class SyntheticPixelsProvider:
    """A declared fixture provider, never an observation of real source content."""

    def __init__(self, source, *, metadata=None, max_frames=384, max_bytes=40 * 1024**2):
        self.source_sha256 = file_hash(source)
        assert self.source_sha256 == metadata['sha256']
        self.cache, self.cache_bytes, self.decoded_frames = {}, 0, 0
        self.max_frames, self.max_bytes = max_frames, max_bytes

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def get(self, timestamp):
        return self(timestamp, None)

    def __call__(self, timestamp, output):
        if timestamp not in self.cache:
            if len(self.cache) >= self.max_frames:
                return {'captured': False, 'reason': 'synthetic_global_frame_budget_exhausted'}
            image = np.full((36, 64, 3), 80, dtype=np.uint8)
            cv2.rectangle(image, (16, 5), (38, 28), (100, 180, 210), -1)
            got, encoded = cv2.imencode('.jpg', image)
            assert got
            self.cache[timestamp] = encoded.tobytes()
            self.cache_bytes += len(self.cache[timestamp])
            self.decoded_frames += 1
        if output is not None:
            Path(output).write_bytes(self.cache[timestamp])
        return {'captured': True, 'source_time_s': timestamp, 'source_frame_index': None,
            'timestamp_provenance': 'SYNTHETIC_FIXTURE', 'capture_method': 'SYNTHETIC_FIXTURE_PIXELS',
            'media_source_sha256': self.source_sha256, 'width': 64, 'height': 36,
            'source_decoded_width': 1920, 'source_decoded_height': 1080, 'quality': 'fixture_only'}


def delivery_fixture(tmp_path, monkeypatch):
    # A reference blob is deliberately not a video. Only the fixture provider
    # supplies synthetic image artifacts, so no decoder/model can touch show media.
    source = tmp_path / 'SYNTHETIC_SOURCE.reference'
    source.write_bytes(b'SYNTHETIC SOURCE IDENTITY ONLY - NO REAL MEDIA')
    analysis = analysis_fixture()
    analysis['metadata']['sha256'] = file_hash(source)
    analysis['metadata']['source'].update(id='SYNTHETIC_DELIVERY', filename=source.name)
    second = deepcopy(analysis['main_moments'][0])
    second.update(moment_id='M2', ideal_start=0., ideal_end=30., evidence_segment_ids=['S0'],
                  default_shortlist_eligible=False)
    analysis['main_moments'].append(second)
    analysis['social_output'] = {'stories': [{'story_id': 'ST_FIXTURE', 'candidate_id': 'M1',
        'start': 30., 'end': 60., 'duration': 30., 'title': 'Uma explicacao completa sobre a carreira.'}]}
    analysis['run_manifest'] = {'run_id': 'SYNTHETIC_ANALYSIS_REVISION'}
    analysis['stage_status'] = {'15_semantic': {'status': 'ok', 'fixture_only': True},
                                '16_understanding': {'status': 'ok', 'fixture_only': True}}
    analysis_dir = tmp_path / 'analysis_fixture'
    analysis_dir.mkdir()
    (analysis_dir / 'run_manifest.json').write_text(json.dumps(analysis['run_manifest']), encoding='utf-8')
    (analysis_dir / 'analysis.json').write_text(json.dumps(analysis), encoding='utf-8')
    monkeypatch.setattr(compact_artifacts, 'load_analysis_artifacts', lambda *_args, **_kwargs: deepcopy(analysis))
    monkeypatch.setattr(visual_frame_handoff, 'SparseFrameProvider', SyntheticPixelsProvider)
    package = Path(build_core_package(analysis, output_dir=tmp_path / 'parent_package')['path'])
    timeline = [{'director_id': 'SYNTHETIC_REPLAY_D1', 'source_shot_id': 'SYNTHETIC_SHOT',
        'start': 0., 'end': 120., 'layout': 'full_frame', 'camera_mode': 'SOURCE_PRESERVE',
        'focus_person': None, 'crop': {'safe': False, 'rect_end': None},
        'camera': {'keyframes': [{'time': 0., 'center': [.5, .5], 'zoom': 1.},
                                 {'time': 120., 'center': [.5, .5], 'zoom': 1.}]}}]
    timeline_path = tmp_path / 'synthetic_revised_timeline.json'
    timeline_path.write_text(json.dumps(timeline), encoding='utf-8')
    return analysis, package, analysis_dir, source, timeline, timeline_path


def test_delivery_profiles_keep_parent_hashes_and_separate_approval_gates(tmp_path, monkeypatch):
    analysis, package, analysis_dir, source, timeline, timeline_path = delivery_fixture(tmp_path, monkeypatch)
    package_hash, source_hash = file_hash(package), file_hash(source)
    result = build_visual_delivery(package, analysis_dir, source, tmp_path / 'delivery',
        camera_timeline_path=timeline_path, max_frames=2)
    assert result['state'] == 'PARTIAL'
    assert result['piece_count'] == 3 and result['reel_count'] == 2 and result['story_piece_count'] == 1
    assert result['new_model_calls'] == 0 and result['full_pipeline_executed'] is False
    assert result['preview_approved'] is result['human_approved'] is result['publication_ready'] is False
    assert file_hash(package) == package_hash and file_hash(source) == source_hash
    full, editorial = Path(result['full_audit']['path']), Path(result['editorial']['path'])
    assert full.is_file() and editorial.is_file()
    assert verify_full_audit(full)['status'] == 'valid'
    assert validate_core_package(editorial)['status'] == 'valid'
    assert file_hash(full) == result['full_audit']['sha256']
    assert file_hash(editorial) == result['editorial']['sha256']
    assert not list(full.parent.glob('*.partial'))
    with zipfile.ZipFile(editorial) as archive:
        master = json.loads(archive.read('HANDOFF_MASTER.json'))
        assert master['derivation']['parent_package_sha256'] == package_hash
        assert master['full_audit_ref']['sha256'] == file_hash(full)
        assert master['package_profiles'] == ['FULL_AUDIT', 'EDITORIAL_HANDOFF']
        assert master['active_camera_ref'] == 'camera/r62_shared_camera_handoff.json'
        assert master['analysis_revision'] == 'SYNTHETIC_ANALYSIS_REVISION'
        assert master['r62_acceptance_state'] == 'PARTIAL'
        assert master['publication_ready'] is master['preview_approved'] is master['human_approved'] is False
        assert json.loads(archive.read('camera/camera_director_timeline.json')) == []
        assert json.loads(archive.read('camera/r62_camera_timeline.json')) == timeline
        assert 'schemas/visual_frame_handoff.schema.json' in archive.namelist()
        assert not any(name.startswith('raw_analysis/') for name in archive.namelist())
        assert not any(name.endswith('.mp4') for name in archive.namelist())
        index = json.loads(archive.read('VISUAL_FRAME_HANDOFF/index.json'))
        assert {row['piece_id'] for row in index['pieces']} == {'M1', 'M2', 'ST_FIXTURE'}
        for piece in index['pieces']:
            manifest = json.loads(archive.read(piece['manifest_ref']))
            assert manifest['source_sha256'] == source_hash
            assert manifest['dependencies'][0]['path'] == 'camera/r62_camera_timeline.json'
            assert manifest['dependencies'][0]['content_sha256'] == digest(timeline)
            assert manifest['coverage']['captured_frames'] == 2
            assert manifest['editorial_state'] == 'PARTIAL'
            for record in manifest['files']:
                path = piece['manifest_ref'].rsplit('/', 1)[0] + '/' + record['path']
                assert hashlib.sha256(archive.read(path)).hexdigest() == record['sha256']
        captions = json.loads(archive.read('subtitles/visual_piece_caption_preflight.json'))
        assert set(captions['stories']) == {'M1', 'M2', 'ST_FIXTURE'}
        assert captions['new_asr_calls'] == 0
    with zipfile.ZipFile(full) as archive:
        assert 'raw_analysis/run_manifest.json' in archive.namelist()
        manifest = json.loads(archive.read('FULL_AUDIT_MANIFEST.json'))
        assert manifest['profile'] == 'FULL_AUDIT'
        assert manifest['source_video_included'] is manifest['preview_approved'] is manifest['publication_ready'] is False


def test_full_audit_checksum_tampering_is_rejected(tmp_path, monkeypatch):
    _, package, analysis_dir, source, _, timeline_path = delivery_fixture(tmp_path, monkeypatch)
    result = build_visual_delivery(package, analysis_dir, source, tmp_path / 'delivery',
        camera_timeline_path=timeline_path, max_frames=2)
    altered = tmp_path / 'altered_full.zip'
    with zipfile.ZipFile(result['full_audit']['path']) as original, zipfile.ZipFile(altered, 'w') as changed:
        for name in original.namelist():
            changed.writestr(name, b'{"synthetic_tamper":true}' if name == 'raw_analysis/run_manifest.json' else original.read(name))
    verification = verify_full_audit(altered)
    assert verification['status'] == 'failed'
    assert 'full_audit_checksum:raw_analysis/run_manifest.json' in verification['errors']


def test_delivery_rejects_media_identity_before_fixture_decoder(tmp_path, monkeypatch):
    _, package, analysis_dir, source, _, timeline_path = delivery_fixture(tmp_path, monkeypatch)
    source.write_bytes(b'DIFFERENT SYNTHETIC REFERENCE')
    with pytest.raises(ValueError, match='media_identity_mismatch'):
        build_visual_delivery(package, analysis_dir, source, tmp_path / 'delivery', camera_timeline_path=timeline_path)


@pytest.mark.parametrize('patch', [
    {'profile': 'INVENTED'}, {'schema_version': 'unknown'}, {'publication_ready': True},
    {'preview_approved': True}, {'source_video_included': True}, {'files': None},
])
def test_full_verifier_rejects_unknown_contract_and_approval_flags(tmp_path, patch):
    blob = b'SYNTHETIC AUDIT EVIDENCE'
    manifest = {'schema_version': 'r6.2', 'profile': 'FULL_AUDIT', 'source_video_included': False,
        'preview_approved': False, 'publication_ready': False,
        'files': [{'path': 'evidence.txt', 'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()}]}
    manifest.update(patch)
    path = tmp_path / 'contract_test.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('evidence.txt', blob)
        archive.writestr('FULL_AUDIT_MANIFEST.json', json.dumps(manifest))
    assert verify_full_audit(path)['status'] == 'failed'


def test_full_verifier_rejects_duplicate_ledger_rows(tmp_path):
    blob = b'SYNTHETIC AUDIT EVIDENCE'
    row = {'path': 'evidence.txt', 'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()}
    manifest = {'schema_version': 'r6.2', 'profile': 'FULL_AUDIT', 'source_video_included': False,
        'preview_approved': False, 'publication_ready': False, 'files': [row, row]}
    path = tmp_path / 'duplicate_ledger.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('evidence.txt', blob)
        archive.writestr('FULL_AUDIT_MANIFEST.json', json.dumps(manifest))
    assert verify_full_audit(path)['status'] == 'failed'
