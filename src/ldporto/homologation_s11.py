"""S11 evidence-based release report: no silent human sign-off or synthetic benchmark claims."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import platform
import shutil
import subprocess
import zipfile
import xml.etree.ElementTree as ET

from .curator_bridge import audit_second_curation_package
from .curator_delivery import file_sha256, verify_mp4, probe, load_json, finalize_batch
from .performance_acceptance import resource_diagnostic

BENCHMARK_KEYS = ('micro_track_ratio', 'speaker_person_mapping_coverage', 'active_speaker_coverage',
                  'resolved_focus_coverage', 'zoom_event_count', 'zoom_delivered_event_count',
                  'commercial_block_count', 'excluded_commercial_count', 'targeted_asr_repaired_regions')
REVIEW_ITEMS = ('editorial', 'payoff', 'commercial', 'subtitles', 'face_tracking', 'audio_sync',
                'safe_area', 'broadcast_graphics', 'camera_motion')


def _analysis(source):
    if not source:
        return None
    path = Path(source)
    if path.is_dir():
        path = path/'analysis.json'
    if not path.is_file():
        return {'status': 'MISSING', 'metrics': {}}
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    quality = data.get('analysis_quality') or {}
    metrics = {k: quality[k] for k in BENCHMARK_KEYS if isinstance(quality.get(k), (int, float))}
    return {'status': 'AVAILABLE', 'analysis_status': data.get('analysis_status'), 'metrics': metrics,
            'stage_status': data.get('stage_status') or {}, 'path': str(path)}


def metric_delta(before, after):
    result = {}
    if not before or not after or before.get('status') != 'AVAILABLE' or after.get('status') != 'AVAILABLE':
        return result
    for key in sorted(set(before['metrics']) & set(after['metrics'])):
        a, b = before['metrics'][key], after['metrics'][key]
        result[key] = {'before': a, 'after': b, 'delta': b-a,
                       'interpretation': 'descriptive_only_not_quality_proof'}
    return result


def _runtime_checks():
    runtime = resource_diagnostic()
    try:
        from .ollama_local import service_info
        service = service_info('http://127.0.0.1:11434', timeout=1.5)
        runtime['ollama_local'] = {'reachable': service['reachable'], 'model_count': len(service.get('models') or [])}
    except Exception as exc:
        runtime['ollama_local'] = {'reachable': False, 'reason': type(exc).__name__}
    runtime['ffmpeg_encoder_libx264'] = False
    if runtime.get('ffmpeg'):
        try:
            p = subprocess.run([runtime['ffmpeg'], '-hide_banner', '-encoders'], capture_output=True,
                               text=True, encoding='utf-8', errors='replace', timeout=20)
            runtime['ffmpeg_encoder_libx264'] = p.returncode == 0 and 'libx264' in p.stdout
        except (OSError, subprocess.SubprocessError):
            pass
    return runtime


def _offline_runtime_checks():
    """Probe only installed CPU tools; never contact Ollama or inspect GPU."""
    runtime = {'python311_windows': platform.system() == 'Windows' and
               platform.python_version_tuple()[:2] == ('3', '11'),
               'gpu': {'available': None, 'reason': 'offline_not_measured'},
               'ollama_local': {'reachable': None, 'model_count': None,
                                'reason': 'offline_not_contacted'},
               'ffmpeg': shutil.which('ffmpeg'), 'ffprobe': shutil.which('ffprobe'),
               'ffmpeg_encoder_libx264': False, 'scope': 'offline_cpu_tools_only'}
    if runtime['ffmpeg']:
        try:
            proc = subprocess.run([runtime['ffmpeg'], '-hide_banner', '-encoders'],
                                  capture_output=True, text=True, encoding='utf-8',
                                  errors='replace', timeout=20)
            runtime['ffmpeg_encoder_libx264'] = proc.returncode == 0 and 'libx264' in proc.stdout
        except (OSError, subprocess.SubprocessError):
            pass
    return runtime


def homologate(*, package=None, source=None, preview=None, batch_manifest=None,
               analysis=None, baseline=None, human_reviews=None, junit=None, render_plan=None,
               offline=False):
    """Read-only real deployment report. Reports unknown as not evaluated."""
    r = {'schema_version': '11.1', 'created_at': datetime.now(timezone.utc).isoformat(),
         'verification_scope': 'local_evidence_read_only',
         'runtime': _offline_runtime_checks() if offline else _runtime_checks(),
         'automated_tests': 'NOT_RUN_IN_THIS_COMMAND', 'editorial_human_approval': False,
         'ready_to_publish': False, 'full_real_technical_flow': False, 'blockers': [], 'warnings': []}
    package_hash = file_sha256(package) if package and Path(package).is_file() else None
    source_hash = file_sha256(source) if source and Path(source).is_file() else None
    if package:
        r['package'] = audit_second_curation_package(package)
        if not r['package'].get('bridge_possible'):
            r['blockers'].append('SECOND_CURATION_READY_NOT_PROVEN')
    else:
        r['blockers'].append('PACKAGE_NOT_SUPPLIED')
    if source:
        path = Path(source)
        if path.is_file():
            r['source'] = {'sha256': source_hash, 'probe': probe(path)}
            if package and Path(package).is_file():
                with zipfile.ZipFile(package) as z:
                    source_expected = json.loads(z.read('source/metadata.json')).get('sha256')
                r['source']['matches_package_sha256'] = source_expected == source_hash
                if source_expected != source_hash:
                    r['blockers'].append('SOURCE_PACKAGE_SHA256_MISMATCH')
        else:
            r['blockers'].append('SOURCE_MEDIA_UNAVAILABLE')
    else:
        r['blockers'].append('SOURCE_MEDIA_NOT_SUPPLIED')
    if preview:
        duration = None
        if Path(preview).is_file():
            duration = probe(preview)['duration']
        r['preview'] = verify_mp4(preview, expected_duration=duration or 0)
        if r['preview']['status'] == 'BLOCKED':
            r['blockers'].append('PREVIEW_CRITICAL_ISSUE')
        receipt = Path(preview).with_suffix('.render.json')
        if receipt.is_file():
            record = json.loads(receipt.read_text(encoding='utf-8'))
            r['preview']['provenance_checked'] = bool(record.get('sha256') == r['preview'].get('sha256') and
                record.get('source_sha256') == source_hash and record.get('package_sha256') == package_hash)
        else:
            r['preview']['provenance_checked'] = False
        if not r['preview']['provenance_checked']:
            r['blockers'].append('PREVIEW_HASH_PROVENANCE_UNVERIFIED')
    else:
        r['blockers'].append('1080X1920_CANARY_NOT_SUPPLIED')
    if batch_manifest:
        batch = json.loads(Path(batch_manifest).read_text(encoding='utf-8'))
        r['batch'] = {'state': batch.get('state'), 'clip_count': len(batch.get('clips', [])),
                      'reports': [verify_mp4(c['file'], c.get('probe', {}).get('duration', 0)) for c in batch.get('clips', [])]}
        if not r['batch']['reports'] or any(x['status'] == 'BLOCKED' for x in r['batch']['reports']):
            r['blockers'].append('BATCH_MP4_TECHNICAL_FAILURE')
        r['batch']['independent_review_verified'] = False
        if render_plan and human_reviews:
            try:
                plan = load_json(render_plan)
                if plan.get('source_sha256') != source_hash or plan.get('package_sha256') != package_hash:
                    raise ValueError('HOMOLOGATION_PLAN_PROVENANCE_MISMATCH')
                if batch.get('canary_report', {}).get('sha256') != r.get('preview', {}).get('sha256'):
                    raise ValueError('HOMOLOGATION_CANARY_PREVIEW_MISMATCH')
                finalize_batch(plan, batch, load_json(human_reviews))
                r['batch']['independent_review_verified'] = True
            except (ValueError, KeyError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
                r['batch']['review_issue'] = str(exc)
        if not r['batch']['independent_review_verified']:
            r['blockers'].append('BATCH_HASH_BOUND_INDEPENDENT_REVIEW_PENDING')
    else:
        r['blockers'].append('INDEPENDENT_MP4_BATCH_NOT_SUPPLIED')
    current, previous = _analysis(analysis), _analysis(baseline)
    if current is not None:
        r['current_benchmark'] = current
    if previous is not None:
        r['baseline_benchmark'] = previous
    r['comparable_metric_deltas'] = metric_delta(previous, current)
    if not r['comparable_metric_deltas']:
        r['warnings'].append('BASELINE_AND_CURRENT_BENCHMARK_COMPARISON_NOT_AVAILABLE')
    if human_reviews:
        data = json.loads(Path(human_reviews).read_text(encoding='utf-8'))
        r['human_review'] = {'reviewer': data.get('reviewer'), 'checks': {k: data.get('checks', {}).get(k) for k in REVIEW_ITEMS}}
        hashes_bound = (bool(package_hash and source_hash and r.get('preview', {}).get('sha256')) and
                       data.get('package_sha256') == package_hash and
                       data.get('source_sha256') == source_hash and
                       data.get('preview_sha256') == r['preview']['sha256'])
        r['human_review']['hashes_bound_to_current_media'] = bool(hashes_bound)
        if (str(data.get('reviewer') or '').strip() and hashes_bound and
            r.get('batch', {}).get('independent_review_verified') is True and
            all(data.get('checks', {}).get(k) is True for k in REVIEW_ITEMS)):
            r['editorial_human_approval'] = True
    if junit:
        try:
            root = ET.parse(junit).getroot()
            suites = [root] if root.tag == 'testsuite' else list(root.findall('.//testsuite'))
            r['automated_tests'] = {'source': str(junit),
                'tests': sum(int(x.get('tests', 0)) for x in suites),
                'failures': sum(int(x.get('failures', 0)) for x in suites),
                'errors': sum(int(x.get('errors', 0)) for x in suites),
                'skipped': sum(int(x.get('skipped', 0)) for x in suites)}
            if r['automated_tests']['tests'] == 0 or r['automated_tests']['failures'] or r['automated_tests']['errors']:
                r['blockers'].append('AUTOMATED_TESTS_FAILED_OR_EMPTY')
        except (OSError, ValueError, ET.ParseError):
            r['automated_tests'] = 'UNREADABLE_JUNIT_REPORT'
            r['blockers'].append('AUTOMATED_TEST_RESULTS_UNAVAILABLE')
    else:
        r['warnings'].append('AUTOMATED_TEST_RESULTS_NOT_ATTACHED_TO_HOMOLOGATION')
    if not r['editorial_human_approval']:
        r['blockers'].append('HUMAN_EDITORIAL_REVIEW_PENDING')
    if not r['runtime']['python311_windows']:
        r['blockers'].append('WINDOWS_PYTHON311_NOT_CONFIRMED')
    if not r['runtime']['gpu'].get('available'):
        r['warnings'].append('NVIDIA_CUDA_NOT_MEASURED_ON_THIS_HOST')
    if not r['runtime']['ollama_local']['reachable']:
        r['warnings'].append('OLLAMA_LOCAL_NOT_VERIFIED')
    if not r['runtime']['ffmpeg_encoder_libx264']:
        r['blockers'].append('LIBX264_NOT_VERIFIED')
    r['full_real_technical_flow'] = bool(package and source and preview and batch_manifest and
                                          not any(x for x in r['blockers'] if x not in ('HUMAN_EDITORIAL_REVIEW_PENDING', 'WINDOWS_PYTHON311_NOT_CONFIRMED')))
    r['release_status'] = 'ACCEPTED_WITH_HUMAN_REVIEW' if not r['blockers'] else 'BLOCKED_OR_PENDING'
    # Never treat CLI-only checks as direct proof of platform publication readiness.
    r['ready_to_publish'] = False
    return r


def markdown_report(report):
    lines = ['# L.D.PORTO — Homologação S11', '',
             f"Estado: **{report['release_status']}** · {report['created_at']}", '',
             '## Escopo', 'Verificação técnica baseada em arquivos reais quando fornecidos; não equivale à aprovação humana.', '',
             '## Bloqueios']
    lines += [f'- {x}' for x in report['blockers']] or ['- Nenhum bloqueio técnico documentado neste relatório']
    lines += ['', '## Observações']
    lines += [f'- {x}' for x in report['warnings']] or ['- Nenhuma']
    lines += ['', '## Comparativo de benchmarks']
    for key, val in report.get('comparable_metric_deltas', {}).items():
        lines.append(f"- {key}: {val['before']} → {val['after']} (Δ {val['delta']:+.4f}) — descritivo, sem prova isolada de qualidade")
    if not report.get('comparable_metric_deltas'):
        lines.append('- Sem dois benchmarks comparáveis fornecidos')
    lines += ['', '## Verificações humanas indispensáveis']
    lines += [f'- [ ] {item}' for item in REVIEW_ITEMS]
    lines += ['', '## Resultado', 'Não publicar nem marcar como pronto até sanar bloqueios e revisar pessoalmente os MP4s.']
    return '\n'.join(lines)+'\n'
