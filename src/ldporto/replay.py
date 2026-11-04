"""Compatible downstream replay; imported snapshots are not fresh inference."""
from pathlib import Path, PureWindowsPath
import copy
import logging
import math
import time

from . import __version__
from .core import Context, digest, file_hash, ok, read_json, setup_logging, output_lock, logging_session, write_json
from .compact_artifacts import COLLECTION_FILES
from .editorial import topic_hierarchy, normalize_moment
from .semantic import questions_answers, qa_contract, SemanticEngine
from .understanding import run_understanding
from .analysis_quality import build_analysis_quality
from .director_integration import run_planner_stage, run_director_stage, attach_director
from .preview_integration import run_preview_stage
from .reports import ReportEngine


COMMERCIAL_STAGES = ('commercial', 'commercial_visual', '17c_commercial_visual')

REPLAY_STAGES = ('commercial_visual', '17c_commercial_visual', 'speaker_person', 'active_speaker', 'semantic', 'commercial', 'understanding', 'ranking', 'camera', 'camera_director', 'preview_verifier', 'second_curation', 'handoff')


def replay_plan(from_stage):
    """Describe this runner's scope, without claiming an inference/cache hit."""
    if from_stage not in REPLAY_STAGES:
        raise ValueError('Unsupported replay stage.')
    stages = []
    if from_stage == 'semantic':
        stages.append('15_semantic')
    elif from_stage in COMMERCIAL_STAGES:
        stages.extend(['17c_commercial_visual', '17e_subtitle_review_s7'])
    elif from_stage in ('speaker_person', 'active_speaker'):
        stages.append('10_active_speaker')
    if from_stage in ('speaker_person', 'active_speaker', 'semantic', 'understanding', 'ranking'):
        stages.append('16_understanding')
    stages.extend(['18b_global_camera_planner', '19_camera_director', '19b_preview_verifier'])
    return {'schema_version': '1.0', 'from_stage': from_stage,
            'stages_to_check': stages, 'exports_to_refresh': ['captions', 'reports', 'second_curation'],
            'snapshot_only': ['04_transcription', '07_people_tracking', '08_person_reid'],
            'semantic_snapshot_only': from_stage != 'semantic',
            'cache_hits': None, 'approval_inherited': False,
            'stage_dispositions': {name: 'reprocessado' for name in stages}}


def understanding_replay_params(config, metadata, transcript, diarization, vision, active, semantic, shots):
    """Hash actual arguments, not the unrelated set of files read for export.

    Includes computed semantic/active results; a snapshot checksum alone cannot
    identify those. The new contract conservatively misses old downstream caches.
    """
    return {'config': config, 'replay_input_contract': '1.0',
            'inputs': digest({'metadata': metadata, 'transcript': transcript,
                              'diarization': diarization, 'vision': vision,
                              'active': active, 'semantic': semantic, 'shots': shots})}


def safe_replay_path(value, root=None):
    """Reject lexical traversal and all symlink/reparse components before resolve."""
    raw = Path(value).expanduser()
    windows = PureWindowsPath(str(value))
    if '..' in raw.parts or '..' in windows.parts or (root is not None and
            (raw.is_absolute() or windows.is_absolute() or windows.drive)):
        raise ValueError('Unsafe replay path traversal.')
    path = Path(root) / raw if root is not None else raw.absolute()
    for part in [path, *path.parents]:
        if part.is_symlink() or (part.exists() and getattr(part.stat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Unsafe replay symlink/reparse path.')
    resolved = path.resolve()
    if root is not None and not resolved.is_relative_to(Path(root).resolve()):
        raise ValueError('Unsafe replay path outside snapshot.')
    return resolved


def checkpoint_hashes(folder):
    """Read checkpoints without copying or updating historical records."""
    return {str(p.relative_to(folder)).replace('\\', '/'): file_hash(safe_replay_path(p))
            for p in sorted(Path(folder).glob('cache/*/*.json'))}


def commercial_dry_run(folder, cfg, source=None, expected_source_hash=None,
                       allow_legacy_snapshot=False, from_stage='commercial'):
    """Read-only DAG inspection. No Context, decoder, inference or output directory."""
    if from_stage not in COMMERCIAL_STAGES:
        raise ValueError('OCR dry-run requires a commercial replay stage.')
    artifacts = ReplayArtifacts(folder, expected_source_hash, allow_legacy_snapshot)
    from .commercial_gate import ocr_runtime_fingerprint
    from .run_status import DEPENDENCIES
    plan = replay_plan(from_stage)
    unavailable = []
    source_valid = False
    try:
        source_valid = bool(source and safe_replay_path(source).is_file() and
                            file_hash(safe_replay_path(source)) == artifacts.source_hash)
    except (ValueError, OSError):
        pass
    if not source_valid:
        unavailable.append('source_media_required_with_matching_SHA256')
    runtime = ocr_runtime_fingerprint(cfg['ocr'])
    if not runtime['available']:
        unavailable.append(runtime['reason'])
    reused = {}
    for stage, names in {
            '04_transcription': ['words.json', 'transcript_segments.json'],
            '05_diarization': ['speaker_turns.json', 'speakers.json'],
            '07_people_tracking': ['people_observations.json'],
            '08_person_reid': ['people.json'], '15_semantic': ['topics.json', 'editorial_moments.json'],
            '16_understanding': ['main_moments.json']}.items():
        present = [artifacts.read(name) is not None for name in names]
        reused[stage] = 'snapshot' if all(present) else 'not_available'
        if not all(present):
            unavailable.append(stage + ': snapshot unavailable')
    candidates = artifacts.read('main_moments.json') or []
    limit = max(0, int(cfg['export']['second_curation_visual_candidate_limit']))
    plan.update(status='BLOCKED' if unavailable else 'READY_FOR_REVIEW', dry_run=True,
                source_sha256=artifacts.source_hash, source_validated=source_valid,
                reused_stages=reused, dependencies_unavailable=unavailable,
                dag={s: DEPENDENCIES.get(s, []) for s in plan['stages_to_check']},
                reasons={'17c_commercial_visual': 'OCR enabled after snapshot: inspect candidate windows',
                         '13_ocr': 'General vision-sample OCR is outside targeted commercial replay'},
                cost_estimate={'basis': 'bounded work estimate, not measured runtime',
                               'max_ocr_frames': 3 * min(len(candidates), limit),
                               'seconds': None, 'asr_calls': 0, 'diarization_calls': 0, 'ollama_calls': 0},
                ocr_runtime=runtime, verified_snapshot_hashes=dict(artifacts.verified),
                instruction='Use original local source with matching SHA-256 and configured local Tesseract; no frames opened.')
    return plan


def write_reprocess_manifest(output, artifacts, analysis, plan):
    states = analysis.get('stage_status', {})
    metrics = analysis.get('stage_runtime', {})
    stages = {}
    for stage, state in states.items():
        metric = metrics.get(stage, {})
        origin = ('snapshot' if state.get('artifact_snapshot_reused') else
                  'cache' if metric.get('cache_hit') else
                  'actually_executed' if metric.get('cache_misses') else 'not_executed')
        stages[stage] = {'stage_origin': origin, 'status': state.get('status'),
                         'cache_key': metric.get('cache_key'), 'invalidators': metric.get('invalidators', [])}
    visual = analysis.get('commercial_visual_s8') or {}
    manifest = {'schema_version': '56.1', 'status': analysis['analysis_status'],
                'source_sha256': artifacts.source_hash, 'stages': stages,
                'measurement_state': visual.get('measurement_state', 'not_measured'),
                'upstream_artifact_sha256': dict(artifacts.verified),
                'upstream_checkpoint_sha256': checkpoint_hashes(artifacts.folder),
                'upstream_checkpoint_before': plan.get('upstream_checkpoint_before', {}),
                'upstream_checkpoints_unchanged': plan.get('upstream_checkpoint_before', {}) == checkpoint_hashes(artifacts.folder),
                'replay_checkpoint_before': plan.get('checkpoint_before', {}),
                'replay_checkpoint_after': checkpoint_hashes(output),
                'ocr_evidence_sha256': digest({k: visual.get(k) for k in
                    ('texts', 'frame_resources', 'candidate_coverage', 'source_sha256')})
                    if visual.get('measurement_state') == 'measured' else None,
                'historical_build_modified': False, 'publication_ready': False}
    analysis['reprocess_manifest'] = manifest
    write_json(safe_replay_path(output / 'reprocess_manifest.json'), manifest)


def blocked_commercial_replay(output, artifacts, plan, reason, runtime=None, ctx=None):
    states = {'17c_commercial_visual': {'status': 'blocked', 'reason': reason}}
    plan['stage_dispositions'].update({stage: 'not_available' for stage in plan['stages_to_check']})
    analysis = {'analysis_status': 'blocked', 'metadata': artifacts.metadata,
                'stage_status': states, 'stage_runtime': {}, 'commercial_present': None,
                'commercial_visual_s8': {'status': 'blocked', 'measurement_state': 'not_measured',
                    'commercial_present': None, 'texts': [], 'reason': reason, 'ocr_runtime': runtime},
                'replay_provenance': {'replay_plan': plan, 'asr_rerun': False, 'vision_rerun': False,
                    'llm_rerun': False, 'upstream_source_hash': artifacts.source_hash},
                'instruction': 'Forneca a midia local original (argumento source) com SHA-256 igual ao metadata; '
                    'habilite ocr.enabled e configure Tesseract/idiomas no JSON --config. '
                    'Contact sheets e thumbnails historicos nao comprovam OCR executado.'}
    if ctx is not None:
        analysis['stage_status'].update(copy.deepcopy(ctx.states))
        analysis['stage_runtime'] = copy.deepcopy(ctx.stage_metrics)
    write_reprocess_manifest(output, artifacts, analysis, plan)
    write_json(output / 'replay_blocked.json', analysis)
    return output, analysis


def resolve_replay_folder(value):
    folder = safe_replay_path(value)
    if not folder.is_dir():
        raise ValueError('Replay requires an extracted analysis directory.')
    if (folder / 'analysis_summary.json').is_file() or (folder / 'analysis.json').is_file():
        return folder
    candidates = sorted({path.parent for path in folder.glob('analysis/*/analysis_summary.json')})
    if len(candidates) != 1:
        raise ValueError('Replay source is ambiguous; specify one analysis directory.')
    return safe_replay_path(candidates[0])


class ReplayArtifacts:
    def __init__(self, folder, expected_source_hash=None, allow_legacy_snapshot=False):
        self.folder = resolve_replay_folder(folder)
        self.document = read_json(safe_replay_path('analysis.json', self.folder)) if (safe_replay_path('analysis.json', self.folder)).is_file() else {}
        self.summary = read_json(safe_replay_path('analysis_summary.json', self.folder)) if (safe_replay_path('analysis_summary.json', self.folder)).is_file() else self.document
        self.metadata = self.summary.get('metadata') or self.document.get('metadata') or {}
        version = str(self.metadata.get('analyzer_version') or self.summary.get('producer_version') or '')
        if not version.startswith(('4.3', '4.4')) and not allow_legacy_snapshot:
            raise ValueError('Legacy replay requires --allow-legacy-snapshot; not a current prompt/model cache.')
        if self.metadata.get('schema_version') not in ('2.0', '4.2', '4.3'):
            raise ValueError('Unsupported replay artifact schema.')
        source_hash = self.metadata.get('sha256')
        if (not isinstance(source_hash, str) or len(source_hash) != 64 or
                any(char not in '0123456789abcdef' for char in source_hash) or
                expected_source_hash and source_hash != expected_source_hash):
            raise ValueError('Replay source hash mismatch or missing.')
        if not isinstance(self.metadata.get('duration'), (int, float)) or not math.isfinite(self.metadata['duration']) or self.metadata['duration'] <= 0:
            raise ValueError('Replay source duration invalid.')
        self.source_hash = source_hash
        self.checksums = {}
        self.verified = {}
        self.projections = []
        local_manifest = safe_replay_path('manifest.json', self.folder)
        if local_manifest.is_file():
            local = read_json(local_manifest)
            for name, checksum in local.get('artifact_checksums', {}).items():
                path = safe_replay_path(name, self.folder)
                if not path.is_relative_to(self.folder):
                    raise ValueError('Unsafe local replay checksum reference.')
                self.register_checksum(path, checksum)
        export_path = safe_replay_path(self.folder.parent.parent / 'ANALYSIS_EXPORT_MANIFEST.json')
        if export_path.is_file():
            export = read_json(export_path)
            for row in export.get('files', []):
                path = safe_replay_path(row['path'], export_path.parent)
                if path.resolve().is_relative_to(self.folder) and row.get('sha256'):
                    self.register_checksum(path.resolve(), row['sha256'])
        for key, reference in self.document.get('collection_refs', {}).items():
            if key not in COLLECTION_FILES or reference.get('path') != COLLECTION_FILES[key]:
                raise ValueError('Unsafe replay collection reference.')
            self.register_checksum(safe_replay_path(reference['path'], self.folder), reference.get('sha256'))

        for name in ('analysis.json', 'analysis_summary.json'):
            path = safe_replay_path(name, self.folder)
            if path in self.checksums:
                self.read(name, required=True)

    def register_checksum(self, path, checksum):
        if path in self.checksums and self.checksums[path] != checksum:
            raise ValueError('Conflicting replay artifact checksums.')
        self.checksums[path] = checksum

    def read(self, name, required=False):
        path = safe_replay_path(name, self.folder)
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
            path = safe_replay_path(name, self.folder)
            if not path.is_relative_to(self.folder) or path.is_symlink():
                raise ValueError('Unsafe replay projection chunk.')
            self.register_checksum(path, reference.get('sha256'))
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
    commercial_replay = from_stage in COMMERCIAL_STAGES
    output = safe_replay_path(output or ANALYSIS_DIR / ('replay_v43_' + artifacts.source_hash[:12] + '_' + from_stage))
    if output == artifacts.folder or output.is_relative_to(artifacts.folder) or artifacts.folder.is_relative_to(output):
        raise ValueError('Replay output must be separate from immutable inputs.')
    output.mkdir(parents=True, exist_ok=True)
    plan_scope['checkpoint_before'] = checkpoint_hashes(output)
    plan_scope['upstream_checkpoint_before'] = checkpoint_hashes(artifacts.folder)
    safe_replay_path(output / 'cache' / artifacts.source_hash[:16])
    runtime = None
    if commercial_replay:
        try:
            if not source:
                return blocked_commercial_replay(output, artifacts, plan_scope, 'source_media_required')
            source = safe_replay_path(source)
            if source.is_relative_to(output):
                return blocked_commercial_replay(output, artifacts, plan_scope, 'output_must_be_separate_from_source_media')
            if not source.is_file() or file_hash(source) != artifacts.source_hash:
                return blocked_commercial_replay(output, artifacts, plan_scope, 'source_media_hash_mismatch_or_missing')
        except (ValueError, OSError) as exc:
            return blocked_commercial_replay(output, artifacts, plan_scope, str(exc))
        from .commercial_gate import ocr_runtime_fingerprint
        runtime = ocr_runtime_fingerprint(cfg['ocr'])
        if not runtime['available']:
            return blocked_commercial_replay(output, artifacts, plan_scope, runtime['reason'], runtime)
    elif source and file_hash(safe_replay_path(source)) != artifacts.source_hash:
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
    snapshot_candidates = artifacts.read('main_moments.json') if commercial_replay else None
    if commercial_replay and snapshot_candidates is None:
        return blocked_commercial_replay(output, artifacts, plan_scope, 'verified_main_moments_snapshot_required', runtime)
    all_segment_ids = {segment['segment_id'] for segment in segments}
    for row in topics + moments + (snapshot_candidates or []):
        if not set(row.get('evidence_segment_ids', [])) <= all_segment_ids:
            raise ValueError('Replay semantic refs do not resolve to transcript.')
    topics, sections, primary, secondary, topic_quality = topic_hierarchy(topics, segments)
    qas = questions_answers(segments)
    semantic = {'topics':topics, 'moments':[normalize_moment(row) for row in moments], 'program_sections':sections,
                'primary_editorial_theme':primary, 'secondary_editorial_themes':secondary, 'topic_quality':topic_quality,
                'questions_answers':qas, **qa_contract(qas),
                'semantic_metrics':{'semantic_inference_call_count':0, 'semantic_seconds':None,
                                   'semantic_cache_hit_ratio':None, 'execution_basis':'legacy_grounded_snapshot_not_fresh_inference'}}
    commercial_visual = {}
    subtitle_review = {}
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
        if from_stage in ('speaker_person', 'active_speaker', 'semantic', 'understanding', 'ranking'):
            understanding = ctx.step('16_understanding', understanding_replay_params(
                ctx.config['understanding'], metadata, transcript, diarization, vision, active, semantic, shots),
                lambda: run_understanding(ctx, metadata, transcript, diarization, vision, active, semantic, shots, ctx.config['understanding']),
                code_files=['understanding.py', 'story_recovery.py', 'editorial.py', 'editorial_intelligence.py', 'semantic.py'], required=True)
        else:
            understanding = {'main_moments':snapshot_candidates if commercial_replay else artifacts.read('main_moments.json') or [], 'participants':artifacts.read('participants.json') or [],
                             'story_arcs':artifacts.read('story_arcs.json') or [], 'entities':artifacts.read('entities.json') or [],
                             'editorial_shortlist':artifacts.summary.get('editorial_shortlist', []), 'video_understanding':{}}
        if commercial_replay:
            from .commercial_gate import targeted_ocr, apply_commercial_refinement, commercial_visual_params
            limit = cfg['export']['second_curation_visual_candidate_limit']
            params = commercial_visual_params(artifacts.source_hash, snapshot_candidates,
                cfg['ocr'], limit, runtime, dict(artifacts.verified))
            def measure():
                # Verify again at the producer boundary, including runtime changes.
                if file_hash(source) != artifacts.source_hash or ocr_runtime_fingerprint(cfg['ocr']) != runtime:
                    return ok({'reason': 'ocr_inputs_changed', 'texts': [], 'commercial_present': None}, 'blocked')
                payload = targeted_ocr(source, snapshot_candidates, cfg['ocr'], limit)
                if file_hash(source) != artifacts.source_hash:
                    return ok({'reason': 'ocr_source_hash_mismatch', 'texts': [], 'commercial_present': None}, 'blocked')
                if payload.get('measurement_state') != 'measured':
                    payload['ocr_runtime'] = runtime
                    return ok(payload, 'blocked', [payload.get('reason') or 'No OCR frames measured'])
                if payload.get('source_sha256') != artifacts.source_hash or any(
                        row.get('source_sha256') != artifacts.source_hash for row in payload.get('texts', [])):
                    return ok({'reason': 'ocr_source_hash_mismatch', 'texts': [], 'commercial_present': None}, 'blocked')
                payload['ocr_runtime'] = runtime
                status = 'ok' if payload.get('status') == 'measured' else 'partial' if payload.get('measurement_state') == 'measured' else 'blocked'
                return ok(payload, status, [] if status == 'ok' else [payload.get('reason') or 'OCR incomplete'])
            safe_replay_path(ctx.cache / '17c_commercial_visual.json')
            commercial_visual = ctx.step('17c_commercial_visual', params, measure,
                code_files=['commercial_gate.py', 'ocr.py', 'ocr_execution.py', 'ocr_runtime.py', 'ocr_diagnostics.py', 'editorial.py', 'replay.py'])
            if file_hash(safe_replay_path(source)) != artifacts.source_hash:
                return blocked_commercial_replay(output, artifacts, plan_scope, 'source_media_changed', runtime, ctx)
            if ctx.states['17c_commercial_visual']['status'] in ('blocked', 'failed', 'unavailable'):
                return blocked_commercial_replay(output, artifacts, plan_scope,
                    commercial_visual.get('reason', 'targeted_ocr_failed'), runtime, ctx)
            if commercial_visual.get('source_sha256') != artifacts.source_hash or any(
                    row.get('source_sha256') != artifacts.source_hash for row in commercial_visual.get('texts', [])):
                return blocked_commercial_replay(output, artifacts, plan_scope, 'cached_ocr_source_hash_mismatch', runtime, ctx)
            if commercial_visual.get('measurement_state') != 'measured':
                return blocked_commercial_replay(output, artifacts, plan_scope, 'cached_ocr_not_measured', runtime, ctx)
            understanding = apply_commercial_refinement(understanding, segments,
                commercial_visual.get('texts', []), cfg['understanding'],
                commercial_visual=commercial_visual, graphics=vision['broadcast_graphics'])
            # Audio repair is selection-dependent and must not run in visual replay.
            ctx.states['17d_targeted_asr'] = {'status': 'skipped', 'reason': 'selection_changed_audio_repair_requires_review'}
            ctx.stage_metrics['17d_targeted_asr'] = {'executed_in_replay': False, 'elapsed_seconds': None}
            from .subtitle_review import review_selected_clips
            subtitle_review = ctx.step('17e_subtitle_review_s7',
                {'selection': digest(understanding), 'words': digest(words), 'captions': cfg['captions']},
                lambda: ok(review_selected_clips(words, understanding['main_moments'],
                    selected_ids=understanding.get('editorial_shortlist', []), alternatives=[], targeted_report={},
                    events=[], caption_config=cfg['captions'], threshold=cfg['transcription']['low_confidence'])),
                code_files=['subtitle_review.py', 'timeline.py'], requires=['17c_commercial_visual'])
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
                    'timeline':[], 'master_timeline':[], 'silences':audio.get('silences', []), 'audio_events':[], 'ocr_text':commercial_visual.get('texts', []),
                    'commercial_visual_s8':commercial_visual, 'subtitle_review_s7':subtitle_review,
                    'low_confidence_words':transcript['low_confidence_words'], 'transcription_alternatives':artifacts.read('transcription_alternatives.json') or [],
                    'unaligned_segments':[], 'issues':list(ctx.issues), 'stage_status':dict(ctx.states), 'stage_runtime':dict(ctx.stage_metrics),
                    **understanding, 'no_final_video_rendered':True,
                    'replay_provenance':{'upstream_run_manifest': copy.deepcopy(upstream_manifest),
                        'from_stage':from_stage, 'upstream_source_hash':artifacts.source_hash,
                        'replay_plan':plan_scope,
                        'source_artifact_checksums':artifacts.verified, 'projection_limitations':artifacts.projections,
                        'asr_rerun':False, 'vision_rerun':False, 'llm_rerun':from_stage == 'semantic',
                        'legacy_snapshot_explicitly_allowed':allow_legacy_snapshot}}
        analysis['analysis_quality'] = build_analysis_quality(metadata, transcript, diarization, vision, active, shots, semantic, camera_timeline or [], ctx.issues)['data']
        analysis['analysis_quality'].update(understanding.get('candidate_metrics', {}))
        attach_director(analysis, director)
        snapshot_files = {
            '04_transcription': ['words.json', 'transcript_segments.json'],
            '05_diarization': ['speaker_turns.json', 'speakers.json'],
            '07_people_tracking': ['people_observations.json'], '08_person_reid': ['people.json'],
            '10_active_speaker': ['active_speaker.json'], '11_shots': ['shots.json'],
            '12_camera_timeline': ['camera_timeline.json'],
            '15_semantic': ['topics.json', 'editorial_moments.json'],
            '16_understanding': ['main_moments.json'], '17b_broadcast_graphics': ['broadcast_graphics.json']}
        dispositions = plan_scope['stage_dispositions']
        for stage, names in snapshot_files.items():
            if stage not in plan_scope['stages_to_check']:
                dispositions[stage] = 'snapshot_reused' if all(name in artifacts.verified for name in names) else 'not_available'
                ctx.states.setdefault(stage, {'status': 'partial'})
                if dispositions[stage] == 'not_available':
                    ctx.states[stage]['status'] = 'partial'
                    ctx.states[stage]['reason'] = 'snapshot_evidence_not_available'
                ctx.states[stage]['artifact_snapshot_reused'] = dispositions[stage] == 'snapshot_reused'
                ctx.states[stage]['replay_disposition'] = dispositions[stage]
                ctx.stage_metrics.setdefault(stage, {'executed_in_replay': False, 'elapsed_seconds': None})
        if commercial_replay:
            dispositions['17d_targeted_asr'] = 'not_available'
        for stage in plan_scope['stages_to_check']:
            state = ctx.states.get(stage, {})
            dispositions[stage] = 'not_available' if state.get('status') in ('blocked', 'failed', 'unavailable') else 'reprocessado'
            state['replay_disposition'] = dispositions[stage]
            state['cache_hit'] = bool(ctx.stage_metrics.get(stage, {}).get('cache_hit'))
        if commercial_replay:
            for stage, state in ctx.states.items():
                if stage not in dispositions:
                    dispositions[stage] = 'not_available'
                    state.update(status='partial', artifact_snapshot_reused=False,
                                 reason='snapshot_evidence_not_available')
                state['replay_disposition'] = dispositions[stage]
        plan_scope['cache_hits'] = [stage for stage, metric in ctx.stage_metrics.items() if metric.get('cache_hit')]
        analysis['stage_status'] = copy.deepcopy(ctx.states)
        analysis['stage_runtime'] = copy.deepcopy(ctx.stage_metrics)
        analysis['replay_provenance']['downstream_elapsed_seconds'] = time.monotonic() - started
        write_reprocess_manifest(output, artifacts, analysis, plan_scope)
        from .timeline import captions
        ReportEngine().run(ctx, analysis, captions(words, cfg['captions']))
        return output, analysis
