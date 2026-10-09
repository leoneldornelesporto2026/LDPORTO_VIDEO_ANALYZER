"""Stage 38: real synthetic MP4, plus isolated failure fixtures. No human approval evidence."""
from copy import deepcopy
from pathlib import Path
import json
import subprocess

import pytest

from ldporto import curator_delivery as delivery
from test_s9_s10_s11_delivery import media, ready, ALL_REVIEWED


def test_canary_and_controlled_stories_have_independent_provenance(tmp_path, ready, media):
    plan = delivery.prepare_plan(ready, media, music_path=media)
    canary = delivery.render_clip(plan, 0, tmp_path/'canary', draft_captions=True)
    # This checklist is simulated test input, never a real human review.
    approval = delivery.approve_canary(plan, canary, ALL_REVIEWED, reviewer='SYNTHETIC_TEST_ONLY')
    batch = delivery.render_batch(plan, approval, canary, tmp_path/'batch', draft_captions=True)
    assert batch['state'] == 'REVIEW_BATCH_RENDERED_NOT_PUBLISHABLE'
    for clip, report in zip(plan['clips'], batch['clips']):
        assert report['probe']['video_codec'] == 'h264'
        assert report['probe']['audio_codec'] == 'aac'
        assert report['probe']['display_aspect_ratio'] == '9:16'
        assert report['probe']['sample_aspect_ratio'] == '1:1'
        assert (report['probe']['width'], report['probe']['height']) == (1080, 1920)
        assert abs(report['probe']['duration'] - clip['duration']) < .35
        assert report['decode_verified'] is True and report['decode_exit_code'] == 0
        assert report['title_suggestion'] == clip['title_suggestion']
        assert report['render_layout'] == 'source_preserve_blurred_fill'
        assert report['preview_approved'] is None and report['publish_ready'] is False
        assert report['audio_mix_log']['listening_verified'] is None
        sidecar = Path(report['file']).with_suffix('.render.json')
        assert json.loads(sidecar.read_text(encoding='utf-8')) == report
    ass = (tmp_path/'canary'/f"{plan['clips'][0]['id']}.ass").read_text(encoding='utf-8')
    assert ',Title,' in ass and ',Caption,' in ass
    assert canary['performance']['encoder_threads'] == 2
    # Shorts use the same renderer but keep their own IDs/windows/titles.
    shorts = delivery.prepare_plan(ready, media, prefer_stories=False)
    assert all(c['id'].startswith('SHORT_') for c in shorts['clips'])
    short = delivery.render_clip(shorts, 1, tmp_path/'short')
    assert short['decode_verified'] is True and short['publication_ready'] is False


def test_failed_middle_story_does_not_stop_next_or_overwrite_reviewed_files(tmp_path, ready, media, monkeypatch):
    plan = delivery.prepare_plan(ready, media)
    extra = deepcopy(plan['clips'][1])
    extra['id'] = 'STORY_003'
    extra['title_suggestion'] = 'Terceiro título sintético'
    plan['clips'].append(extra)
    plan['plan_sha256'] = delivery.canonical_hash({k: v for k, v in plan.items() if k != 'plan_sha256'})
    canary = delivery.render_clip(plan, 0, tmp_path/'batch')
    approval = delivery.approve_canary(plan, canary, ALL_REVIEWED, reviewer='SYNTHETIC_TEST_ONLY')
    original = delivery.render_clip

    def fail_middle(*args, **kwargs):
        if args[1] == 1:
            raise subprocess.TimeoutExpired('synthetic_failure', 120)
        return original(*args, **kwargs)

    monkeypatch.setattr(delivery, 'render_clip', fail_middle)
    batch = delivery.render_batch(plan, approval, canary, tmp_path/'batch')
    assert batch['state'] == 'PARTIAL'
    assert [r['status'] for r in batch['clips']] == [canary['status'], 'BLOCKED', canary['status']]
    assert delivery.file_sha256(canary['file']) == canary['sha256']
    assert batch['clips'][2]['decode_verified'] is True
    assert batch['clips'][1]['sha256'] is None
    assert (tmp_path/'batch'/'STORY_002.render.json').is_file()
    with pytest.raises(ValueError, match='BATCH_NOT_READY'):
        delivery.finalize_batch(plan, batch, {'clips': []})
    before = {p.name: delivery.file_sha256(p) for p in (tmp_path/'batch').glob('STORY_*')}
    delivery.render_batch(plan, approval, canary, tmp_path/'batch')
    assert before == {p.name: delivery.file_sha256(p) for p in (tmp_path/'batch').glob('STORY_*')}


@pytest.mark.parametrize('audio_codec,sar,issue', [
    ('mp3', '1', 'WRONG_DELIVERY_CODEC'), ('aac', '2', 'WRONG_ASPECT_RATIO')])
def test_actual_wrong_codec_or_aspect_is_blocked(tmp_path, media, audio_codec, sar, issue):
    target = tmp_path/'wrong.mp4'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
        '-i', str(media), '-vf', f'scale=1080:1920,setsar={sar}', '-t', '0.5',
        '-c:v', 'libx264', '-threads', '2', '-preset', 'ultrafast', '-c:a', audio_codec,
        str(target)], check=True, capture_output=True, timeout=60)
    report = delivery.verify_mp4(target, .5)
    assert report['status'] == 'BLOCKED' and issue in report['issues']


def test_real_corrupt_payload_is_rejected_despite_readable_container(tmp_path, ready, media):
    plan = delivery.prepare_plan(ready, media)
    report = delivery.render_clip(plan, 0, tmp_path/'original')
    payload = bytearray(Path(report['file']).read_bytes())
    mdat = payload.index(b'mdat') + 4
    payload[mdat:mdat+4096] = b'\x00' * 4096
    damaged = tmp_path/'damaged.mp4'
    damaged.write_bytes(payload)
    assert delivery.probe(damaged)['video_codec'] == 'h264'
    checked = delivery.verify_mp4(damaged, plan['clips'][0]['duration'])
    assert checked['status'] == 'BLOCKED'
    assert 'DECODE_INTEGRITY_FAILED' in checked['issues']


def test_source_changed_after_plan_blocks_render(tmp_path, ready, media):
    plan = delivery.prepare_plan(ready, media)
    # Use a synthetic copy so the shared fixture is never modified.
    changed = tmp_path/'changed.mp4'
    changed.write_bytes(media.read_bytes() + b'changed')
    plan['source_video'] = str(changed)
    plan['plan_sha256'] = delivery.canonical_hash({k: v for k, v in plan.items() if k != 'plan_sha256'})
    with pytest.raises(ValueError, match='SOURCE_MODIFIED'):
        delivery.render_clip(plan, 0, tmp_path/'blocked')
