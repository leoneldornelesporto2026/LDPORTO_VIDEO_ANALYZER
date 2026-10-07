from copy import deepcopy

from ldporto.config import DEFAULTS, validate
from ldporto.social_output import ASPECT_RATIOS, build_social_output, select_story_set


def candidate(cid, start, category='impacto', topic='T1', commercial=False, score=.8):
    components = {'humor': 0.0, 'emotion': 0.0, 'curiosity': 0.0, 'surprise': 0.0,
                  'controversy': 0.0, 'story_completeness': 0.0, 'qa_completeness': 0.0,
                  'information_density': .3, 'visual_viability': .7, 'standalone_clarity': .9}
    map_key = {'humor':'humor', 'emocao':'emotion', 'curiosidade':'curiosity', 'impacto':'surprise',
               'historia':'story_completeness', 'pergunta_resposta':'qa_completeness'}
    if category in map_key:
        components[map_key[category]] = .95
    return {'candidate_id': cid, 'start': start, 'end': start + 40, 'duration': 40,
            'primary_topic_id': topic, 'topic': topic, 'editorial_quality_score': score,
            'ranking_confidence': .8, 'hook_strength': .85, 'score_components': components,
            'default_shortlist_eligible': not commercial,
            'commercial_classification': {'eligibility': 'exclude' if commercial else 'eligible',
                                          'commercial_score': .95 if commercial else 0.0},
            'transcript_literal': f'Pergunta forte {cid}? Esta e uma resposta completa e independente.',
            'generated_copy': {'title_idea': f'Titulo {cid}', 'hook_idea': None},
            'person_ids': ['P1'], 'camera_mode': ['SOURCE_PRESERVE'], 'layouts': ['full_frame']}


def test_story_set_means_multiple_independent_diverse_moments_and_excludes_ads():
    candidates = [
        candidate('A', 0, 'impacto', 'T1', score=.95),
        candidate('B', 60, 'impacto', 'T1', score=.94),
        candidate('C', 130, 'humor', 'T2', score=.90),
        candidate('D', 210, 'emocao', 'T3', score=.89),
        candidate('AD', 300, 'impacto', 'T4', commercial=True, score=.99),
    ]
    selected, metrics = select_story_set(candidates, {'min_seconds':15, 'max_seconds':60, 'max_stories':4,
                                                       'min_spacing_seconds':45, 'max_per_topic':1})
    ids = [row['candidate_id'] for row in selected]
    assert len(selected) >= 3
    assert 'AD' not in ids
    assert not ({'A','B'} <= set(ids))
    assert len({row['story_category'] for row in selected}) >= 3
    assert metrics['selected_count'] == len(selected)


def test_social_output_has_all_aspect_ratios_titles_caption_safe_area_and_font():
    cfg = deepcopy(DEFAULTS)
    cfg['social_output'].update(aspect_ratio='4:5', caption_preset='karaoke', content_mode='entrevista',
                                caption_font='Montserrat', caption_size_scale=1.2)
    cfg['social_output']['stories'].update(max_stories=2)
    analysis = {
        'second_curation_package': {'candidates': [candidate('A', 0), candidate('C', 100, 'humor', 'T2')]},
        'broadcast_graphics': {'intervals':[{'start':0,'end':50,'regions':[{'kind':'lower_third','persistent':True,'y_start':.7,'y_end':.9}]}]},
    }
    result = build_social_output(analysis, cfg, analysis['second_curation_package'])
    assert set(result['available_aspect_ratios']) == set(ASPECT_RATIOS)
    assert result['selected_aspect_ratio'] == '4:5'
    assert len(result['stories']) == 2
    first = result['stories'][0]
    assert first['aspect_ratio'] == '4:5'
    assert first['caption_plan']['preset'] == 'karaoke'
    assert first['caption_plan']['font_family'] == 'Montserrat'
    assert first['caption_plan']['size_scale'] == 1.2
    assert first['caption_plan']['preferred_position'] == 'upper_middle'
    assert first['caption_plan']['avoid_faces'] is True
    assert first['title_variants']


def test_social_config_rejects_bad_ratio_and_accepts_supported_ratios():
    for ratio in ASPECT_RATIOS:
        cfg = deepcopy(DEFAULTS); cfg['social_output']['aspect_ratio'] = ratio; validate(cfg)
    cfg = deepcopy(DEFAULTS); cfg['social_output']['aspect_ratio'] = '3:2'
    try:
        validate(cfg)
    except ValueError as exc:
        assert 'aspect_ratio' in str(exc)
    else:
        raise AssertionError('invalid ratio must fail')


def test_second_curation_core_exposes_social_story_contract(tmp_path):
    import json, zipfile
    from test_v43_handoff import analysis_fixture
    from ldporto.second_curation import build_second_curation_package
    from ldporto.second_curation_export import build_core_package
    cfg = deepcopy(DEFAULTS)
    analysis = analysis_fixture()
    package = build_second_curation_package(analysis)
    analysis['second_curation_package'] = package
    analysis['social_output'] = build_social_output(analysis, cfg, package)
    result = build_core_package(analysis, output_dir=tmp_path, package=package)
    with zipfile.ZipFile(result['path']) as archive:
        names = set(archive.namelist())
        assert {'social/stories_manifest.json', 'social/stories_candidates.json',
                'social/title_suggestions.json', 'social/caption_style_recommendations.json',
                'social/render_profiles.json'} <= names
        manifest = json.loads(archive.read('social/stories_manifest.json'))
        index = json.loads(archive.read('CURATION_INDEX.json'))
        assert manifest['mode'] == 'multiple_independent_stories'
        assert index['stories_ref'] == 'social/stories_manifest.json'
        assert index['selected_aspect_ratio'] == '9:16'
