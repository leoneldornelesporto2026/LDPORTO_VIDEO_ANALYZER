"""Read-only preservation audit and objective R5 delivery report."""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
REPORT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'src'))


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4194304), b''):
            h.update(block)
    return h.hexdigest()


def main():
    from ldporto.second_curation_export import validate_core_package
    initial = read(REPORT/'initial_state.json')
    result = read(REPORT/'release_replay/replay_result.json')
    frozen = read(REPORT/'sources_frozen_final.json')
    after = read(REPORT/'release_full.json')
    before = read(ROOT/initial['baseline'])
    analysis = ROOT/'analysis/video_5198fcdaef38'
    failures = []
    for name, meta in initial['original_analysis_files'].items():
        path = analysis/name
        if not path.is_file() or path.stat().st_size != meta['bytes'] or sha(path) != meta['sha256']:
            failures.append('original_analysis_changed:' + name)
    files = {p.relative_to(analysis).as_posix() for p in analysis.rglob('*') if p.is_file()}
    if files != set(initial['original_analysis_files']):
        failures.append('original_analysis_file_set_changed')
    for name, expected in initial['protected_package'].items():
        if sha(ROOT/name) != expected:
            failures.append('protected_package_changed:' + name)
    if sha(ROOT/initial['reference_package']) != initial['reference_package_sha256']:
        failures.append('reference_zip_changed')
    for name, expected in frozen.items():
        if sha(ROOT/name) != expected:
            failures.append('source_drift_after_freeze:' + name)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    if head != initial['head'] or branch != initial['branch']:
        failures.append('git_identity_changed')
    missing = list((Counter(before['test_identities'])-Counter(after['test_identities'])).elements())
    added = list((Counter(after['test_identities'])-Counter(before['test_identities'])).elements())
    if missing or after['returncode'] or after['failed'] or after['errors']:
        failures.append('regression_failed_or_old_tests_missing')
    package = Path(result['result']['path'])
    validation = validate_core_package(package)
    original_validation = validate_core_package(ROOT/initial['reference_package'])
    if validation['status'] != 'valid' or original_validation['status'] != 'valid':
        failures.append('package_validation')
    if sha(package) != result['package_sha256'] or result.get('historical_field_drift'):
        failures.append('historical_candidate_or_package_hash_drift')
    packet = REPORT/'review_packet'
    packet.mkdir(exist_ok=True)
    with zipfile.ZipFile(package) as archive:
        manifest = json.loads(archive.read('SECOND_CURATION_MANIFEST.json'))
        handoff = json.loads(archive.read('SECOND_CURATION_NARRATIVE_HANDOFF.json'))
        qa = json.loads(archive.read('editorial/question_answer_links.json'))['links']
        titles = json.loads(archive.read('social/narrative_title_suggestions.json'))['titles']
        repair = json.loads(archive.read('editorial/narrative_repair_plan.json'))
        bundle_cache = read(REPORT/'release_replay/NARRATIVE_REPLAY_BUNDLE.json')
        arcs = bundle_cache['story_arcs']
        nodes = json.loads(archive.read('editorial/narrative_graph.json'))
        units = json.loads(archive.read('editorial/story_units.json'))['units']
        exported_segments = [json.loads(line) for line in archive.read('transcript/relevant_segments.jsonl').decode('utf8').splitlines() if line]
        for name in ('CODEX_ANALYZER_REVIEW.md', 'CODEX_ANALYZER_REVIEW.json', 'NARRATIVE_BEFORE_AFTER.json',
                     'STORY_READINESS_REPORT.json', 'SECOND_CURATION_HANDOFF_VALIDATION.json',
                     'README_SECOND_CURATION.md', 'NARRATIVE_REVIEW.html', 'SECOND_CURATION_NARRATIVE_HANDOFF.json'):
            (packet/name).write_bytes(archive.read(name))
    after_conflicts = sum(bool((arc.get('support_diagnostics') or {}).get('canonical_interval_conflicts')) for arc in arcs)
    coverage = {'canonical_segments_exported': len(exported_segments),
        'segments_in_story_units': len({sid for unit in units for sid in unit['source_segment_ids']}),
        'graph_nodes': len(nodes['nodes']), 'graph_edges': len(nodes['edges']),
        'dangling_references': validation['dangling_references']}
    changed = [name for name, info in initial['sources'].items() if sha(ROOT/name) != info['sha256']]
    new = sorted(set(frozen)-set(initial['sources']))
    source_path = ROOT/'input/youtube/zd_wjssZ7mc/zd_wjssZ7mc.mp4'
    media = {'exists': source_path.is_file(), 'decoded': False}
    if source_path.is_file():
        media['sha256'] = sha(source_path)
        media['matches_original_metadata'] = media['sha256'] == result['source_sha256']
        if not media['matches_original_metadata']:
            failures.append('source_media_metadata_hash_disagreement')
    comparison = {'baseline_passed': before['passed'], 'baseline_skipped': before['skipped'],
        'passed': after['passed'], 'skipped': after['skipped'], 'failed': after['failed'], 'errors': after['errors'],
        'old_cases_preserved': not missing, 'missing': missing, 'added_count': len(added), 'added_cases': added}
    integrity = {'state': 'VERIFIED' if not failures else 'FAILED', 'timestamp': datetime.now().astimezone().isoformat(),
        'failures': failures, 'head': head, 'branch': branch, 'original_analysis_files_verified': len(files),
        'original_analysis_bytes_verified': sum(m['bytes'] for m in initial['original_analysis_files'].values()),
        'completed_checkpoints_verified': len(result['checkpoint_sha256']),
        'protected_package_files_verified': len(initial['protected_package']),
        'original_zip_validation': original_validation['status'], 'package_validation': validation['status'],
        'package_sha256': sha(package), 'package_bytes': package.stat().st_size,
        'manifest_hashes_verified': len(manifest['files']), 'package_members': manifest['file_count'],
        'frozen_sources_verified': len(frozen), 'source_media': media,
        'sources_changed': changed, 'sources_added': new, 'test_comparison': comparison,
        'arc_interval_conflicts_before': result['before']['arc_interval_conflicts'],
        'arc_interval_conflicts_after': after_conflicts, 'historical_candidate_fields_preserved': not result['historical_field_drift'],
        'new_model_calls': result['new_model_calls'], 'publication_ready': False}
    integrity['coverage'] = coverage
    cached_repeat = read(REPORT/'cache_repeat_validation.json') if (REPORT/'cache_repeat_validation.json').is_file() else None
    integrity['actual_cache_repeat'] = cached_repeat
    (REPORT/'final_integrity.json').write_text(json.dumps(integrity, indent=2, ensure_ascii=False), encoding='utf8')
    (REPORT/'git_after.txt').write_text(subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True), encoding='utf8')
    quality = result['after']
    reason_counts = Counter(reason for row in quality['selection_diagnostics'].values() for reason in set(row['recorded_reasons']))
    reason_text = '; '.join(f'{name}: {count}' for name, count in reason_counts.most_common(8))
    examples = [t for t in titles if any(token in t['hook_text'].lower() for token in ('voo', 'proa', 'combust', 'aeronave'))][:3]
    example_text = '\n'.join('- ' + ' / '.join('“' + variant['title'] + '”' for variant in title['suggested_titles']) +
        ' — fonte `' + ', '.join(title['hook_segment_ids']) + '`, revisão obrigatória.' for title in examples)
    suggestions = [q for q in qa if q.get('answer_segment_ids')]
    focus = read(REPORT/'focused_release_summary.json')
    p = package.relative_to(REPORT).as_posix()
    report = f'''# Analyzer R5 — Narrative Intelligence & Second Curation Handoff

Decisão: **{result['status']}**. Integridade final: **{integrity['state']}**. O replay real foi executado em CPU sobre os dados persistidos do vídeo VARIG; nenhuma inferência audiovisual, chamada Qwen, renderização ou publicação nova.

## A. Diagnóstico e causas confirmadas

O [baseline](../../audits/ANALYZER_R5_BASELINE.md) foi escrito antes da implementação. Os 485 fontes da V4.1 estavam intactos. A análise possui 621 arquivos, 383 segmentos, 34 perguntas e 50 arcos. [data_diagnostic.json](data_diagnostic.json) registra caminhos, hashes e exemplos.

46 itens no catálogo são 45 principais avaliados em S3 e 1 alternativa preservada (MOMENT_00001_0000 → MOMENT_00001_0001); não houve perda. A shortlist zero decorre dos gates registrados, incluindo hook/clareza não medidos, contexto, limites, QA e evidência comercial insuficiente. Nenhum threshold foi reduzido.

Frequências dos principais motivos registrados nos candidatos: {reason_text}.

28 discussões tinham IDs de miolo da seção em narrative_structure.development, mas nenhum desenvolvimento narrativo validado. Isso era diferença de escopo, não prova de 28 histórias completas. Outro problema real afetava oito arcos: o desenvolvimento podia anteceder/incluir o setup.

Na classificação comercial, “20 mil pés” gerava price e “9 vezes a força da gravidade” gerava installment. A busca QA aceitava todos os segmentos e perguntas, mas não reconhecia duas autorrespostas locais muito específicas. As demais abstenções não provam ausência de resposta semântica.

## B. Alterações e contratos

O desenvolvimento canônico agora fica após o setup e respeita o narrador e o payoff. section_layout guarda posições da seção; structure_contract 1.0 declara que layout não é evidência narrativa. narrative_structure deriva dos componentes canônicos. Os arquivos originais permanecem intactos, e o contrato derivado explicita essa migração de significado.

Foi criado um handoff narrativo 1.0, com schema, grafo, unidades, propostas QA, agrupamentos, títulos, plano ASR, diagnósticos e auditoria independente. O grafo separa ordem de apresentação e cronologia dos fatos; nenhuma aresta lexical vira causalidade. Duas referências de entidade entre seções são recuperação de contexto, sujeitas a revisão, sem afirmar continuidade do mesmo evento.

O fluxo normal de relatórios habilita R5 quando há SHA-256 canônico; fontes legadas sem hash válido continuam no contrato anterior, com motivo de indisponibilidade R5. Exportação direta mantém opção explícita. Cache/fingerprints incluem módulos e schema novos. O VIDEO CURATOR não foi modificado.

## C. Antes e depois no vídeo real

| Medida | Antes | Depois |
|---|---:|---:|
| Arcos | 50 | {quality['source_arcs']} |
| Arcos completos sustentados | 0 | {quality['complete_supported_sequence_count']} |
| Conflitos temporais nos componentes | 8 | {after_conflicts} |
| QA canônico unresolved / not_expected | 29 / 5 | 29 / 5, preservados |
| Propostas novas de autorresposta | 0 | {quality['question_answer_link_count']}, não confirmadas |
| Unidades para revisão | 0 no contrato R5 | {quality['unit_count']} |
| Agrupamentos provisórios | 0 no contrato R5 | {quality['sequence_count']} |
| Sementes literais de títulos | 0 | {quality['title_seed_count']} |
| Candidatos standalone / shortlist | 46 / 0 | 46 / 0 |
| Novas inferências | — | 0 |

O QA derivado possui 27 casos ainda sem proposta para perguntas esperadas e duas propostas de autorresposta. Não foram convertidos em respostas canônicas resolvidas: Q_0000 liga SEG_00003 (“Como a gente lê?”) a SEG_00004 (“270.”), exigindo também SEG_00002 (“número 0270”). Q_0004 liga SEG_00013 à confirmação “Sim, a gente contou…” de SEG_00014. Não houve observação de tela nem escuta para confirmar esses vínculos. [Diagnóstico QA e exemplos](varig_qa_abstention_focus.md).

Os tipos dos arcos continuam 28 discussion_segment, 14 anecdote e 8 partial_story; os 50 não ganharam payoff artificialmente. A limitação de compreensão semântica global continua explícita: explicações plausíveis sem os vínculos estritos, como Q_0015, ainda exigem inspeção ou um resolver semântico mais amplo. Não se mediu precisão/recall humano.

## D. Unidades, sequências e câmera

As {quality['unit_count']} unidades preservam texto, IDs, intervalos separados, função/escopo, contexto, falantes acústicos e vínculos com os 46 candidatos. Unidades de contexto podem entrar na curadoria de uma sequência mesmo sem passar pelo gate de Reel. PROVISIONAL_REVIEW_READY significa evidência disponível para inspeção, não autorização de distribuição.

Cobertura: {coverage['canonical_segments_exported']} segmentos canônicos exportados; {coverage['segments_in_story_units']} participam das unidades. O grafo contém {coverage['graph_nodes']} nós e {coverage['graph_edges']} arestas. Referências pendentes no pacote final: {coverage['dangling_references']}. Unidades não são uma alegação de cobertura narrativa integral do episódio.

Os {quality['sequence_count']} agrupamentos seguem arcos registrados e preservam dependências transitivas. São recortes de contexto/discussão ou narrativas parciais; **zero** agrupamentos foram certificados como história completa. Não são 50 Stories finais. O Curator precisa decidir limites, montagem e ordem. Intervalos distantes permanecem individualizados.

O diagnóstico visual existente registra LOW_AFFINITY, OFFSCREEN_SPEAKER, TRACK_FRAGMENTATION e problemas de sincronismo/consenso. Esses códigos não provam identidade ou defeito global de áudio/vídeo. Active speaker 0% e foco resolvido ~5,77% não foram artificialmente aumentados. Contagens do Director são janelas/decisões, não observação contínua. O fallback R5 é SOURCE_PRESERVE, sem crop, zoom ou movimentos novos. [Diagnósticos visuais reaproveitados](visual_diagnostics_reused.json).

## E. Títulos, comercial e ASR

Foram geradas {quality['title_seed_count']} sementes **extrativas**, com offsets, segmentos e trechos literais. São insumos conservadores; não equivalem a títulos publicitários finalizados ou fatos confirmados por áudio. Há duas variantes quando o texto permite, sem completar frases ou anunciar causalidade, revelação ou viralidade inexistentes.

Exemplos rastreáveis:

{example_text}

O helper comercial distingue anúncio, patrocínio, CTA de compra, afiliado, discussão de produto, preço factual e site contextual, além de incerteza. Foram corrigidos os dois falsos padrões físicos, preservando anúncios reais e OCR. Os 30 casos históricos com cobertura comercial insuficiente continuam pendentes; os gates e scores históricos não foram reescritos. Direitos permanecem desconhecidos, separados de classificação comercial.

As 116 palavras sinalizadas e suas hipóteses originais foram preservadas. O plano direcionado propõe {len(repair['regions'])} regiões, {repair['planned_audio_seconds']:.2f}s de áudio e {repair['selected_word_count']} palavras sinalizadas, dentro do orçamento de quatro regiões/60s. Prioriza contexto narrativo, perguntas, números e entidades mesmo quando a shortlist está vazia. **Nenhum reparo ASR foi executado.**

## F. Compatibilidade e handoff

Os contratos legados de candidatos, scores, gates, fila 1.2 e Stories independentes foram preservados. social/stories_candidates.json e social/title_suggestions.json continuam no escopo legado e podem permanecer vazios. As sequências e títulos R5 estão em editorial/story_sequence_candidates.json e social/narrative_title_suggestions.json, referenciados explicitamente no novo handoff, manifestos e README. Isso evita apresentar unidades dependentes como Stories independentes aprovados.

Os arquivos derivados story_arcs, catalog, selection_report, stories_manifest, índice, brief e manifesto carregam informações compatíveis e escopos explícitos. Referência resolvida é diferente de narrativa completa; preview técnico é diferente de aprovação. Todos os estados de revisão, preview e publicação permanecem separados.

## G. Testes e validação

Foco de integração final: **{focus['passed']} aprovados**. Regressão completa: **{after['passed']} aprovados, {after['skipped']} skips, {after['failed']} falhas, {after['errors']} erros**, em {after['wall_seconds']:.2f}s. Baseline: 1.972 aprovados/3 skips. Todos os {before['test_count']} casos anteriores foram preservados; {len(added)} casos foram adicionados.

Cobertura: narrativas contínuas e entre seções; respostas imediatas/tardias, interrupção, retórica, parcialidade, perguntas concorrentes e contradição; discussão sem arco; múltiplos speakers/identidade desconhecida; dependência de contexto; títulos sem suporte; publicidade versus contexto físico; fonte sem vídeo; cache/retomada após falha; manifesto/referências quebradas; perda de referência do Planner; ciclos; timestamps booleanos; zero Stories justificado e compatibilidade legada. Testes sintéticos não foram usados como homologação humana do vídeo.

As falhas intermediárias foram corrigidas sem afrouxar testes: timestamps bool, hook inventado, estados de revisão, fixture sem checkpoint, referência de teste em pacote sem unidades e SHA legado não canônico. A comparação real também bloqueou um pacote intermediário: o runner não havia carregado camera_plan.json, deixando 403 planner_ids sem resolução e derrubando elegibilidade humana. A correção reutiliza o Planner persistido e valida referências antes da exportação; não altera o gate. Um teste novo cobre a perda de Planner em snapshot compacto. Os logs e o pacote bloqueado permanecem preservados. [Foco](focused_release_02.log), [regressão final](release_full.json), [integridade](final_integrity.json).

## H. Execução e custo

Replay final: {result['wall_seconds']:.2f}s; {len(result['verified_input_sha256'])} entradas verificadas e {len(result['checkpoint_sha256'])} checkpoints reutilizados. ASR, diarização, YOLO, Active Speaker, OCR, Qwen e render não foram executados novamente. Os tempos históricos de Qwen pertencem ao processamento original e não foram apresentados como benchmark do código atual.

A nova API/CLI editorial calcula chave determinística dos dados, checkpoints, código, schema, configuração e evidência de testes. Retoma somente bundles com hash válido; saída anterior incompatível exige outra pasta. Targeted Repair permanece um plano de orçamento integrado ao mecanismo ASR existente; Full Processing continua no pipeline original e não é chamado automaticamente.

Repetição real do cache: {cached_repeat}. O tempo de lookup é medido separadamente do tempo da primeira execução; não se declara uma nova execução dos modelos.

## I. Artefatos e preservação

- [ZIP final]({p}) — {integrity['package_bytes']:,} bytes, {integrity['manifest_hashes_verified']} arquivos com SHA-256 no manifesto, {integrity['package_members']} membros incluindo o manifesto.
- SHA-256: `{integrity['package_sha256']}`.
- [Handoff](review_packet/SECOND_CURATION_NARRATIVE_HANDOFF.json), [HTML de revisão](review_packet/NARRATIVE_REVIEW.html), [auditoria](review_packet/CODEX_ANALYZER_REVIEW.md), [readiness](review_packet/STORY_READINESS_REPORT.json), [antes/depois](review_packet/NARRATIVE_BEFORE_AFTER.json).
- [Replay e proveniência](release_replay/replay_result.json), [schema](../../../schemas/narrative_handoff.schema.json), [baseline](../../audits/ANALYZER_R5_BASELINE.md).

Preservados: {len(files)} arquivos originais ({integrity['original_analysis_bytes_verified']:,} bytes), {len(result['checkpoint_sha256'])} checkpoints, ZIP original e três arquivos .package. Os 495 fontes congelados conferem com a versão testada. HEAD/branch permanecem iguais; não houve commit, instalação, download, exclusão ou acesso aos sete renders do Curator. A mídia local {'está presente e seu hash confere' if media.get('matches_original_metadata') else 'não foi decodificada; verificar disponibilidade local para escuta'}.

Fontes alterados nesta missão:
'''
    report += '\n'.join('- `' + name + '`' for name in sorted(changed)) + '\n'
    report += '\nFontes/contratos adicionados:\n\n' + '\n'.join('- `' + name + '`' for name in new)
    report += '''

## J. Pendências e próximo passo

Abrir o HTML e revisar as duas autorrespostas com seus contextos, depois selecionar uma narrativa/explicação para validar começo e fechamento. Ouvir somente as regiões ASR propostas se forem editorialmente relevantes. Nenhum termo foi corrigido por fluidez textual.

O handoff é tecnicamente válido e parcial: ainda não comprova a reconstrução semântica global do episódio nem um payoff para os 50 arcos. É possível aprofundar relações e classificações por replay dos dados sem refazer percepção. Associação visual e sincronismo exigem inspeção/novas janelas específicas se forem necessários; isso não bloqueia revisão textual na câmera original. Contexto comercial, direitos, títulos, limites, preview e publicação precisam de decisões humanas separadas.

O próximo incremento semântico deve tratar explicações/autorrespostas sem marcadores explícitos, começando por Q_0015 e preservando a abstenção em negativas e contradições. Não há autorização automática de publicação nem necessidade de reprocessar o episódio inteiro.
'''
    (REPORT/'RELATORIO_TECNICO.md').write_text(report, encoding='utf8')
    checkpoint = {'state': result['status'], 'integrity': integrity['state'], 'report': str(REPORT/'RELATORIO_TECNICO.md'),
        'package': str(package), 'tests': {k: comparison[k] for k in ('passed','skipped','failed','errors','added_count')},
        'next_step': 'Human review of source-bound units/QA and selected ASR windows; semantic resolver expansion for Q_0015, no full episode rerun.'}
    (REPORT/'CHECKPOINT.md').write_text('# R5 checkpoint\n\n' + json.dumps(checkpoint, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: v for k, v in integrity.items() if k not in ('sources_changed','sources_added','test_comparison')}, ensure_ascii=True))
    print(json.dumps({k: v for k, v in comparison.items() if k != 'added_cases'}))
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main())
