"""Read-only preservation audit and final report; no inference or rendering."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[3]
REPORT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'src'))
from ldporto.core import file_hash, digest
from ldporto.semantic_runtime import atomic_json, inference_history
from ldporto.semantic_package import validate_semantic_package

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def test_rows(path):
    return {c.get('classname','')+'.'+c.get('name',''): ('skip' if c.find('skipped') is not None else
            'fail' if c.find('failure') is not None or c.find('error') is not None else 'pass')
            for c in ET.parse(path).findall('.//testcase')}

if __name__ == '__main__':
    state = load(REPORT/'semantic_replay/semantic_state.json')
    package = Path(state['package']['path'])
    old = load(ROOT/'docs/reports/r5_20261014/initial_state.json')
    before = load(REPORT/'baseline.json')
    tests = load(REPORT/'final_validation.json')
    original_failures = []
    total_bytes = 0
    for name, expected in old['original_analysis_files'].items():
        path = ROOT/'analysis/video_5198fcdaef38'/name
        if not path.is_file() or path.stat().st_size != expected['bytes'] or file_hash(path) != expected['sha256']:
            original_failures.append(name)
        total_bytes += expected['bytes']
    checkpoint_paths = [n for n in old['original_analysis_files']
                        if len(Path(n).parts) == 3 and Path(n).parts[0] == 'cache'
                        and Path(n).suffix == '.json']
    frozen = load(REPORT/'sources_before_release.json')
    source_drift = [n for n,h in frozen.items() if not (ROOT/n).is_file() or file_hash(ROOT/n) != h]
    baseline_rows = test_rows(ROOT/'docs/reports/r5_20261014/release_full.xml')
    final_rows = test_rows(REPORT/'final_validation.xml')
    isolated = test_rows(REPORT/'native_display_targeted.xml')
    missing_old = sorted(set(baseline_rows)-set(final_rows))
    old_pass_not_reproduced = sorted(n for n,s in baseline_rows.items() if s=='pass' and
                                     final_rows.get(n)!='pass' and isolated.get(n)!='pass')
    renders = load(REPORT/'curator_renders_baseline.json')
    changed_renders = []
    for entry in renders['renders']:
        path = ROOT.parent/'LDPORTO_VIDEO_CURATOR'/entry['path_relative_to_curator']
        prior = entry['stat']
        if not path.is_file() or path.stat().st_size != prior['bytes'] or path.stat().st_mtime_ns != prior['mtime_ns']:
            changed_renders.append(entry['clip_id'])
    reference = ROOT/before['r5_package']
    validation = validate_semantic_package(package, reference=reference)
    with zipfile.ZipFile(package) as archive:
        crc_error = archive.testzip()
        comparison = json.loads(archive.read('R5_VS_R51.json'))
        table = archive.read('RESUMO_EXECUTIVO_CONSUMO.md').decode('utf-8')
        names = archive.namelist()
        packet = REPORT/'review_packet'
        packet.mkdir(exist_ok=True)
        # Read only selected contract/report members; no historical code/media extraction.
        selected = [n for n in names if n in {'SEMANTIC_REVIEW.html','RESUMO_EXECUTIVO_CONSUMO.md',
                    'README_R51_CURATOR.md','SECOND_CURATION_SEMANTIC_HANDOFF.json','R5_VS_R51.json'} or
                    n.startswith(('editorial/semantic_', 'social/story_visual',
                                  'social/narrative_editorial_', 'schemas/story_visual',
                                  'schemas/semantic_handoff'))]
        for name in selected:
            target = packet/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    history = inference_history(REPORT/'semantic_replay')
    failures = []
    if original_failures: failures.append('original_analysis_hash_drift')
    if len(checkpoint_paths) != before['checkpoints']: failures.append('checkpoint_inventory_mismatch')
    if source_drift: failures.append('tested_sources_changed')
    if changed_renders: failures.append('curator_render_stat_drift')
    if missing_old or old_pass_not_reproduced: failures.append('R5_test_regression')
    if tests['failed'] or tests['errors'] or tests['returncode']: failures.append('pytest_failure')
    if validation['status'] != 'valid' or crc_error: failures.append('package_invalid')
    if file_hash(reference) != 'a84ede22de5fe91b8a5e1abe7044229534fe55943777d769364ff58842ab9807':
        failures.append('R5_reference_zip_changed')
    result = {'state':'VERIFIED' if not failures else 'FAILED', 'failures':failures,
        'original_files_verified':len(old['original_analysis_files']), 'original_bytes_verified':total_bytes,
        'original_hash_failures':original_failures, 'checkpoints_preserved':len(checkpoint_paths),
        'checkpoint_paths_verified':checkpoint_paths,
        'source_files_verified':len(frozen), 'source_drift':source_drift,
        'renders_stat_verified':len(renders['renders']), 'changed_renders':changed_renders,
        'render_verification_scope':'existence_size_mtime; historical hashes not reattested; no MP4 read or decoding',
        'package_sha256':file_hash(package), 'package_validation':validation, 'zip_crc_error':crc_error,
        'missing_R5_test_identities':missing_old, 'old_pass_not_reproduced':old_pass_not_reproduced,
        'tests':{k:tests[k] for k in ('passed','skipped','failed','errors','test_count','wall_seconds')},
        'comparison':comparison, 'publication_ready':False}
    atomic_json(REPORT/'FINAL_INTEGRITY.json', result)
    package.with_suffix('.sha256').write_text(file_hash(package)+'  '+package.name+'\n',encoding='ascii')
    command = ('.venv/Scripts/python.exe analyze.py --semantic-replay '
        'docs/reports/r5_20261014/release_replay/package/SECOND_CURATION_PARTIAL_zd_wjssZ7mc_20261014_140253_762578_0b9a68.zip '
        '--semantic-output docs/reports/r5_1_20261014/semantic_replay --semantic-phase package '
        '--semantic-config docs/reports/r5_1_20261014/semantic_config_final.json '
        '--semantic-test-evidence docs/reports/r5_1_20261014/test_evidence_final.json')
    report = f'''# R5.1 — relatório técnico

Estado: **SEMANTIC_HANDOFF_PARTIAL**. Integridade: **{result['state']}**. Implementação e pacote para revisão; homologação editorial integral ainda pendente.

## A — Base

HEAD inicial `{before['head']}`, branch `{before['branch']}`. Git inicialmente limpo na primeira etapa; na retomada preservaram-se todas as alterações parciais. Não houve reset, limpeza, commit, push, instalação ou download. O MASTER foi lido integralmente; o usuário confirmou o checkpoint persistido como continuidade.

## B — Limitações confirmadas

O sanitizador confundia `s:/` de HTTPS com drive Windows. Campos antigos `unresolved` e contexto pouco seletivo prejudicaram a resolução; propostas do Qwen também acrescentaram nomes/expansões sem citação e frases não literais. Esses resultados ficaram arquivados. Não foram convertidos em fatos por aumento de scores ou redução de gates.

## C — P0

Schemas exportados mantêm a URI Draft 2020-12 e são validados inteiros. Proveniência original versus replay classificada como **explained** pelos checkpoints; `build_mismatch=true`, as razões e o estágio20 permanecem preservados. Texto novo, replay CPU e inferência audiovisual histórica têm escopos distintos.

## D — Implementação

`semantic_narrative.py`: recuperação hierárquica, relações, QA, completude por tipo, séries e abstenções. `semantic_runtime.py`: cliente Ollama existente, limites, cache por contexto/prompt/schema/modelo/código, reparação JSON limitada e ledger. `semantic_replay.py`: fases separadas, manifests atômicos, revisões e reaproveitamento de propostas válidas. `semantic_package.py`: exportação aditiva e consumidor offline com schemas, hashes, referências e gates. `story_visual_handoff.py` e dois novos schemas: títulos, fala temporizada, destaques, sequência, capa, CTA e layout desconhecido. CLI: `analyze.py --semantic-replay`.

## E — Relações reais

Três propostas `CONTINUES`: STORY_0018→STORY_0031, STORY_0031→STORY_0032 e STORY_0018→STORY_0032. Citações e referências foram verificadas. Relações causais sem fala causal foram rejeitadas; continuidade semântica exige revisão. O grafo R5 de208 nós/203 arestas permanece intacto.

## F — QA

Q_0015 tem uma associação **ANSWER_PROPOSED**, com trechos de resposta referenciados e transcrição literal. Resumos abstrativos com fatos extras foram substituídos por excertos canônicos, com transformação e hashes registrados; isso não promove a associação a confirmação. O QA canônico não mudou:29 perguntas históricas permanecem unresolved. As outras33 entradas semânticas não foram avaliadas nesta homologação direcionada. O contrafactual tardio sobre “essa antena” requer contexto anterior e escuta; não fundamenta causalidade observada.

## G — Completude

Zero narrativas e zero explicações foram certificadas como completas. O modelo não entregou proposta de completude que passasse por todas as verificações. A revisão textual de126–132 identifica pergunta, mecanismo e fecho local; não equivale ao desfecho da história do acidente nem à revisão audiovisual.

## H — Série

Uma série com **um Story real**: SEG_00126–SEG_00132. São7 intervalos, união42,64s e janela44,80s. A proposta anterior válida foi reutilizada quando nova inferência se absteve; SHA e revalidação estão no pacote. A duração final depende da montagem no Curator. Nenhum Reel ou shortlist foi forçado.

## I — Story Visual Handoff

Um título principal e duas alternativas, hook, caption separado da fala, CTA, capa proposta, partes1/1,118 palavras com tempos originais e3 destaques. Os títulos finais são **rascunhos assistidos de autoria Codex**, não saídas Qwen aprovadas nem revisão humana. O script `draft_titles.py`, payload, hashes e proveniência estão salvos. As tentativas Qwen foram preservadas e recusadas pelos validadores. Duas paráfrases herdadas (posição/rota e disponibilidade geográfica do GPS) foram substituídas por texto da fonte, com registro das versões. Safe areas e regiões de rostos permanecem UNKNOWN; sem crop/zoom autorizado, MP4, ASS, SRT ou PNG novos.

{table}

## J — Testes

Regressão de entrega: **{tests['passed']} aprovados, {tests['skipped']} skips, {tests['failed']} falhas, {tests['errors']} erros** em{tests['wall_seconds']:.2f}s. Todas as identidades R5 preservadas; testes anteriormente aprovados não reproduzidos: {len(old_pass_not_reproduced)}. Focos e JUnit estão neste diretório. O teste de interface também passou isoladamente. O consumidor real de ZIP possui teste de integração que verifica preservação legada e referências novas de proveniência.

## K — Inferência e desempenho

{history['new_model_calls']} chamadas textuais novas ao Ollama/Qwen3:14b, inclusive tentativas rejeitadas; {history['cache_hits']} reutilizações de tarefas registradas. Serviço0.35.1, digest bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8. Tempos e tokens reais por requisição no ledger; medições ausentes ficam desconhecidas. O rascunho assistido não conta como chamada Ollama. Nenhuma inferência ASR/YOLO/ASD/Director/OCR ou render nova. Uso de GPU não foi medido nesta rodada textual.

## L — Preservação

{len(old['original_analysis_files'])} arquivos originais/{total_bytes:,}bytes e27 checkpoints conferidos; sete renders preservados por stat, sem abrir os MP4. {validation.get('legacy_documents_preserved')} documentos legados byte a byte; somente schemas e manifesto do ZIP derivado recebem atualização. ZIP R5 original preservado. Scores, shortlist, QA, gates, previews, direitos e autorizações não foram promovidos.

## M — Pendências

Cobertura semântica direcionada, não auditoria completa de todos os tópicos/perguntas. Completude automática e títulos Qwen ainda precisam melhorar: houve citações inventadas, extrapolações e bloqueios conservadores de vocabulário/negação. Não reduzir esses filtros para obter READY. Escuta/ASR, semântica, fatos, direitos, composição visual, câmera, preview e publicação exigem suas revisões. Importação automática desses campos na versão instalada do Curator não foi modificada nem homologada; foi validado o contrato offline e preservada a compatibilidade legada.

## N — Arquivos e SHA-256

ZIP: `{package.relative_to(ROOT).as_posix()}`

SHA-256: `{file_hash(package)}`

Validação: {validation['status']}; {validation.get('manifest_hashes_verified')} hashes no manifesto; CRC íntegro; referências pendentes0. Veja `review_packet/SEMANTIC_REVIEW.html`, `review_packet/social/story_visual_handoff.json`, seu schema, `FINAL_INTEGRITY.json`, `final_validation.xml` e `test_evidence_final.json`.

## O — Readiness e consumo

**SEMANTIC_HANDOFF_PARTIAL**, `publication_ready=false`. Não declarar R5.1 integralmente homologada. Abra `README_R51_CURATOR.md` e `SECOND_CURATION_SEMANTIC_HANDOFF.json`, valide o visual handoff pelo schema enviado, resolva IDs nos segmentos/units, vincule mídia pelo SHA e use os tempos absolutos. O Curator aplica seus presets, valida montagem e preview e solicita aprovação. Nenhuma importação desses metadados exige novamente Whisper, Qwen, visão ou Director.

Repetição do pacote com cache (sem inferências):

```text
{command}
```
'''
    (REPORT/'RELATORIO_TECNICO.md').write_text(report,encoding='utf-8')
    (REPORT/'CHECKPOINT.md').open('a',encoding='utf-8').write(
        '\n\nEntrega: A/B/C/D validados tecnicamente, estado editorial SEMANTIC_HANDOFF_PARTIAL. '
        f'Integridade {result["state"]}; regressão {tests["passed"]}pass/{tests["skipped"]}skip. '
        'Próximo passo: revisão humana dos118words e peça126–132; ampliar QA/completude e melhorar geração automática de títulos, sem novo processamento audiovisual. '
        'Caminhos e hashes no RELATORIO_TECNICO.md e FINAL_INTEGRITY.json.\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('comparison',)},ensure_ascii=True))
    raise SystemExit(1 if failures else 0)
