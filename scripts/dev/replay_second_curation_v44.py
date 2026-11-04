"""Real evidence package + promoted visual, separately labelled downstream replay."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.compact_artifacts import load_analysis_artifacts
from ldporto.second_curation_export import build_core_package, generate_visuals_on_demand


def main():
    baseline = ROOT / 'analysis/video_31329be78ca4'
    output = ROOT / '.cache/v44_validation/P1_second_curation_replay'
    output.mkdir(parents=True, exist_ok=True)
    analysis = load_analysis_artifacts(baseline, ['words', 'transcript_segments', 'speakers', 'people', 'person_identities',
        'participants', 'topics', 'entities', 'shots', 'questions_answers', 'question_answer_pairs', 'program_sections',
        'main_moments', 'editorial_moments', 'story_arcs', 'low_confidence_words'])
    read = lambda path: json.loads(path.read_text(encoding='utf-8-sig'))
    cache = ROOT / '.cache/v44_validation'
    analysis.update(execution_scope='second_curation_snapshot_replay',
        main_moments=read(cache / 'P0C_commercial_replay/main_moments.json'),
        story_arcs=read(cache / 'P0D_story_replay/story_arcs.json'),
        active_speaker=read(cache / 'P0A_audio_replay/active_speaker.json'),
        speaker_person_summary=read(cache / 'P0A_audio_replay/speaker_person_summary.json'),
        camera_director_timeline=read(cache / 'P0B_camera_replay/camera_director_timeline.json'),
        preview_validation={'status': 'not_validated_v44', 'verifier_uses_rendered_frames': False})
    analysis['analysis_quality'].update(read(cache / 'P0B_camera_replay/camera_replay_metrics.json')['metrics'])
    source = ROOT / 'input/youtube/yZ78vCgiPZk/yZ78vCgiPZk.mp4'
    report = build_core_package(analysis, source=source, output_dir=output, cfg={'second_curation_visual_candidate_limit': 12})
    candidates = [r for r in analysis['main_moments'] if r['moment_id'] not in analysis.get('editorial_shortlist', [])
                  and r['commercial_classification']['eligibility'] == 'eligible' and 7650 <= r['ideal_start'] < 7900]
    if not candidates:
        candidates = [r for r in analysis['main_moments'] if r['moment_id'] not in analysis.get('editorial_shortlist', []) and r['commercial_classification']['eligibility'] == 'eligible']
    promoted = candidates[0]
    visuals = generate_visuals_on_demand(report['path'], source, [promoted['moment_id']], output / 'promoted')
    document = {'schema_version': '4.4.0', 'source_sha256': analysis['metadata']['sha256'], 'provider': 'manual_json',
                'input_package_sha256': __import__('ldporto.core', fromlist=['file_hash']).file_hash(visuals['path']),
                'notes': ['Decisão de validação local do fluxo; revisão editorial completa independente permanece pendente.'],
                'actions': [{'decision_id': 'VALIDATION_PROMOTED_01', 'action': 'promote', 'candidate_ids': [promoted['moment_id']],
                             'reason': 'Candidato fora da shortlist com desfecho literal; validar importação e preview.',
                             'title': 'O que aconteceu depois da palestra'}]}
    (output / 'SECOND_CURATION_DECISIONS.json').write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
    report = {'execution_scope': 'second_curation_snapshot_replay', 'package': report, 'promoted_visuals': visuals,
              'promoted_candidate_id': promoted['moment_id'], 'decision_scope': 'integration_validation_not_final_editorial_selection'}
    (output / 'second_curation_replay_metrics.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'candidate_count': report['package']['candidate_count'], 'shortlist_count': report['package']['shortlist_count'],
                      'state': report['package']['state'], 'promoted_candidate': promoted['moment_id'], 'path': visuals['path']}))


if __name__ == '__main__':
    main()
