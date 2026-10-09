"""Reproduce stage 01 from current sources and read-only evidence; stdlib only.

Run from the project root: python scripts/dev/baseline_etapa01.py
Only BASELINE.json and BASELINE_TECNICO.md are written. No ZIP extraction,
pipeline import, media processing, model access or approval changes occur.
"""
import ast
import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[2]
FEATURES = [
    ('S1', 'Understanding e contratos', ['understanding.py', 'editorial.py'], 'editorial/story_arcs.json', '16_understanding'),
    ('S2', 'Integridade e gates upstream', ['integrity_contracts.py', 'run_status.py', 'second_curation_export.py'], 'summary/upstream_contract_validation.json', '21_second_curation_handoff'),
    ('S3', 'Integridade narrativa e shortlist', ['editorial_intelligence.py', 'story_recovery.py', 'semantic.py'], 'editorial/selection_report_s3.json', '16_understanding'),
    ('S4', 'Tracking e recuperação facial', ['vision.py', 'person_reid.py', 'face_quality.py'], 'people/person_identities.json', '07_people_tracking'),
    ('S5', 'Speaker/person e falante ativo', ['active_speaker.py', 'speaker_roles.py', 'speaker_signals.py'], 'people/speaker_person_summary.json', '10_active_speaker'),
    ('S6', 'Camera Director e Smart Zoom', ['camera_director.py', 'camera_preflight.py', 'camera_motion.py'], 'camera/camera_summary.json', '19_camera_director'),
    ('S7', 'Revisão de transcrição e legendas', ['transcription.py', 'targeted_asr.py', 'subtitle_review.py'], 'subtitles/subtitle_review_s7.json', '17e_subtitle_review_s7'),
    ('S8', 'Comercial, GC e Stories', ['commercial_gate.py', 'broadcast_graphics.py', 'social_output.py'], 'editorial/commercial_review_s8.json', '17b_broadcast_graphics'),
    ('S9', 'Curator, canário e lote por hash', ['curator_delivery.py', 'curator_bridge.py'], None, None),
    ('S10', 'Aceitação A/B e recursos', ['performance_acceptance.py', 'performance.py'], None, None),
    ('S11', 'Homologação técnica e humana', ['homologation_s11.py'], None, None),
]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def inspect_zip(path, manifest_name, selected):
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read(manifest_name))
        checks = []
        for entry in manifest['files']:
            if entry.get('included', True) is False:
                continue
            name = entry['path']
            raw = archive.read(name) if name in archive.namelist() else None
            checks.append({'path': name, 'expected_sha256': entry.get('sha256'),
                           'actual_sha256': sha(raw) if raw is not None else None,
                           'matches': raw is not None and sha(raw) == entry.get('sha256')})
        records = {name: {'sha256': sha(archive.read(name)),
                          'data': json.loads(archive.read(name))} for name in selected}
        return {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path.read_bytes()),
                'member_count': len(archive.namelist()), 'manifest_sha256': sha(archive.read(manifest_name)),
                'manifest_member_checks': checks, 'records': records}, manifest


def build_baseline():
    manifest_path = ROOT / '.package/PROJECT_EXPORT_MANIFEST.json'
    manifest = read_json(manifest_path)
    files = []
    for entry in manifest['files']:
        path = ROOT / entry['path']
        # Never read credentials, repository internals, models or real media.
        relative = Path(entry['path'])
        if (relative.is_absolute() or '..' in relative.parts
                or any(part in {'.git', 'models', 'modelos', '.aws'} or part.startswith('.env') for part in relative.parts)
                or relative.suffix.lower() in {'.mp4', '.wav', '.mp3', '.pt', '.onnx'}):
            raise ValueError('Manifest path outside the allowed baseline scope: ' + entry['path'])
        actual = sha(path.read_bytes()) if path.is_file() else None
        files.append({'path': entry['path'], 'expected_sha256': entry['sha256'],
                      'actual_sha256': actual, 'matches': actual == entry['sha256']})
    declarations = {}
    for node in ast.parse((ROOT / 'src/ldporto/__init__.py').read_text(encoding='utf-8-sig')).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {'__version__', '__build__'}:
                    declarations[target.id] = ast.literal_eval(node.value)
    second, second_manifest = inspect_zip(ROOT / 'automacao/evidencias/SECOND_CURATION_READY.zip',
        'SECOND_CURATION_MANIFEST.json', ['SECOND_CURATION_MANIFEST.json', 'CURATION_INDEX.json',
        'summary/analysis_summary.json', 'summary/final_quality_gate.json'])
    prefix = 'analysis/video_869f6a2b1fdb/'
    review, review_manifest = inspect_zip(ROOT / 'automacao/evidencias/CHATGPT_REVIEW.zip',
        'ANALYSIS_EXPORT_MANIFEST.json', [prefix + 'analysis_summary.json', prefix + 'analysis_quality.json', prefix + 'run_manifest.json'])
    summary = review['records'][prefix + 'analysis_summary.json']['data']
    quality = review['records'][prefix + 'analysis_quality.json']['data']
    run = review['records'][prefix + 'run_manifest.json']['data']
    index = second['records']['CURATION_INDEX.json']['data']
    coverage = []
    for stage, feature, implementors, evidence, runtime_stage in FEATURES:
        paths = ['src/ldporto/' + name for name in implementors]
        coverage.append({'stage': stage, 'feature': feature, 'implementors': paths,
            'implementation_status': 'implementada' if all((ROOT / p).is_file() for p in paths) else 'inconclusiva',
            'export_evidence': 'SECOND_CURATION_READY.zip::' + evidence if evidence else None,
            'historical_stage_status': summary.get('stage_status', {}).get(runtime_stage, {}).get('status') if runtime_stage else None,
            'current_code_execution_in_export': None,
            'execution_status': 'inconclusiva' if evidence else 'não executada nesta etapa; sem prova no export',
            'reason': 'Artefato histórico não prova a execução dos hashes atuais.' if evidence else 'Documentação e testes sintéticos anteriores não provam homologação real S9–S11.'})
    metrics = {key: quality.get(key) for key in ('candidates_before_dedup', 'candidates_after_dedup',
        'final_shortlist_count', 'raw_track_count', 'valid_track_count', 'micro_track_count',
        'persistent_person_count', 'id_switch_count', 'active_speaker_confirmed_coverage',
        'resolved_focus_coverage', 'zoom_event_count', 'story_payoff_coverage', 'semantic_fallback_ratio')}
    identity = {'run_id_matches': run.get('run_id') == second_manifest.get('run_id'),
                'source_hash_matches': summary['metadata'].get('sha256') == second_manifest.get('source_hash')}
    return {'schema_version': '1.0', 'stage': '01', 'scope': 'reconciliation_offline_only',
        'codebase': {'authority': 'workspace atual; sem extração de ZIP', 'release': manifest['release'],
            'base': manifest['base'], 'declarations': declarations,
            'integrated_zip_available': (ROOT / 'LDPORTO_VIDEO_ANALYZER_R4_9_S9_S10_S11_INTEGRADO.zip').is_file(),
            'manifest_sha256': sha(manifest_path.read_bytes()), 'manifest_file_checks': files,
            'matching_files': sum(f['matches'] for f in files),
            'different_or_missing_files': [f for f in files if not f['matches']],
            'source_fingerprint_sha256': sha(json.dumps(files, sort_keys=True).encode()),
            'fingerprint_scope': '296 arquivos do manifesto; adições da automação não incluídas'},
        'execution': {'reported_build': second_manifest.get('analyzer_build'),
            'exact_executed_source_hashes': None, 'producer_version': summary.get('producer_version'),
            'run_id': run.get('run_id'), 'source_hash': second_manifest.get('source_hash'),
            'same_execution_checks': identity, 'source_media_hash_verified_locally': None,
            'analysis_status': summary.get('analysis_status'), 'quality_status': summary.get('quality_gate', {}).get('status'),
            'root_cause_stage': summary.get('root_cause_stage'), 'metrics': metrics,
            'stage_status': summary.get('stage_status'), 'stage_runtime': summary.get('stage_runtime'),
            'workflow': index.get('workflow'), 'analysis_export_state': review_manifest.get('export_state'),
            'analysis_export_created_at': review_manifest.get('created_at_local'),
            'second_curation_created_at': second_manifest.get('created_at')},
        'parameters': {'current_config_sha256': sha((ROOT / 'config/config.yaml').read_bytes()),
            'historical_full_config': None, 'historical_full_config_reason': 'Nenhum config/params no inventário dos dois ZIPs.',
            'source_metadata': summary['metadata'], 'selected_aspect_ratio': index.get('selected_aspect_ratio'),
            'semantic_available': {k: quality.get(k) for k in ('model_fingerprint', 'prompt_mode', 'semantic_call_budget', 'semantic_inference_call_count')}},
        'coverage': coverage, 'evidence': [second, review],
        'risks': ['Build declarado no código está desatualizado em relação ao manifesto; não alterado nesta etapa.',
            'Hashes do código executado não estão disponíveis; build exato só é conhecido como rótulo reportado.',
            'Um teste atual difere do manifesto original; o workspace é a autoridade e não foi sobrescrito.',
            'READY/READY_FOR_REVIEW coexistem com partial/P1_DEGRADED; não significam PREVIEW_APPROVED ou PUBLISH_READY.',
            'S9–S11 carecem de prova real Windows, Curator independente, revisão humana por hash e A/B medido.',
            'Identidades e falante ativo não são ground truth; null de id_switch_count preservado.',
            'Relatório histórico de 582 passed/2 skipped é evidência anterior, não resultado desta etapa.'],
        'cache_invalidated': False, 'publication_ready': index.get('workflow', {}).get('publication_ready')}


def markdown(data):
    code, run = data['codebase'], data['execution']
    lines = ['# Baseline técnico — etapa 01', '',
        'Base autorizada: workspace atual. Nenhum ZIP foi extraído ou criado; pipeline e identificadores permanecem intactos.', '',
        f"Manifesto: `{code['release']}`, base `{code['base']}`. Código declara `{code['declarations']}`.",
        f"Conferência: {code['matching_files']}/296 hashes coincidem; divergências: " + ', '.join(f['path'] for f in code['different_or_missing_files']) + '.',
        'O ZIP integrado original não está na raiz; o manifesto do export e os fontes atuais permitem a reconciliação disponível.', '',
        f"Execução João Gordo: build **reportado** `{run['reported_build']}`, run_id `{run['run_id']}`, source_hash `{run['source_hash']}`.",
        'Os dois pacotes têm o mesmo run_id e hash de fonte. Não existe prova dos hashes dos fontes executados: essa identificação permanece null.',
        f"Estado: `{run['analysis_status']}/{run['quality_status']}`; causa raiz `{run['root_cause_stage']}`. Métricas observadas: `{run['metrics']}`.",
        f"Workflow histórico: `{run['workflow']}`. Export de análise: `{run['analysis_export_state']}`.",
        '55 → 52 → 1 são observações históricas, sem metas de seleção. READY não autoriza publicação.', '',
        '## Cobertura funcional', '',
        '| Sessão / funcionalidade | Implementadores atuais | Evidência no export antigo | Estado |',
        '|---|---|---|---|']
    for row in data['coverage']:
        lines.append(f"| {row['stage']} — {row['feature']} | " + ', '.join(f'`{p}`' for p in row['implementors'])
            + f" | {row['export_evidence'] or 'null'}; runtime={row['historical_stage_status']} | {row['implementation_status']}; execução atual no export: {row['execution_status']} |")
    lines += ['', 'Implementada indica fonte presente e reconciliado, não homologação de todos os caminhos. Os estágios antigos contêm artefatos S5–S8 apesar do rótulo S4; não se infere uma versão executada exata desses nomes.', '',
        '## Evidências e parâmetros', '', 'BASELINE.json guarda hashes SHA-256 dos ZIPs, membros consultados, conferência de todos os membros declarados e todos os 296 arquivos do manifesto.',
        'Também preserva stage_status, stage_runtime, metadados da fonte, formato 9:16, fingerprint/modelo e parâmetros semânticos disponíveis. Configuração histórica completa: null; config atual é apenas referência com hash.', '']
    for evidence in data['evidence']:
        failures = [c['path'] for c in evidence['manifest_member_checks'] if not c['matches']]
        lines += [f"- `{evidence['path']}`: `{evidence['sha256']}`; {evidence['member_count']} membros; divergências no manifesto: {failures}."]
    lines += ['', '## Riscos e limites', ''] + ['- ' + risk for risk in data['risks']]
    lines += ['', '## Reprodução e validação', '',
        '`python scripts/dev/baseline_etapa01.py` regenera ambos os baselines de forma determinística com biblioteca padrão, sem importar o pipeline.',
        'Comandos, saídas e exit codes efetivamente executados: `automacao/execucao/checkpoints/CHECKPOINT_ETAPA_01.md`.',
        'Não executados: mídia real, ASR, visão, CUDA, Ollama, renderização, A/B e Curator independente. Homologar no Windows em etapa autorizada com mídia original e revisão humana por hash.',
        'Cache invalidado: nenhum. Próximo passo: revisar divergência do teste e rastreabilidade da build; não reanalisar para corrigir rótulo.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    baseline = build_baseline()
    (ROOT / 'automacao/baselines/BASELINE.json').write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'automacao/baselines/BASELINE_TECNICO.md').write_text(markdown(baseline), encoding='utf-8')
    print('BASELINE_OK: matching_files=' + str(baseline['codebase']['matching_files']))
    for evidence in baseline['evidence']:
        print(evidence['path'] + ': manifest_hash_mismatches=' + str(sum(not c['matches'] for c in evidence['manifest_member_checks'])))
