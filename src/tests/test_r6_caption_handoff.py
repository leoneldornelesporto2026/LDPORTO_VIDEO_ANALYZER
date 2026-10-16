"""R6 package triage uses only synthetic canonical rows; no models or media."""
from copy import deepcopy
import hashlib
import json
import zipfile

import pytest

from ldporto.subtitle_review import build_caption_preflight, build_story_interval_preflight, CAPTION_PREFLIGHT_PATH
from ldporto.second_curation_export import build_core_package, validate_core_package


def word(text='Teste.', **extra):
    return dict(word_id='W1', segment_id='S1', word=text, start=1., end=2.,
                confidence=.95, needs_review=False, **extra)


def preflight(words=(), segments=(), **extra):
    return build_caption_preflight(list(words), list(segments),
        [{'candidate_id': 'C1', 'start': 0., 'end': 4.}], duration=10., **extra)['candidates']['C1']


@pytest.mark.parametrize('words,segments,events,status', [
    ([word(alignment_verified=True, audio_verified=True)], [], [], 'CAPTION_READY'),
    ([word(audio_verified=True)], [], [], 'PHRASE_SUBTITLE_ONLY'),
    ([word()], [], [], 'AUDIO_REVIEW_REQUIRED'),
    ([], [dict(segment_id='S1', start=0., end=4., text='Uma frase longa que não tem palavras alinhadas.')], [], 'ALIGNMENT_REVIEW_REQUIRED'),
    ([], [], [dict(type='INSTRUMENTAL', start=0., end=4.)], 'INSTRUMENTAL_NO_CAPTION'),
    ([], [], [], 'BLOCKED'),
])
def test_states_do_not_grant_publication_or_fabricate_word_times(words, segments, events, status):
    before = deepcopy((words, segments, events))
    result = preflight(words, segments, events=events)
    assert result['status'] == status
    assert result['human_approved'] is False and result['publication_ready'] is False
    assert result['subtitle_publish_ready'] is False
    assert (words, segments, events) == before


def test_generic_music_or_partial_or_conflicting_instrumental_is_not_no_caption():
    for events in ([dict(type='music', start=0., end=4.)],
                   [dict(type='INSTRUMENTAL', start=0., end=3.)],
                   [dict(type='INSTRUMENTAL', start=0., end=4.), dict(type='SINGING', start=1., end=2.)]):
        assert preflight(events=events)['status'] == 'BLOCKED'


def test_even_verified_long_token_needs_layout_review():
    result = preflight([word('X'*80, alignment_verified=True, audio_verified=True)])
    assert result['status'] == 'BLOCKED'
    assert 'caption_text_layout_requires_review' in result['reason_codes']
    assert result['karaoke_allowed'] is False


def test_explicit_mixed_audio_keeps_listening_gate_even_with_verified_words():
    result = preflight([word(alignment_verified=True, audio_verified=True)],
        events=[dict(type='MIXED_AUDIO', start=0., end=4.)])
    assert result['status'] == 'AUDIO_REVIEW_REQUIRED'
    assert result['audio_categories_observed'][0]['category'] == 'MIXED_AUDIO'


def test_partial_word_tokens_do_not_certify_whole_long_canonical_segment():
    segment = dict(segment_id='S1', start=0., end=8., text='Primeira segunda terceira quarta quinta sexta.')
    result = preflight([word('Primeira', alignment_verified=True, audio_verified=True)], [segment])
    assert result['status'] == 'ALIGNMENT_REVIEW_REQUIRED'
    assert result['unaligned_long_segment_ids'] == ['S1']
    assert result['word_evidence_seconds'] == 1.
    assert result['word_evidence_gaps'] == [dict(start=0., end=1., reason='no_word_timestamp_evidence'),
                                           dict(start=2., end=4., reason='no_word_timestamp_evidence')]


def test_story_is_rechecked_with_own_bounds_and_invalid_range_is_blocked():
    words = [word(alignment_verified=True, audio_verified=True)]
    report = build_caption_preflight(words, [], [{'candidate_id': 'C1', 'start': 0., 'end': 4.}],
        [dict(story_id='ST1', candidate_id='C1', start=1.5, end=3.),
         dict(story_id='ST2', candidate_id='C1', start=5., end=11.)], duration=10.)
    assert report['candidates']['C1']['status'] == 'CAPTION_READY'
    assert report['stories']['ST1']['status'] == 'ALIGNMENT_REVIEW_REQUIRED'
    assert report['stories']['ST2']['status'] == 'BLOCKED'
    assert report['new_asr_calls'] == 0


def test_discontinuous_story_never_includes_gap_words_or_inherits_montage_approval():
    rows = [word(alignment_verified=True, audio_verified=True),
            {**word(alignment_verified=True, audio_verified=True), 'word_id': 'W_GAP', 'start': 25., 'end': 26.},
            {**word(alignment_verified=True, audio_verified=True), 'word_id': 'W2', 'start': 51., 'end': 52.}]
    story = dict(story_id='CANONICAL_STORY', source_intervals=[dict(start=0., end=4.), dict(start=50., end=54.)])
    result = build_story_interval_preflight(rows, [], [story], duration=60.)['stories']['CANONICAL_STORY']
    assert result['start'] is result['end'] is None
    assert result['assembled_duration_seconds'] == 8.
    assert result['canonical_word_ids'] == ['W1', 'W2']
    assert all(r['preflight']['status'] == 'CAPTION_READY' for r in result['interval_reviews'])
    assert result['status'] == 'AUDIO_REVIEW_REQUIRED' and result['karaoke_allowed'] is False
    assert result['publication_ready'] is False


@pytest.mark.parametrize('intervals', [[], [dict(start=0., end=30.), dict(start=29., end=40.)],
    [dict(start=50., end=55.), dict(start=0., end=4.)], [dict(start=0., end=61.)]])
def test_story_missing_overlapping_reordered_or_overlong_intervals_are_blocked(intervals):
    report = build_story_interval_preflight([], [], [dict(story_id='ST1', source_intervals=intervals)], duration=120.)
    assert report['stories']['ST1']['status'] == 'BLOCKED'


def test_semantic_contract_uses_existing_story_ids_and_separate_source_intervals():
    from test_r51_semantic_package import sample
    from ldporto.semantic_package import semantic_caption_preflight
    legacy, additions = sample()
    report = semantic_caption_preflight({**legacy, **additions})
    incoming = [s for series in additions['editorial/story_series_proposals.json']['series'] for s in series['stories']]
    assert incoming and set(report['stories']) == {s['story_id'] for s in incoming}
    for story in incoming:
        reviewed = report['stories'][story['story_id']]
        assert reviewed['source_intervals'] == story['source_intervals']
        assert len(reviewed['interval_reviews']) == len(story['source_intervals'])
        assert reviewed['start'] is reviewed['end'] is None
    assert report['new_asr_calls'] == 0


def package_fixture():
    from test_v43_handoff import analysis_fixture
    analysis = analysis_fixture()
    analysis['main_moments'].append({**deepcopy(analysis['main_moments'][0]),
        'moment_id': 'M2', 'ideal_start': 0., 'ideal_end': 30., 'evidence_segment_ids': ['S0'],
        'default_shortlist_eligible': False})
    analysis['main_moments'][0]['alternates'] = [dict(moment_id='M1_ALT', ideal_start=31., ideal_end=88.,
        evidence_segment_ids=['S1'])]
    # Existing S7 reviewed only one cut. R6 must cover the other cuts too.
    analysis['subtitle_review_s7'] = {'selected_candidate_count': 1,
        'candidates': {'M1': {'approval_state': 'HUMAN_AUDIO_REVIEW_REQUIRED'}}}
    return analysis


def test_package_indexes_every_exported_candidate_without_changing_shortlist_or_s7(tmp_path):
    analysis = package_fixture()
    original = deepcopy(analysis)
    result = build_core_package(analysis, output_dir=tmp_path)
    assert analysis == original
    with zipfile.ZipFile(result['path']) as archive:
        report = json.loads(archive.read(CAPTION_PREFLIGHT_PATH))
        master = json.loads(archive.read('HANDOFF_MASTER.json'))
        catalog = json.loads(archive.read('editorial/candidate_catalog.json'))
        assert set(report['candidates']) == {'M1', 'M2', 'M1_ALT'}
        assert report['candidate_count'] == len(catalog['candidates']) == 3
        assert all(c['caption_preflight']['status'] == 'ALIGNMENT_REVIEW_REQUIRED' for c in catalog['candidates'])
        assert json.loads(archive.read('subtitles/subtitle_review_s7.json')) == analysis['subtitle_review_s7']
        assert master['publication_ready'] is master['preview_approved'] is master['human_approved'] is False
        for row in master['artifacts']:
            assert hashlib.sha256(archive.read(row['path'])).hexdigest() == row['sha256']
        assert json.loads(archive.read('editorial/default_shortlist.json'))['candidate_ids'] == ['M1']
    assert validate_core_package(result['path'])['status'] == 'valid'


def test_package_story_preflight_and_shared_camera_and_people_remain_additive(tmp_path):
    analysis = package_fixture()
    analysis['social_output'] = {'stories': [dict(story_id='ST1', candidate_id='M1', start=30., end=60.,
        duration=30., title='Uma explicacao completa sobre a carreira.') ]}
    result = build_core_package(analysis, output_dir=tmp_path)
    with zipfile.ZipFile(result['path']) as archive:
        report = json.loads(archive.read(CAPTION_PREFLIGHT_PATH))
        stories = json.loads(archive.read('social/stories_manifest.json'))['stories']
        assert report['story_count'] == 1
        assert report['stories']['ST1']['start'] == 30. and report['stories']['ST1']['end'] == 60.
        assert stories[0]['caption_preflight']['status'] == 'ALIGNMENT_REVIEW_REQUIRED'
        assert stories[0]['camera_handoff']['source_intervals'] == [dict(start=30., end=60.)]
        camera = json.loads(archive.read('camera/candidate_camera_plans.json'))
        assert isinstance(camera, list) and len(camera) == 3
        assert camera[0]['camera_handoff']['camera_engine'] == 'ldporto.camera_director'
        shared = json.loads(archive.read('camera/shared_camera_handoff.json'))
        assert shared['applies_to'] == ['REEL', 'STORY']
        for name in ('person_tracks', 'person_appearances', 'instrument_observations', 'speaker_person_mapping', 'performer_review_queue'):
            assert isinstance(json.loads(archive.read('people/'+name+'.json')), list)
        participant = json.loads(archive.read('people/participants.json'))[0]
        assert participant['participant_id'] == 'PART1'
        assert participant['civil_identity_confirmed'] is False


def rewrite_package(source, destination, mutate, *, repair_master=False):
    with zipfile.ZipFile(source) as archive:
        payloads = {name: archive.read(name) for name in archive.namelist()}
    mutate(payloads)
    if repair_master:
        master = json.loads(payloads['HANDOFF_MASTER.json'])
        for row in master['artifacts']:
            data = payloads[row['path']]
            row.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        payloads['HANDOFF_MASTER.json'] = json.dumps(master).encode()
    # Even an updated outer checksum cannot legitimize false preflight evidence.
    manifest = json.loads(payloads['SECOND_CURATION_MANIFEST.json'])
    for row in manifest['files']:
        data = payloads[row['path']]
        row.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    payloads['SECOND_CURATION_MANIFEST.json'] = json.dumps(manifest).encode()
    with zipfile.ZipFile(destination, 'w') as archive:
        for name, data in payloads.items():
            archive.writestr(name, data)


@pytest.mark.parametrize('kind', ['preflight', 'master_hash', 'master_gate', 'missing_candidate'])
def test_validator_rejects_false_preflight_missing_candidates_and_master_tampering(tmp_path, kind):
    result = build_core_package(package_fixture(), output_dir=tmp_path/'source')
    def mutate(payloads):
        path = CAPTION_PREFLIGHT_PATH if kind in {'preflight', 'missing_candidate'} else 'HANDOFF_MASTER.json'
        document = json.loads(payloads[path])
        if kind == 'preflight':
            document['candidates']['M2']['status'] = 'CAPTION_READY'
        elif kind == 'missing_candidate':
            del document['candidates']['M2']
        elif kind == 'master_hash':
            document['artifacts'][0]['sha256'] = '0' * 64
        else:
            document['publication_ready'] = True
        payloads[path] = json.dumps(document).encode()
    destination = tmp_path/'tampered.zip'
    rewrite_package(result['path'], destination, mutate, repair_master=kind in {'preflight', 'missing_candidate'})
    validation = validate_core_package(destination)
    assert validation['status'] == 'failed'
    assert any(error.startswith('r6:') for error in validation['errors'])
