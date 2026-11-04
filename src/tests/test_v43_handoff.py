from copy import deepcopy

from ldporto.second_curation import build_second_curation_package


def analysis_fixture():
    return {'metadata': {'duration': 120, 'width': 1920, 'height': 1080, 'fps': 30, 'sha256': 'fixture',
                         'source': {'title': 'Synthetic episode', 'type': 'local'}},
            'analysis_status': 'partial', 'words': [],
            'transcript_segments': [{'segment_id': 'S0', 'start': 0, 'end': 30, 'speaker': 'SP1', 'text': 'Contexto anterior.'},
                                    {'segment_id': 'S1', 'start': 30, 'end': 90, 'speaker': 'SP1', 'text': 'Uma explicacao completa sobre a carreira.'},
                                    {'segment_id': 'S2', 'start': 90, 'end': 120, 'speaker': 'SP1', 'text': 'Contexto posterior.'}],
            'speakers': [{'speaker_id': 'SP1', 'speech_seconds': 120}], 'people': [], 'person_identities': [],
            'participants': [{'participant_id': 'PART1', 'speaker_ids': ['SP1'], 'person_id': None}],
            'topics': [{'topic_id': 'T1', 'start': 0, 'end': 120, 'topic': 'Carreira musical', 'summary': 'Uma discussao sobre carreira.'}],
            'main_moments': [{'moment_id': 'M1', 'ideal_start': 30, 'ideal_end': 90, 'topic_id': 'T1',
                              'core_moment': {'start': 30, 'end': 90, 'text': 'Uma explicacao completa sobre a carreira.'},
                              'clean_opening': True, 'clean_ending': True, 'standalone_score': .8,
                              'content_type': 'editorial_content', 'context_requirement': 'none',
                              'evidence_segment_ids': ['S1'], 'default_shortlist_eligible': True}],
            'editorial_shortlist': ['M1'], 'analysis_quality': {}, 'issues': [],
            'audio_analysis': {'quality_windows': [{'start': 0, 'end': 120, 'rms_dbfs': -20, 'clipping_fraction': .001}],
                               'silences': [{'start': 30, 'end': 33}]},
            'shots': [{'shot_id': 'SHOT1', 'start': 0, 'end': 120}],
            'video_analysis': {'frame_samples': [{'time': 60, 'blur_laplacian_variance': 100}]}}


def test_second_curation_propagates_topic_context_quality_and_explicit_null_person():
    package = build_second_curation_package(analysis_fixture())
    candidate = package['candidates'][0]
    assert candidate['topic'] == 'Carreira musical'
    assert candidate['standalone_assessment']
    assert candidate['audio_quality']['rms_dbfs'] == -20
    assert candidate['technical_quality']['source_resolution'] == [1920, 1080]
    assert candidate['context_before'] and candidate['context_after']
    assert candidate['person_id'] is None and candidate['person_resolution_reason'] == 'speaker_person_unresolved'
    assert candidate['generated_copy']['status'] == 'not_generated_by_analyzer'


def test_second_curation_tolerates_legacy_editorial_review_list():
    analysis = analysis_fixture()
    analysis['ollama_editorial_review'] = [{
        'moment_id': 'M1', 'hook_text': 'Hook revisado', 'title_idea': 'Titulo revisado',
        'editorial_score': .9, 'why': 'fixture'
    }]
    candidate = build_second_curation_package(analysis)['candidates'][0]
    assert candidate['generated_copy']['hook_idea'] == 'Hook revisado'
    assert candidate['generated_copy']['title_idea'] == 'Titulo revisado'


def test_second_curation_propagates_resolved_person_and_smart_camera_metadata():
    analysis = analysis_fixture()
    analysis['people'] = [{'person_id': 'P1'}]
    analysis['active_speaker'] = [{'start': 30, 'end': 90, 'person_id': 'P1', 'speaker_id': 'SP1'}]
    analysis['camera_director_timeline'] = [{'director_id': 'D1', 'start': 30, 'end': 90, 'focus_person': 'P1',
        'layout': 'single_person', 'camera_mode': 'SMART_ZOOM_IN', 'camera': {'zoom_start': 1, 'zoom_end': 1.2},
        'crop': {'safe': True}, 'decision': {'reasons': ['HOOK_EMPHASIS']}}]
    candidate = build_second_curation_package(analysis)['candidates'][0]
    assert candidate['person_ids'] == ['P1']
    assert candidate['director_segments'][0]['camera_mode'] == 'SMART_ZOOM_IN'
    assert candidate['director_segments'][0]['zoom_end'] == 1.2


def test_core_package_includes_all_candidates_transcript_context_and_no_dangling_refs(tmp_path):
    import zipfile
    from ldporto.second_curation_export import build_core_package, validate_core_package
    analysis = analysis_fixture()
    second = deepcopy(analysis['main_moments'][0])
    second.update(moment_id='M2', ideal_start=0, ideal_end=30)
    analysis['main_moments'].append(second)
    result = build_core_package(analysis, output_dir=tmp_path)
    assert result['state'] == 'PARTIAL'
    assert result['candidate_count'] == 2
    assert result['bytes'] < 2 * 1024 * 1024
    assert not result['expensive_inference_executed']
    validation = validate_core_package(result['path'])
    assert validation['checksums_valid'] and validation['dangling_references'] == 0
    with zipfile.ZipFile(result['path']) as archive:
        assert {'SECOND_CURATOR_BRIEF.json', 'transcript/transcript.txt', 'transcript/transcript.srt', 'candidates/M1.json', 'candidates/M2.json'} <= set(archive.namelist())
        brief = __import__('json').loads(archive.read('SECOND_CURATOR_BRIEF.json'))
        assert brief['task'] == 'second_editorial_curation' and brief['candidate_count'] == 2
        assert brief['target_duration_seconds'] == {'preferred_min': 30, 'preferred_max': 90}
        assert brief['capability_reasons']['visual_ready'] == 'shortlist_visual_evidence_incomplete'
        index = __import__('json').loads(archive.read('CURATION_INDEX.json'))
        assert index['second_curation_readiness_reasons']['visual_ready'] == 'shortlist_visual_evidence_incomplete'
        assert 'CURATION_INDEX.json' in brief['recommended_entrypoints']
        assert not any(name.endswith('.mp4') or '.venv' in name for name in archive.namelist())


def test_real_contact_sheet_enables_visual_ready_and_ready_naming(tmp_path):
    import cv2
    import numpy as np
    from ldporto.second_curation_export import build_core_package, validate_core_package
    source = tmp_path / 'source with spaces.mp4'
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'mp4v'), 10, (320, 180))
    assert writer.isOpened()
    for index in range(100):
        frame = np.full((180, 320, 3), (index + 50) % 200, dtype=np.uint8)
        cv2.rectangle(frame, (40 + index // 5, 40), (160 + index // 5, 140), (20, 170, 220), -1)
        writer.write(frame)
    writer.release()
    analysis = analysis_fixture()
    analysis['metadata'].update(duration=10, width=320, height=180)
    analysis['transcript_segments'] = [{'segment_id': 'S1', 'start': 0, 'end': 10, 'speaker': 'SP1', 'text': 'Uma explicacao completa sobre a carreira.'}]
    analysis['topics'][0].update(start=0, end=10)
    analysis['main_moments'][0].update(ideal_start=0, ideal_end=10)
    analysis['main_moments'][0]['core_moment'].update(start=0, end=10)
    result = build_core_package(analysis, source, tmp_path / 'packages', {'include_candidate_previews':True})
    assert result['state'] == 'READY' and result['readiness']['visual_ready']
    assert 'SECOND_CURATION_READY_' in result['path']
    assert validate_core_package(result['path'])['visual_count'] == 1
    import zipfile
    assert result['media_path'] and result['media_preview_count'] == 1
    with zipfile.ZipFile(result['path']) as core, zipfile.ZipFile(result['media_path']) as media:
        assert not any(name.endswith('.mp4') for name in core.namelist())
        assert 'previews/M1.mp4' in media.namelist()


def test_package_validator_rejects_tampered_checksum_and_missing_actual_jpg(tmp_path):
    import json
    import zipfile
    from ldporto.second_curation_export import build_core_package, validate_core_package
    result = build_core_package(analysis_fixture(), output_dir=tmp_path)
    corrupted = tmp_path / 'corrupted.zip'
    with zipfile.ZipFile(result['path']) as source, zipfile.ZipFile(corrupted, 'w') as target:
        for name in source.namelist():
            data = b'changed transcript' if name == 'transcript/transcript.txt' else source.read(name)
            target.writestr(name, data)
    validation = validate_core_package(corrupted)
    assert validation['status'] == 'failed' and not validation['checksums_valid']


def test_core_package_redacts_tokens_and_private_paths(tmp_path):
    import zipfile
    from ldporto.second_curation_export import build_core_package
    analysis = analysis_fixture()
    secret = 'hf_' + 'z' * 32
    analysis['transcript_segments'][1]['text'] += ' ' + secret + ' C:\\Users\\Private\\video.mp4'
    result = build_core_package(analysis, output_dir=tmp_path)
    with zipfile.ZipFile(result['path']) as archive:
        text = archive.read('transcript/transcript.txt').decode('utf-8')
    assert secret not in text and 'C:\\Users\\Private' not in text
    assert '[REDACTED_SECRET]' in text and '[PRIVATE_PATH]' in text