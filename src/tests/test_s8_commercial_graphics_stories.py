"""S8 regression: advertising, visual evidence, title grounding and video-wide diversity."""
import sys
import types

import numpy as np

from ldporto.commercial_gate import apply_commercial_refinement, build_commercial_blocks, targeted_ocr
from ldporto.social_output import build_social_output, select_story_set
from ldporto.config import DEFAULTS


def _moment(cid, start, end, transcript='', *, score=.8):
    return {'moment_id': cid, 'ideal_start': start, 'ideal_end': end,
            'core_moment': {'start': start, 'end': end}, 'text': transcript,
            'standalone_score': .90, 'hook_score': score,
            'clean_opening': True, 'clean_ending': True,
            'context_requirement': 'none'}


def _candidate(cid, start, *, topic='X', score=.8):
    return {'candidate_id': cid, 'start': start, 'end': start + 35., 'duration': 35.,
            'primary_topic_id': topic, 'editorial_quality_score': score,
            'ranking_confidence': .8, 'hook_strength': .8,
            'score_components': {'standalone_clarity': .9, 'humor': .9},
            'transcript_literal': 'Como esse caso aconteceu? Foi durante a entrevista.',
            'generated_copy': {'title_idea': 'Segredo inacreditável que ninguém sabia',
                               'hook_idea': 'Como esse caso aconteceu?'},
            'default_shortlist_eligible': True,
            'commercial_classification': {'eligibility': 'eligible', 'commercial_score': 0., 'content_type':'editorial_content'},
            'person_ids': ['P1'], 'layouts': ['full_frame']}


def test_canonical_sale_and_guest_self_promotion_excluded_from_shortlist():
    segments = [
        {'segment_id':'A', 'start':0, 'end':20, 'text':'Compre o curso com 50% de desconto e acesse a loja hoje.'},
        {'segment_id':'B', 'start':21, 'end':40, 'text':'Aproveite a promoção e compre ingressos para meu show.'},
        {'segment_id':'C', 'start':50, 'end':70, 'text':'Eu conheci essa loja e lembro das histórias antigas.'},
    ]
    moments = [_moment('A', 0, 20), _moment('B', 21, 40), _moment('C', 50, 70)]
    result = apply_commercial_refinement({'main_moments': moments}, segments, [], {'max_moments': 12})
    statuses = {r['moment_id']:r['commercial_classification']['eligibility'] for r in result['main_moments']}
    assert statuses['A'] == 'excluded' and statuses['B'] == 'excluded'
    assert statuses['C'] != 'excluded'
    assert result['candidate_metrics']['excluded_commercial_count'] == 2
    assert result['candidate_metrics']['commercial_block_count'] >= 1
    assert not set(result['editorial_shortlist']) & {'A', 'B'}


def test_partial_candidate_inside_commercial_block_fails_closed():
    segments = [{'segment_id':'SALE', 'start':0, 'end':30,
                 'text':'Aproveite o desconto em todos os cursos, compre e pague no Pix.'}]
    moments = [_moment('PART', 12, 17)]
    out = apply_commercial_refinement({'main_moments':moments}, segments, [], {'max_moments':12})
    c = out['main_moments'][0]
    assert c['commercial_classification']['eligibility'] == 'excluded'
    assert c['commercial_classification']['block_propagated'] is True
    assert c['commercial_block_refs'] and not out['editorial_shortlist']


def test_brand_discussion_near_ad_does_not_inherit_exclusion():
    segments = [{'segment_id':'A','start':0,'end':15,'text':'Eu trabalhava nessa empresa e contei a história da minha infância.'},
                {'segment_id':'B','start':19,'end':35,'text':'Compre hoje e aproveite o desconto especial no Pix na loja.'}]
    out = apply_commercial_refinement({'main_moments':[_moment('A',0,15),_moment('B',19,35)]},segments,[],{})
    by = {r['moment_id']:r for r in out['main_moments']}
    assert by['A']['commercial_classification']['eligibility'] == 'eligible'
    assert by['B']['commercial_classification']['eligibility'] == 'excluded'


def test_ocr_only_offer_is_review_not_confirmed_speech_ad():
    segments = [{'segment_id':'S1', 'start':0,'end':30, 'text':'Naquele dia a plateia começou a rir.'}]
    visual = [{'source':'ocr', 'text':'Compre agora por R$ 79 com desconto na loja',
               'start':10,'end':10,'duration_unknown':True,'moment_id':'M'}]
    out = apply_commercial_refinement({'main_moments':[_moment('M',0,30)]},segments,visual,{})
    row = out['main_moments'][0]
    assert row['commercial_classification']['eligibility'] == 'review'
    assert row['commercial_classification']['visual_only_sale_unconfirmed'] is True
    assert row['default_shortlist_eligible'] is False and out['editorial_shortlist'] == []


def test_ocr_observation_outside_candidate_does_not_contaminate_other_clip():
    segments = [{'segment_id':'S1', 'start':50, 'end':80,
                 'text':'Falamos do programa passado e da história dos convidados.'}]
    visual = [{'source':'ocr', 'text':'Compre agora com desconto na loja por R$ 79',
               'start':10,'end':10,'duration_unknown':True,'moment_id':'OTHER'}]
    out = apply_commercial_refinement({'main_moments':[_moment('M',50,80)]},segments,visual,{})
    assert out['main_moments'][0]['commercial_classification']['eligibility'] == 'eligible'


def test_targeted_ocr_reports_observed_bbox_and_never_infers_duration(monkeypatch):
    import cv2
    class Capture:
        def __init__(self, *_): self.pos = 0
        def isOpened(self): return True
        def set(self, _, val): self.pos = val
        def read(self): return True, np.zeros((100,200,3), dtype=np.uint8)
        def release(self): pass
    fake = types.SimpleNamespace(
        Output=types.SimpleNamespace(DICT='dict'),
        TesseractError=RuntimeError,
        get_tesseract_version=lambda: 'mock',
        image_to_data=lambda *a, **kw: {'text':['PROMOÇÃO', 'R$79'], 'conf':['95','90'],
            'block_num':[1,1], 'par_num':[1,1], 'line_num':[1,1],
            'left':[10,90], 'top':[65,65], 'width':[70,40], 'height':[18,18]})
    monkeypatch.setitem(sys.modules, 'pytesseract', fake)
    monkeypatch.setattr(cv2, 'VideoCapture', Capture)
    result = targeted_ocr('mock.mp4', [_moment('M', 0, 20)], {'enabled':True,'languages':'por+eng'}, 1)
    assert result['status'] == 'measured' and result['sampled_frames'] == 3
    assert len(result['texts']) == 3
    assert all(r['duration_unknown'] and r['end'] == r['start'] for r in result['texts'])
    assert all(0 <= r['bbox']['x'] < 1 and r['bbox']['y'] > .5 for r in result['texts'])
    assert all(r['visual_type_hint'] == 'offer_or_price' for r in result['texts'])


def test_disabled_optional_ocr_reports_skipped_not_empty_success():
    assert targeted_ocr('does-not-exist.mp4', [], {'enabled': False})['status'] == 'skipped'


def test_story_set_spreads_from_start_to_end_without_forcing_slots():
    rows = [_candidate('EARLY', 100, topic='P1',score=.87),
            _candidate('EARLY_COPY',105,topic='P1',score=.86),
            _candidate('MID', 1800, topic='P2',score=.83),
            _candidate('END', 3600, topic='P3',score=.75)]
    out, metrics = select_story_set(rows, {'min_seconds':15,'max_seconds':60,'max_stories':12,
        'min_spacing_seconds':45,'max_per_topic':1, 'distribution_window_seconds':600,'max_per_window':2})
    assert {c['candidate_id'] for c in out} == {'EARLY','MID','END'}
    assert metrics['phase_coverage'] == 3
    assert metrics['unfilled_slots_are_intentional'] is True


def test_review_commercial_candidate_never_selected_as_story():
    row = _candidate('REVIEW', 0)
    row['commercial_classification'] = {'eligibility':'review', 'commercial_score':.25}
    out, _ = select_story_set([row], {'max_stories':12})
    assert not out


def test_story_hook_is_anchored_and_visual_plan_marks_safe_area_unverified():
    from copy import deepcopy
    cfg = deepcopy(DEFAULTS)
    item = _candidate('M1', 20)
    result = build_social_output({'second_curation_package':{'candidates':[item]},
        'broadcast_graphics': {'intervals':[{'start':10,'end':70,'regions':[
            {'kind':'lower_third','persistent':True,'y_start':.67,'y_end':.9}]}]},
        'commercial_visual_s8':{'texts':[{'moment_id':'M1','observed_at':35,
            'bbox':{'x':.2,'y':.8,'width':.5,'height':.08},'visual_type_hint':'lower_third_gc'}]},
        'audio_events':[{'start':30,'end':31,'label':'laughter','confidence':.91}]},
        cfg, {'candidates':[item]})
    story = result['stories'][0]
    assert story['title'] != item['generated_copy']['title_idea']
    assert story['title'] in item['transcript_literal']
    assert story['caption_plan']['preferred_position'] == 'upper_middle'
    assert story['caption_plan']['observed_ocr_boxes'][0]['persistence'] == 'unknown'
    assert story['caption_plan']['final_safe_area_verified'] is False
    assert story['visual_plan']['safe_area_verified'] is False
    assert story['visual_plan']['audio_reaction_evidence_count'] == 1
    assert story['publication_ready'] is False


def test_nonexistent_audio_events_never_fabricate_laughter():
    from copy import deepcopy
    row = _candidate('M1',0)
    result = build_social_output({}, deepcopy(DEFAULTS), {'candidates':[row]})
    assert not result['stories'][0]['audio_reaction_evidence']
    assert result['stories'][0]['visual_plan']['audio_reaction_evidence_count'] == 0


def test_visual_step_propagates_real_status_without_silent_success():
    from ldporto.pipeline import _optional_visual_result
    assert _optional_visual_result({'status':'measured'})['status'] == 'ok'
    assert _optional_visual_result({'status':'unavailable','reason':'optional_tesseract_missing'})['status'] == 'unavailable'
    assert _optional_visual_result({'status':'skipped','reason':'ocr_disabled'})['status'] == 'skipped'
    assert _optional_visual_result({'status':'partial'})['status'] == 'partial'


def test_prior_commercial_exclusion_not_erased_by_local_reclassification():
    candidate = _moment('OLD',0,15)
    candidate['commercial_classification']={'eligibility':'excluded','content_type':'advertisement',
        'commercial_score':.95, 'evidence_spans':[], 'signals':['sponsor'],'reason':'upstream_review'}
    segments=[{'segment_id':'S1','start':0,'end':15,'text':'Hoje vamos contar uma história da nossa infância.'}]
    result=apply_commercial_refinement({'main_moments':[candidate]},segments,[],{})
    assert result['main_moments'][0]['commercial_classification']['upstream_exclusion_preserved']
    assert not result['editorial_shortlist']


def test_recalculated_stories_commercial_review_cannot_be_reenabled_on_export():
    from ldporto.second_curation_export import _final_commercial_classification
    result = _final_commercial_classification({'commercial_classification':{
        'eligibility':'review','content_type':'uncertain', 'commercial_score':.3,
        'review_reason':'ocr_sales_evidence_without_transcript_confirmation'},
        'transcript_literal':'Naquele dia começou a festa.'})
    assert result['eligibility'] == 'review'
    assert result['export_reclassification'] == 'upstream_commercial_review_preserved'


def test_auditor_from_folder_and_zip_no_fake_media_results(tmp_path):
    import json, zipfile
    from scripts.dev.audit_commercial_stories_s8 import audit
    saved=tmp_path/'run'; saved.mkdir()
    (saved/'transcript_segments.json').write_text(json.dumps([
        {'segment_id':'S1','start':0,'end':30,
         'text':'Aproveite o desconto e compre agora o curso na loja.'}]),encoding='utf-8')
    (saved/'main_moments.json').write_text(json.dumps([_moment('A',0,30)]),encoding='utf-8')
    for loc in (saved, tmp_path/'run.zip'):
        if loc.suffix == '.zip':
            with zipfile.ZipFile(loc, 'w') as archive:
                for f in saved.iterdir(): archive.write(f, f.name)
        result=audit(loc,tmp_path/('audit_zip' if loc.suffix else 'audit_folder'))
        assert result['source_has_canonical_segments'] is True
        assert result['rechecked_eligibility']['excluded'] == 1
        assert result['ocr']['observation_count'] == 0
        assert result['stories']['count'] == 0


def test_sale_split_between_asr_segments_still_becomes_block():
    segments = [{'segment_id':'S1','start':0,'end':10,'text':'Compre meu curso de fotografia.'},
                {'segment_id':'S2','start':10,'end':20,'text':'Preço de R$ 79 em dez parcelas.'}]
    assert not any((__import__('ldporto.editorial',fromlist=['classify_content']).classify_content(s['text'])['eligibility']=='excluded') for s in segments)
    blocks = build_commercial_blocks(segments)
    assert len(blocks) == 1
    assert blocks[0]['start'] == 0 and blocks[0]['end'] == 20
    assert blocks[0]['segment_ids'] == ['S1','S2']
    out = apply_commercial_refinement({'main_moments': [_moment('A',0,10)]},segments,[],{})
    assert out['main_moments'][0]['commercial_classification']['eligibility'] == 'excluded'


def test_graphics_detector_requires_temporal_samples_without_inventing_text():
    from ldporto.broadcast_graphics import detect_graphics
    import cv2
    frames=[]
    for i in range(8):
        image=np.zeros((180,320,3),dtype=np.uint8)
        cv2.rectangle(image,(0,125),(319,173),(200,200,200),1)
        cv2.putText(image,'TEXTO NO GC',(20,156),cv2.FONT_HERSHEY_SIMPLEX,.7,(255,255,255),2)
        frames.append(image)
    result = detect_graphics(frames)
    assert result['status'] == 'measured'
    assert all(r['measurement'] == 'graphic_candidate_not_text_recognition' for r in result['regions'])
    assert all(r['needs_review'] for r in result['regions'])
    assert detect_graphics(frames[:2])['status'] == 'insufficient_temporal_samples'


def test_ocr_overlay_conflict_moves_caption_from_lower_to_upper_even_without_graphics():
    from copy import deepcopy
    candidate = _candidate('M', 0)
    report=build_social_output({'commercial_visual_s8': {'texts':[
        {'moment_id':'M', 'observed_at':5,'bbox':{'x':0.0,'y':.62,'width':1.,'height':.2}}]}},
        deepcopy(DEFAULTS), {'candidates':[candidate]})
    plan=report['stories'][0]['caption_plan']
    assert plan['preferred_position'] == 'upper_middle'
    rects={r['position']:r for r in plan['candidate_safe_rects_normalized']}
    assert rects['lower_middle']['observed_overlay_conflicts'] == 1
    assert rects['upper_middle']['observed_overlay_conflicts'] == 0
    assert plan['final_safe_area_verified'] is False
