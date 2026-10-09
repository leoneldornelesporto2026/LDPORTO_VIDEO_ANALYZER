"""Compatible downstream replay; imported snapshots are not fresh inference."""
from pathlib import Path
import copy
import logging
import math
import time

from . import __version__
from .core import Context, digest, file_hash, ok, read_json, setup_logging, output_lock, logging_session
from .compact_artifacts import COLLECTION_FILES
from .editorial import topic_hierarchy, normalize_moment
from .semantic import questions_answers, qa_contract, SemanticEngine
from .understanding import run_understanding
from .analysis_quality import build_analysis_quality
from .director_integration import run_planner_stage, run_director_stage, attach_director
from .preview_integration import run_preview_stage
from .reports import ReportEngine


REPLAY_STAGES = ('speaker_person', 'active_speaker', 'semantic', 'commercial', 'understanding', 'ranking', 'camera', 'camera_director', 'preview_verifier', 'second_curation', 'handoff')


def replay_plan(from_stage):
    """Describe this runner's scope, without claiming an inference/cache hit."""
    if from_stage not in REPLAY_STAGES:
        raise ValueError('Unsupported replay stage.')
    stages = []
    if from_stage == 'semantic':
        stages.append('15_semantic')
    elif from_stage in ('speaker_person', 'active_speaker'):
        stages.append('10_active_speaker')
    if from_stage in ('speaker_person', 'active_speaker', 'semantic', 'commercial', 'understanding', 'ranking'):
        stages.append('16_understanding')
    stages.extend(['18b_global_camera_planner', '19_camera_director', '19b_preview_verifier'])
    return {'schema_version': '1.0', 'from_stage': from_stage,
            'stages_to_check': stages, 'exports_to_refresh': ['captions', 'reports', 'second_curation'],
            'snapshot_only': ['04_transcription', '07_people_tracking', '08_person_reid'],
            'semantic_snapshot_only': from_stage != 'semantic',
            'cache_hits': None, 'approval_inherited': False}


def understanding_replay_params(config, metadata, transcript, diarization, vision, active, semantic, shots):
    """Hash actual arguments, not the unrelated set of files read for export.

    Includes computed semantic/active results; a snapshot checksum alone cannot
    identify those. The new contract conservatively misses old downstream caches.
    """
    return {'config': config, 'replay_input_contract': '1.0',
            'inputs': digest({'metadata': metadata, 'transcript': transcript,
                              'diarization': diarization, 'vision': vision,
                              'active': active, 'semantic': semantic, 'shots': shots})}


def resolve_replay_folder(value):
    folder = Path(value).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError('Replay requires an extracted analysis directory.')
    if (folder / 'analysis_summary.json').is_file() or (folder / 'analysis.json').is_file():
        return folder
    candidates = sorted({path.parent for path in folder.glob('analysis/*/analysis_summary.json')})
    if len(candidates) != 1:
        raise ValueError('Replay source is ambiguous; specify one analysis directory.')
    return candidates[0]


class ReplayArtifacts:
    def __init__(self, folder, expected_source_hash=None, allow_legacy_snapshot=False):
        self.folder = resolve_replay_folder(folder)
        self.document = read_json(self.folder / 'analysis.json') if (self.folder / 'analysis.json').is_file() else {}
        self.summary = read_json(self.folder / 'analysis_summary.json') if (self.folder / 'analysis_summary.json').is_file() else self.document
        self.metadata = self.summary.get('metadata') or self.document.get('metadata') or {}
        version = str(self.metadata.get('analyzer_version') or self.summary.get('producer_version') or '')
        if not version.startswith(('4.3', '4.4')) and not allow_legacy_snapshot:
            raise ValueError('Legacy replay requires --allow-legacy-snapshot; not a current prompt/model cache.')
        if self.metadata.get('schema_version') not in ('2.0', '4.2', '4.3'):
            raise ValueError('Unsupported replay artifact schema.')
        source_hash = self.metadata.get('sha256')
        if not source_hash or expected_source_hash and source_hash != expected_source_hash:
            raise ValueError('Replay source hash mismatch or missing.')
        if not isinstance(self.metadata.get('duration'), (int, float)) or not math.isfinite(self.metadata['duration']) or self.metadata['duration'] <= 0:
            raise ValueError('Replay source duration invalid.')
        self.source_hash = source_hash
        self.checksums = {}
        self.verified = {}
        self.projections = []
        local_manifest = self.folder / 'manifest.json'
        if local_manifest.is_file():
            local = read_json(local_manifest)
            for name, checksum in local.get('artifact_checksums', {}).items():
                path = (self.folder / name).resolve()
                if not path.is_relative_to(self.folder):
                    raise ValueError('Unsafe local replay checksum reference.')
                self.checksums[path] = checksum
        export_path = self.folder.parent.parent / 'ANALYSIS_EXPORT_MANIFEST.json'
        if export_path.is_file():
            export = read_json(export_path)
            for row in export.get('files', []):
                path = export_path.parent / row['path']
                if path.resolve().is_relative_to(self.folder) and row.get('sha256'):
                    self.checksums[path.resolve()] = row['sha256']
        for key, reference in self.document.get('collection_refs', {}).items():
            if key not in COLLECTION_FILES or reference.get('path') != COLLECTION_FILES[key]:
                raise ValueError('Unsafe replay collection reference.')
            self.checksums[(self.folder / reference['path']).resolve()] = reference.get('sha256')

    def read(self, name, required=False):
        path = self.folder / name
        if path.is_symlink() or not path.resolve().is_relative_to(self.folder):
            raise ValueError('Unsafe replay artifact path.')
        if not path.is_file():
            if required:
                raise ValueError('Required replay artifact missing: ' + name)
            return None
        expected = self.checksums.get(path.resolve())
        if not expected:
            raise ValueError('Replay artifact has no trusted checksum: ' + name)
        actual = file_hash(path)
        if actual != expected:
            raise ValueError('Replay artifact checksum mismatch: ' + name)
        self.verified[name] = actual
        return read_json(path)

    def projected(self, summary_file, index_key):
        summary = self.read(summary_file)
        projection = (summary or {}).get(index_key) or {}
        if projection.get('format') != 'indexed_json_projection':
            return []
        rows = []
        for reference in projection.get('chunks', []):
            name = reference['path']
            path = (self.folder / name).resolve()
            if not path.is_relative_to(self.folder) or path.is_symlink():
                raise ValueError('Unsafe replay projection chunk.')
            self.checksums[path] = reference.get('sha256')
            payload = self.read(name, required=True)
            rows.extend(payload.get('records', []))
        self.projections.append({'source_artifact': projection.get('source_artifact'),
                                 'not_complete_raw_collection': True, 'record_count': len(rows)})
        return rows

    def validate_transcript(self, words, segments):
        duration = self.metadata['duration']
        segment_ids = [segment.get('segment_id') for segment in segments]
        if not segments or None in segment_ids or len(set(segment_ids)) != len(segment_ids):
            raise ValueError('Replay segment IDs missing or duplicated.')
        for row in words + segments:
            if not all(isinstance(row.get(key), (int, float)) and math.isfinite(row[key]) for key in ('start', 'end')) or not 0 <= row['start'] < row['end'] <= duration + .1:
                raise ValueError('Replay transcript timestamp contract invalid.')
        if any(word.get('segment_id') and word['segment_id'] not in set(segment_ids) for word in words):
            raise ValueError('Replay word references missing segment.')


def replay_analysis(folder, cfg, from_stage='understanding', output=None, source=None,
                    expected_source_hash=None, allow_legacy_snapshot=False, force=False):
    plan_scope = replay_plan(from_stage)
    artifacts = ReplayArtifacts(folder, expected_source_hash, allow_legacy_snapshot)
    from .paths import ANALYSIS_DIR
    output = Path(output or ANALYSIS_DIR / ('replay_v43_' + artifacts.source_hash[:12] + '_' + from_stage)).resolve()
    if output == artifacts.folder or output.is_relative_to(artifacts.folder) or artifacts.folder.is_relative_to(output):
        raise ValueError('Replay output must be separate from immutable inputs.')
    output.mkdir(parents=True, exist_ok=True)
    if source and file_hash(source) != artifacts.source_hash:
        raise ValueError('Replay media source hash mismatch.')
    metadata = {**artifacts.metadata, 'analyzer_version': __version__,
                'upstream_analyzer_version': artifacts.metadata.get('analyzer_version'), 'execution_scope':'downstream_replay'}
    upstream_manifest = artifacts.summary.get('run_manifest') or artifacts.document.get('run_manifest') or {}
    for field in ('run_id', 'analyzer_build', 'code_fingerprint'):
        if upstream_manifest.get(field) is not None:
            metadata[field] = upstream_manifest[field]
    logger = setup_logging(output)
    ctx = Context(Path(source or 'unavailable_source.mp4'), output, copy.deepcopy(cfg), artifacts.source_hash, logger, force)
    ctx.config['understanding']['extract_frames'] = False
    original_states = artifacts.summary.get('stage_status') or {}
    for stage, state in original_states.items():
        ctx.states[stage] = {'status':state.get('status', 'partial'), 'key':digest({'source':artifacts.source_hash, 'stage':stage, 'snapshot':state}),
                             'artifact_snapshot_reused':True, 'upstream_producer':metadata['upstream_analyzer_version']}
        origin = state.get('execution_provenance') or (upstream_manifest.get('stage_status') or {}).get(stage, {}).get('execution_provenance')
        if origin:
            ctx.states[stage]['execution_provenance'] = copy.deepcopy(origin)
        ctx.stage_metrics[stage] = {'elapsed_seconds':None, 'original_elapsed_seconds':(artifacts.summary.get('stage_runtime', {}).get(stage) or {}).get('elapsed_seconds'),
                                   'artifact_snapshot_reused':True, 'executed_in_replay':False}
    words = artifacts.read('words.json', required=True)
    segments = artifacts.read('transcript_segments.json', required=True)
    artifacts.validate_transcript(words, segments)
    quality_original = artifacts.read('analysis_quality.json') or {}
    review_words = []
    for index, word in enumerate(words):
        if word.get('needs_review'):
            review_words.append({**word, 'confidence':word.get('confidence'),
                                 'context_before':' '.join(row.get('word', '') for row in words[max(0, index - 5):index]),
                                 'context_after':' '.join(row.get('word', '') for row in words[index + 1:index + 6]),
                                 'context_source':'canonical_neighbor_words_not_new_asr'})
    transcript = {'words':words, 'segments':segments, 'low_confidence_words':review_words,
                  'quality_metrics':{key:value for key,value in quality_original.items() if not key.startswith('preview_') and any(term in key for term in ('transcription', 'confidence_word', 'timestamp', 'hallucination', 'review_', 'speech_coverage'))}}
    diarization = {'turns':artifacts.read('speaker_turns.json') or [], 'speakers':artifacts.read('speakers.json') or [],
                   'overlaps':artifacts.read('speech_overlaps.json') or [],
                   'alignment_metrics':{key:value for key,value in quality_original.items() if any(term in key for term in ('diarization', 'speaker_fraction', 'overlap_fraction', 'alignment_coverage', 'unmapped_speech'))}}
    people = artifacts.read('people.json') or []
    observations = artifacts.read('people_observations.json')
    if observations is None:
        observations = artifacts.projected('people_summary.json', 'observation_projection')
    video = artifacts.read('video_analysis.json')
    frames = (video or {}).get('frame_samples')
    if frames is None:
        frames = artifacts.projected('CHATGPT_ANALYSIS_HANDOFF.compact.json', 'video_frame_projection')
    scenes = artifacts.read('scenes.json') or []
    shots = artifacts.read('shots.json') or []
    vision = {'people':people, 'observations':observations, 'frames':frames,
              'scene_intervals':[{key:row[key] for key in ('start', 'end', 'scene_id')} for row in scenes], 'thumbnails':[],
              'tracking_metrics':{key:value for key,value in quality_original.items() if any(term in key for term in ('track', 'identity', 'reid', 'embedding', 'persistent_person'))},
              'broadcast_graphics':artifacts.read('broadcast_graphics.json') or {}}
    active = {'intervals':artifacts.read('active_speaker.json') or [], 'mappings':artifacts.read('speaker_person_mapping.json') or [],
              'mapping_summary':artifacts.read('speaker_person_summary.json') or [],
              'metrics':{key:value for key,value in quality_original.items() if any(term in key for term in ('active_speaker', 'speaker_person', 'mapping_', 'unknown_person', 'offscreen'))}}
    audio = artifacts.read('audio_analysis.json') or {}
    topics = artifacts.read('topics.json', required=True)
    moments = artifacts.read('editorial_moments.json') or []
    all_segment_ids = {segment['segment_id'] for segment in segments}
    for row in topics + moments:
        if not set(row.get('evidence_segment_ids', [])) <= all_segment_ids:
            raise ValueError('Replay semantic refs do not resolve to transcript.')
    topics, sections, primary, secondary, topic_quality = topic_hierarchy(topics, segments)
    qas = questions_answers(segments)
    semantic = {'topics':topics, 'moments':[normalize_moment(row) for row in moments], 'program_sections':sections,
                'primary_editorial_theme':primary, 'secondary_editorial_themes':secondary, 'topic_quality':topic_quality,
                'questions_answers':qas, **qa_contract(qas),
                'semantic_metrics':{'semantic_inference_call_count':0, 'semantic_seconds':None,
                                   'semantic_cache_hit_ratio':None, 'execution_basis':'legacy_grounded_snapshot_not_fresh_inference'}}
    started = time.monotonic()
    with logging_session(logger), output_lock(output):
        if from_stage == 'semantic':
            semantic = ctx.step('15_semantic', {'config':ctx.config['semantic_analysis'], 'transcript':digest(transcript)}, lambda: SemanticEngine().run(ctx, transcript),
                                code_files=['semantic.py', 'ollama_local.py', 'editorial.py'], required=True)
        elif from_stage in ('speaker_person', 'active_speaker'):
            from .active_speaker import build_active_speaker
            evidence = artifacts.read('active_speaker_evidence.json')
            if evidence is None:
                raise ValueError('Active speaker replay requires raw mouth/audio evidence; V4.2 review does not supply it. Use a verified fixture or source audio.')
            active = ctx.step('10_active_speaker', {'config':cfg['active_speaker'], 'snapshot':digest(artifacts.verified)},
                             lambda: build_active_speaker(diarization, vision, evidence, cfg['active_speaker']),
                             code_files=['active_speaker.py', 'perception_diagnostics.py', 'temporal.py'])
        if from_stage in ('speaker_person', 'active_speaker', 'semantic', 'commercial', 'understanding', 'ranking'):
            understanding = ctx.step('16_understanding', understanding_replay_params(
                ctx.config['understanding'], metadata, transcript, diarization, vision, active, semantic, shots),
                lambda: run_understanding(ctx, metadata, transcript, diarization, vision, active, semantic, shots, ctx.config['understanding']),
                code_files=['understanding.py', 'story_recovery.py', 'editorial.py', 'editorial_intelligence.py', 'semantic.py'], required=True)
        else:
            understanding = {'main_moments':artifacts.read('main_moments.json') or [], 'participants':artifacts.read('participants.json') or [],
                             'story_arcs':artifacts.read('story_arcs.json') or [], 'entities':artifacts.read('entities.json') or [],
                             'editorial_shortlist':artifacts.summary.get('editorial_shortlist', []), 'video_understanding':{}}
        camera_timeline = artifacts.read('camera_timeline.json')
        if camera_timeline is None:
            camera_timeline = artifacts.projected('camera_timeline.compact.json', 'legacy_camera_projection')
        plan = run_planner_stage(ctx, metadata, vision, shots, camera_timeline or [], active.get('intervals', []), semantic, understanding)
        director = run_director_stage(ctx, metadata, vision, shots, active.get('intervals', []), [], semantic, understanding, plan)
        preview = run_preview_stage(ctx, metadata, director, cfg['preview'])
        analysis = {'schema_version':'2.0', 'metadata':metadata, 'analysis_status':'partial', 'execution_scope':'downstream_replay',
                    'audio_analysis':audio, 'video_analysis':{'metadata':metadata, 'frame_samples':frames, 'quality':{}},
                    'words':words, 'transcript_segments':segments, 'speakers':diarization['speakers'], 'speaker_turns':diarization['turns'],
                    'speech_overlaps':diarization['overlaps'], 'people':people, 'people_observations':observations,
                    'person_identities':people, 'scenes':scenes, 'shots':shots, 'topics':semantic['topics'],
                    'questions_answers':semantic['questions_answers'], 'question_candidates':semantic['question_candidates'],
                    'question_answer_pairs':semantic['question_answer_pairs'], 'qa_metrics':semantic['qa_metrics'],
                    'program_sections':semantic['program_sections'], 'primary_editorial_theme':semantic['primary_editorial_theme'],
                    'topic_quality':semantic['topic_quality'], 'semantic_metrics':semantic['semantic_metrics'],
                    'editorial_moments':semantic['moments'], 'candidate_hooks':semantic.get('candidate_hooks', []), 'candidate_endings':semantic.get('candidate_endings', []),
                    'speaker_person_mapping':active.get('mappings', []), 'speaker_person_summary':active.get('mapping_summary', []),
                    'speaker_person_diagnostics':active.get('speaker_person_diagnostics', []),
                    'speaker_person_affinity':active.get('affinity', []), 'active_speaker_evidence':active.get('active_speaker_evidence', []),
                    'active_speaker':active.get('intervals', []), 'camera_timeline':camera_timeline or [], 'camera_plan':plan,
                    'preview_validation':preview.get('validation', {}), 'preview_canaries':preview.get('canaries', []), 'preview_closed_loop':preview.get('closed_loop', {}),
                    'timeline':[], 'master_timeline':[], 'silences':audio.get('silences', []), 'audio_events':[], 'ocr_text':[],
                    'low_confidence_words':transcript['low_confidence_words'], 'transcription_alternatives':artifacts.read('transcription_alternatives.json') or [],
                    'unaligned_segments':[], 'issues':list(ctx.issues), 'stage_status':dict(ctx.states), 'stage_runtime':dict(ctx.stage_metrics),
                    **understanding, 'no_final_video_rendered':True,
                    'replay_provenance':{'from_stage':from_stage, 'upstream_source_hash':artifacts.source_hash,
                        'replay_plan':plan_scope,
                        'source_artifact_checksums':artifacts.verified, 'projection_limitations':artifacts.projections,
                        'asr_rerun':False, 'vision_rerun':False, 'llm_rerun':from_stage == 'semantic',
                        'legacy_snapshot_explicitly_allowed':allow_legacy_snapshot}}
        analysis['analysis_quality'] = build_analysis_quality(metadata, transcript, diarization, vision, active, shots, semantic, camera_timeline or [], ctx.issues)['data']
        analysis['analysis_quality'].update(understanding.get('candidate_metrics', {}))
        attach_director(analysis, director)
        analysis['replay_provenance']['downstream_elapsed_seconds'] = time.monotonic() - started
        from .timeline import captions
        ReportEngine().run(ctx, analysis, captions(words, cfg['captions']))
        return output, analysis
