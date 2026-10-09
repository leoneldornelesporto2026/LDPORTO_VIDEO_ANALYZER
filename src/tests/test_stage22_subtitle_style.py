"""Synthetic text/timing only; no real audio alignment or platform approval."""
from copy import deepcopy
from pathlib import Path
import subprocess

import pytest

from ldporto.config import DEFAULTS
from ldporto.curator_delivery import overlay_ass
from ldporto.media_runtime import find_media_tool
from ldporto.social_output import build_social_output
from ldporto.subtitle_review import review_selected_clips, clip_karaoke_gate, _wrap_caption
from ldporto.subtitle_style import checked_text, contrast_on_black, style_rules
from test_v44_social_output import candidate


def evidence():
    cut = candidate('SYNTHETIC22', 100)
    words = [{'word': 'Teste', 'start': 101., 'end': 101.6, 'confidence': .99,
              'alignment_verified': True, 'audio_verified': True},
             {'word': 'sintético.', 'start': 101.7, 'end': 102.3, 'confidence': .99,
              'alignment_verified': True, 'audio_verified': True}]
    report = review_selected_clips(words, [cut], [cut['candidate_id']])
    return cut, words, report


@pytest.mark.parametrize('change', ['missing', 'boolean_only', 'other_id', 'changed_cut', 'unaligned',
                                    'not_listened', 'overlap', 'edited_text', 'cut_word'])
def test_karaoke_fails_closed_and_preserves_preference(change):
    cut, _, report = evidence()
    review = report['candidates'][cut['candidate_id']]
    assert clip_karaoke_gate(review, cut)
    if change == 'missing':
        report['candidates'] = {}
    elif change == 'boolean_only':
        report['candidates'][cut['candidate_id']] = {'karaoke_allowed': True}
    elif change == 'other_id':
        review['candidate_id'] = 'OTHER'
    elif change == 'changed_cut':
        cut['start'] += 1
    elif change in ('unaligned', 'not_listened'):
        review['captions'][0]['words'][0]['alignment_verified' if change == 'unaligned' else 'audio_verified'] = False
    elif change == 'overlap':
        review['captions'][0]['words'][1]['start'] = 101.5
    elif change == 'edited_text':
        review['captions'][0]['final_text'] = 'Texto alterado'
    else:
        review['captions'][0]['issue_codes'].append('cut_splits_word')
    cfg = deepcopy(DEFAULTS)
    cfg['social_output']['caption_preset'] = 'karaoke'
    result = build_social_output({'subtitle_review_s7': report}, cfg, {'candidates': [cut]})
    plan = result['stories'][0]['caption_plan']
    assert plan['requested_preset'] == 'karaoke'
    assert plan['effective_preset'] == 'simple'
    assert plan['effective_caption_mode'] == 'phrase_subtitles'
    assert plan['word_highlight_enabled'] is False
    assert plan['final_safe_area_verified'] is False
    assert result['publication_ready'] is False


def test_current_verified_cut_can_plan_karaoke_but_not_publish():
    cut, _, report = evidence()
    cfg = deepcopy(DEFAULTS)
    cfg['social_output']['caption_preset'] = 'pod_p'
    story = build_social_output({'subtitle_review_s7': report}, cfg, {'candidates': [cut]})['stories'][0]
    assert story['caption_plan']['word_highlight_enabled'] is True
    assert story['caption_preset'] == 'pod_p'
    assert story['publication_ready'] is False


@pytest.mark.parametrize('scale', [0, 100, float('nan'), None])
def test_contrast_size_and_font_constraints(scale):
    rules = style_rules(scale=scale, font='Arial,1\nStyle: injected', primary='#000000', highlight='invalid')
    assert 49 <= rules['font_size_px'] <= 72
    assert rules['font_family'] == 'Arial'
    assert contrast_on_black(rules['primary_color']) >= 4.5
    assert contrast_on_black(rules['highlight_color']) >= 4.5
    assert rules['background_opacity'] == 1.
    assert rules['font_availability_verified'] is None
    assert rules['safe_area_verified'] is False


def test_srt_phrase_wrap_keeps_tokens_punctuation_and_limits():
    text = 'Primeira frase, segunda frase sintética.'
    wrapped = _wrap_caption(text, 25)
    assert wrapped.splitlines() == ['Primeira frase,', 'segunda frase sintética.']
    assert ' '.join(wrapped.split()) == text
    with pytest.raises(ValueError, match='TEXT_LAYOUT_REVIEW_REQUIRED'):
        checked_text(' '.join(['palavra'] * 30))
    with pytest.raises(ValueError):
        checked_text('W' * 80)


def synthetic_clip():
    return {'duration': 2., 'title_suggestion': 'PREVIEW SINTÉTICO', 'karaoke_allowed': True,
            'segments': [{'start': 0., 'end': 2., 'text': 'Legenda sintética, sem prova de áudio.'}]}


def test_ass_constraints_no_fake_word_timing_and_no_truncation(tmp_path):
    path = tmp_path / 'overlay.ass'
    overlay_ass(synthetic_clip(), path, include_draft=True)
    content = path.read_text(encoding='utf-8')
    assert 'PlayResX: 1080' in content and 'PlayResY: 1920' in content
    assert 'WrapStyle: 2' in content and r'\N' in content
    assert r'\k' not in content
    assert 'Legenda sintética,' in content and 'sem prova de áudio.' in content
    assert ',3,8,0,2,108,194,430,1' in content
    original = content
    clip = synthetic_clip()
    clip['title_suggestion'] = 'título ' * 50
    with pytest.raises(ValueError, match='TEXT_LAYOUT_REVIEW_REQUIRED'):
        overlay_ass(clip, path, include_draft=True)
    assert path.read_text(encoding='utf-8') == original
    clip['title_suggestion'] = 'W' * 21
    with pytest.raises(ValueError, match='glyph width budget exceeded'):
        overlay_ass(clip, path)


def render_synthetic_frame(folder):
    ffmpeg = find_media_tool('ffmpeg')
    if not ffmpeg:
        pytest.skip('Local FFmpeg unavailable')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    overlay_ass(synthetic_clip(), folder / 'overlay.ass', include_draft=True)
    command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
               '-i', 'color=c=0x607080:s=1080x1920:r=1:d=1', '-vf', 'ass=overlay.ass',
               '-frames:v', '1', '-threads', '1', 'preview.png']
    proc = subprocess.run(command, cwd=folder, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return folder / 'preview.png'


def test_ffmpeg_renders_synthetic_ass_1080x1920(tmp_path):
    import cv2
    frame = cv2.imread(str(render_synthetic_frame(tmp_path)))
    assert frame is not None and frame.shape[:2] == (1920, 1080)
    white = (frame.min(axis=2) > 230)
    ys, xs = white.nonzero()
    assert len(xs) > 100
    assert xs.min() >= 108 and xs.max() < 886
    assert ys.min() >= 346 and ys.max() < 1498
