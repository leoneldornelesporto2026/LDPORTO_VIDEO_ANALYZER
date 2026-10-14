"""CPU component refinement and new curator ZIP; original analysis is read-only."""
from pathlib import Path
import hashlib
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
REPORT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'src'))


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(4*1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def main():
    from ldporto.core import digest
    from ldporto.semantic import qa_contract
    from ldporto.understanding import recover_dialogue_links, build_story_arcs, _validate_story_arcs_contract
    from ldporto.second_curation_export import build_core_package, validate_core_package
    folder = ROOT/'analysis/video_1da839aad175'
    preservation = json.loads((REPORT/'preservation_before.json').read_text(encoding='utf-8'))['analysis_files']
    input_hashes = {}
    def read(name):
        path = folder/name
        actual = sha(path)
        if actual != preservation[name]['sha256']:
            raise ValueError('changed_original_input:' + name)
        input_hashes[name] = actual
        return json.loads(path.read_text(encoding='utf-8-sig'))
    analysis = read('analysis.json')
    # Load the evidence needed by existing contracts, never facial embeddings.
    keys = ['words', 'transcript_segments', 'speakers', 'speaker_turns', 'speech_overlaps',
        'speaker_person_summary', 'shots', 'scenes', 'topics', 'program_sections', 'participants',
        'entities', 'story_arcs', 'main_moments', 'questions_answers', 'question_candidates',
        'question_answer_pairs', 'camera_director_timeline', 'transcription_alternatives',
        'low_confidence_words', 'source_audio_review', 'transcription_hypothesis_comparison',
        'commercial_visual_s8']
    for key in keys:
        reference = analysis.get('collection_refs', {}).get(key)
        if reference:
            analysis[key] = read(reference['path'])
    with __import__('zipfile').ZipFile(ROOT/'pacotes_para_enviar/SECOND_CURATION_PARTIAL_7laRa_F3FbA_20261013_140239_076346_6beb9d.zip') as archive:
        analysis['person_identities'] = json.loads(archive.read('people/person_identities.json'))
    before_qas = analysis['questions_answers']
    before_stories = analysis['story_arcs']
    before_moments_sha = digest(analysis['main_moments'])
    before_source_review_sha = digest(analysis['source_audio_review'])
    started = time.perf_counter()
    qas, diagnostic = recover_dialogue_links({'segments':analysis['transcript_segments']}, before_qas, analysis['topics'])
    qa_seconds = time.perf_counter()-started
    started = time.perf_counter()
    stories = build_story_arcs({'segments':analysis['transcript_segments']}, analysis['topics'], qas)
    stories, contract = _validate_story_arcs_contract(stories, analysis['transcript_segments'])
    story_seconds = time.perf_counter()-started
    if {r['story_arc_id'] for r in stories} != {r['story_arc_id'] for r in before_stories}:
        raise ValueError('story_id_set_changed_requires_separate_review')
    analysis.update(questions_answers=qas, story_arcs=stories, dialogue_diagnostics=diagnostic, **qa_contract(qas))
    # Add diagnostics to the derived package; do not pretend this was a new full run.
    analysis['post_homologation_scope'] = 'CPU_dialogue_and_curator_export_only_no_model_inference'
    destination = REPORT/'derived_export'
    if destination.exists():
        raise RuntimeError('derived_export_exists_no_overwrite')
    started = time.perf_counter()
    result = build_core_package(analysis, source=None, output_dir=destination,
        cfg={'second_curation_visual_candidate_limit':0, 'include_candidate_previews':False})
    export_seconds = time.perf_counter()-started
    validation = validate_core_package(Path(result['path']))
    record = {'state':'VERIFIED' if validation['status']=='valid' else 'FAILED',
        'input_sha256': input_hashes, 'scope':analysis['post_homologation_scope'],
        'qa_seconds':qa_seconds, 'story_seconds':story_seconds, 'export_seconds':export_seconds,
        'qas_before':len(before_qas), 'qas_after':len(qas), 'qa_ids_preserved':
            [r['question_id'] for r in before_qas]==[r['question_id'] for r in qas],
        'qas_exactly_preserved':digest(before_qas)==digest(qas), 'dialogue_diagnostics':diagnostic,
        'stories_before':len(before_stories), 'stories_after':len(stories),
        'narratives_before':sum(r.get('narrative_supported')is True for r in before_stories),
        'narratives_after':sum(r.get('narrative_supported')is True for r in stories),
        'story_contract_events':contract, 'candidate_payload_unchanged':before_moments_sha==digest(analysis['main_moments']),
        'source_audio_review_unchanged':before_source_review_sha==digest(analysis['source_audio_review']),
        'result':result, 'validation':validation, 'new_model_calls':0, 'publication_ready':False}
    (REPORT/'curator_export_replay.json').write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({key:record[key]for key in ['state','qa_seconds','story_seconds','export_seconds','qas_before','qas_after','qas_exactly_preserved','stories_after','narratives_after','candidate_payload_unchanged','source_audio_review_unchanged']}))
    print(json.dumps({'path':result['path'],'candidate_count':result['candidate_count'],'shortlist_count':result['shortlist_count'],'validation':validation['status']}))


if __name__ == '__main__':
    main()
