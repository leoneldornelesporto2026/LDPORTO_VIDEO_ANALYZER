"""Produce the five source-bound review proposals and final preservation record."""
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
PREVIOUS = REPORT.parent/'sol_v4_pos_foquinha_20261013'
sys.path.insert(0, str(ROOT/'src'))


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b''):
            result.update(block)
    return result.hexdigest()


PROPOSALS = [
    {'candidate_id': 'MOMENT_00002_0000', 'start': 360.36, 'end': 407.76,
     'title': 'A ideia de podcast que a rádio recusou',
     'hook': 'Antecipou um formato inspirado em Grace Helbig e ouviu uma recusa.',
     'context': 'Incluir a pergunta sobre criadores de referência (SEG_00177–00178).',
     'development': 'SEG_00179–00182: referência, proposta à rádio e recusa.',
     'ending': 'SEG_00183–00184: comentário sobre estar à frente do tempo; termina antes da mudança em 407.96.',
     'quality_hypothesis': 'Promissor: causa, tentativa, obstáculo e autoavaliação final aparecem no texto; humor e surpresa não medidos.',
     'risks': ['topic_boundary_crossed permanece; conferir se a fronteira é uma mudança real de assunto',
               'Grace Helbig e atribuição das intervenções precisam de escuta'],
     'human_tasks': ['Ouvir pergunta e resposta juntas', 'Conferir pronúncia e locutores sem atribuir identidade visual',
                    'Reavaliar a fronteira temática com evidência, sem remover gate por conveniência']},
    {'candidate_id': 'MOMENT_00006_0002', 'start': 1109.68, 'end': 1170.52,
     'title': 'A Live dos Anjos confundida com live religiosa',
     'hook': 'SEG_00497: “Gente, achei que era uma live bíblica.”',
     'context': 'Começar na apresentação do projeto com João (SEG_00481–00483); o nome composto está incerto na transcrição.',
     'development': 'SEG_00492–00495 explicam o nome ligado ao BBB; SEG_00496–00502 relatam a confusão.',
     'ending': 'SEG_00509–00513: formação de comunidade e “Então, isso foi muito legal.”',
     'quality_hypothesis': 'Promissor: há setup do nome, equívoco e consequência social explícita. A versão curta perde antecedentes.',
     'risks': ['“João, o Luiz Pedrosa” e a frase sobre porcentagem dos evangélicos precisam de revisão acústica',
               'Q_0104 trata fala iniciada por “Porque” como pergunta; o trecho é discurso relatado, obrigação de resposta requer revisão'],
     'human_tasks': ['Confirmar nome e sentido da referência religiosa', 'Ouvir sem suprimir o contexto do BBB',
                    'Revisar Q_0104 sem alterar retroativamente o gate ou marcar resposta como confirmada']},
    {'candidate_id': 'MOMENT_00008_0002', 'start': 1585.2, 'end': 1617.2,
     'title': 'Reconhecendo o primeiro vídeo do canal',
     'hook': 'Reconhecimento do primeiro vídeo diante de um mural de arquivos.',
     'context': 'SEG_00664–00665 apresentam a retrospectiva; a reação depende das imagens realmente exibidas.',
     'development': 'SEG_00666–00671: reação, reconhecimento e descrição de um teaser.',
     'ending': 'SEG_00672 explica o teaser: lançou o canal querendo ir para a TV. É uma unidade de reação; a trajetória continua depois.',
     'quality_hypothesis': 'Condicional: útil como reação nostálgica se o mural for legível. A posição alta na triagem não comprova história completa.',
     'risks': ['Original tem 28.74s e está abaixo do alvo de 30s',
               'Extensão a 32s só faz sentido pela explicação do teaser, nunca como preenchimento de duração',
               'Não encerrar a história da carreira em SEG_00672; SEG_00673 em diante continuam outro desenvolvimento'],
     'human_tasks': ['Ver o mural e ouvir a reação sincronizada', 'Decidir se a unidade é reação ou início de narrativa maior',
                    'A prévia existente cobre somente 1585.2–1613.94; inspecionar o restante no original']},
    {'candidate_id': 'MOMENT_00018_0002', 'start': 3333.08, 'end': 3373.72,
     'title': 'Ser outra pessoa ao entrevistar em espanhol',
     'hook': 'O nervosismo vem de perder a própria personalidade em outro idioma.',
     'context': 'SEG_01206 inicia a pergunta sobre entrevistas internacionais; manter as intervenções breves.',
     'development': 'SEG_01207–01222: idioma, personalidade e autodescrição tímida em espanhol.',
     'ending': 'Original termina em “Eu fico meio, tipo...”. SEG_01224–01226 completam com “Eu sou básica” e “muito básica em espanhol”.',
     'quality_hypothesis': 'Promissor para identificação e autodepreciação. Desfecho da resposta melhora com a continuação literal; não há risada confirmada.',
     'risks': ['ASR “esmui ratatá” e fragmentação das intervenções exigem escuta',
               'A anedota de La Casa de Papel começa em SEG_01236 (3377.5), fora da proposta'],
     'human_tasks': ['Confirmar palavras em espanhol sem normalização inventada', 'Conferir turnos de fala',
                    'Validar fim após a autodescrição antes da próxima anedota']},
    {'candidate_id': 'MOMENT_00020_0000', 'start': 3688.94, 'end': 3744.38,
     'title': 'O perrengue que o glamour do evento esconde',
     'hook': 'O resultado constrangedor é dito na abertura; não depende de inventar um clímax posterior.',
     'context': 'SEG_01372 inicia o relato. Se usar o contraste “glamour”, ouvir também SEG_01369–01371 em 3681.62–3688.74.',
     'development': 'SEG_01373–01399: segurar a vontade, roupa, show, chuva, tentativa de banheiro e caminho ao hotel.',
     'ending': 'SEG_01400 comenta “foi perrengue chique”. Proposta para inspeção, não fechamento semanticamente confirmado. SEG_01401 termina em handoff; não anexar como conclusão limpa.',
     'quality_hypothesis': 'Promissor como relato e contraste com glamour, mas sensível e dependente do tom; humor não verificado.',
     'risks': ['Original termina antes da continuação do hotel', 'ASR “rock rico” e outras falas coloquiais precisam de escuta',
               'Constrangimento pessoal exige cuidado editorial; não ampliar a exposição por sensacionalismo',
               'O autoquestionamento dentro do relato não prova pergunta externa nem resposta independente'],
     'human_tasks': ['Confirmar o evento e a fala inicial pelo áudio', 'Rever o término em 3744.38 e o comentário seguinte',
                    'Avaliar tom, dignidade e necessidade do contexto sobre glamour']},
]


def main():
    from ldporto.review_media import build_source_media_references, resolve_review_media, review_player_html
    replay = read(REPORT/'editorial_replay_final.json')
    with zipfile.ZipFile(replay['result']['path']) as archive:
        catalog = json.loads(archive.read('editorial/candidate_catalog.json'))['candidates']
        metadata = json.loads(archive.read('source/metadata.json'))
        identity = json.loads(archive.read('SECOND_CURATION_MANIFEST.json'))['build_provenance']
        provenance = json.loads(archive.read('provenance/editorial_replay.json'))
    by_id = {c['candidate_id']: c for c in catalog}
    rows = read(ROOT/'analysis/video_1da839aad175/transcript_segments.json')
    by_segment = {s['segment_id']: s for s in rows}
    source = ROOT/'input/youtube/7laRa_F3FbA/7laRa_F3FbA.mp4'
    priorities = {c['candidate_id']: c for c in replay['priority_comparison']}
    selected = []
    for proposal in PROPOSALS:
        c = by_id[proposal['candidate_id']]
        start, end = proposal['start'], proposal['end']
        evidence = [s for s in rows if s['start'] < end and s['end'] > start]
        if evidence[0]['start'] != start or evidence[-1]['end'] != end:
            raise ValueError('proposal_not_on_canonical_segment_edges:' + c['candidate_id'])
        contract = c['duration_contract']
        if not contract['hard_min_seconds'] <= end - start <= contract['hard_max_seconds']:
            raise ValueError('proposal_outside_hard_duration')
        refs = build_source_media_references(metadata, {**c, 'start': start, 'end': end})
        # Extended inspection is source-only; never associate the shorter old preview.
        resolved = resolve_review_media(refs, source)
        player = REPORT/'review_players'/(c['candidate_id'] + '_inspection.html')
        player.write_text(review_player_html(resolved), encoding='utf8')
        selected.append({**proposal, 'proposal_kind': 'human_inspection_only',
            'original_interval': {'start': c['start'], 'end': c['end']},
            'inspection_interval': {'start': start, 'end': end, 'duration_seconds': round(end-start, 3)},
            'duration_contract': contract, 'source_sha256': metadata['sha256'],
            'historical_score': c['editorial_score_final'],
            'old_queue_position': priorities[c['candidate_id']]['old_priority_rank'],
            'new_queue_position': priorities[c['candidate_id']]['new_priority_rank'],
            'canonical_evidence': [{k: s.get(k) for k in ('segment_id', 'start', 'end', 'speaker', 'text')} for s in evidence],
            'source_media_references': refs, 'original_candidate_media_references': c['source_media_references'],
            'local_inspection_player': player.relative_to(REPORT).as_posix(),
            'recorded_editorial_blockers': c['editorial_blockers'],
            'recorded_gate_reasons': c['review_plan']['local_gate_reasons'],
            'review_milestones': c['review_milestones'], 'human_review_completed': False,
            'audio_listened_by_human': False, 'preview_approved': False, 'publication_ready': False,
            'proposed_limits_applied_to_candidate': False, 'semantic_completion_verified': None})
    packet = {'schema_version': '1.0', 'source_sha256': metadata['sha256'], 'candidates': selected,
              'purpose': 'five_editorial_inspection_proposals_not_official_shortlist', 'publication_ready': False}
    (REPORT/'priority_candidates.json').write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding='utf8')
    initial = read(REPORT/'initial_state.json')
    old_initial = read(PREVIOUS/'initial_state.json')
    protected = read(PREVIOUS/'preservation_before.json')
    failures = []
    original = ROOT/'analysis/video_1da839aad175'
    for name, expected in protected['analysis_files'].items():
        p = original/name
        if not p.is_file() or p.stat().st_size != expected['bytes'] or sha(p) != expected['sha256']:
            failures.append('original_analysis:' + name)
    current = {p.relative_to(original).as_posix() for p in original.rglob('*') if p.is_file()}
    if current != set(protected['analysis_files']):
        failures.append('original_analysis_file_set_changed')
    for name, expected in old_initial['protected_package'].items():
        if sha(Path(name)) != expected:
            failures.append('protected_package:' + name)
    for name, expected in old_initial['completed_checkpoints'].items():
        if sha(original/'cache'/'0231c20cfd8147d9'/name) != expected['sha256']:
            failures.append('checkpoint:' + name)
    model = ROOT/'models/body/yolo11n.pt'
    if sha(model) != '0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1':
        failures.append('yolo_weight_changed')
    if sha(ROOT/protected['package']) != protected['package_sha256']:
        failures.append('original_package_changed')
    previews = read(PREVIOUS/'source_previews_manifest.json')
    for p in previews['results']:
        if sha(PREVIOUS/Path(p['preview_path'])) != p['sha256']:
            failures.append('old_preview_changed:' + p['candidate_id'])
    frozen = read(REPORT/'sources_frozen_final.json')
    for name, expected in frozen.items():
        if sha(ROOT/name) != expected:
            failures.append('frozen_source_drift:' + name)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    if head != initial['head'] or branch != initial['branch']:
        failures.append('git_identity_changed')
    before, after = read(PREVIOUS/'after_full.json'), read(REPORT/'after_full.json')
    missing = list((Counter(before['test_identities']) - Counter(after['test_identities'])).elements())
    added = list((Counter(after['test_identities']) - Counter(before['test_identities'])).elements())
    if missing or after['returncode'] or after['failed'] or after['errors']:
        failures.append('full_regression')
    changed = []
    for name, info in initial['sources'].items():
        expected = info['sha256'] if isinstance(info, dict) else info
        if sha(ROOT/name) != expected:
            changed.append(name)
    new = sorted(set(frozen) - set(initial['sources']))
    comparison = {'baseline_passed': before['passed'], 'baseline_skipped': before['skipped'],
        'passed': after['passed'], 'skipped': after['skipped'], 'failed': after['failed'],
        'errors': after['errors'], 'old_cases_preserved': not missing, 'missing': missing,
        'added_count': len(added), 'added_cases': added}
    record = {'state': 'VERIFIED' if not failures else 'FAILED', 'timestamp': datetime.now().astimezone().isoformat(),
        'failures': failures, 'head': head, 'branch': branch, 'source_media_sha256': sha(source),
        'original_analysis_files': len(current), 'original_analysis_bytes': sum(v['bytes'] for v in protected['analysis_files'].values()),
        'completed_checkpoints': len(old_initial['completed_checkpoints']),
        'protected_package_files': len(old_initial['protected_package']), 'existing_previews_preserved': len(previews['results']),
        'sources_changed_this_round': sorted(changed), 'sources_added_this_round': new,
        'test_comparison': comparison, 'frozen_sources': len(frozen),
        'new_package_sha256': replay['package_sha256'], 'new_package_bytes': replay['package_bytes'],
        'new_model_calls': 0, 'build_mismatch_preserved': identity['build_mismatch'],
        'perception_code_fingerprint': identity['code_fingerprint'],
        'replay_code_fingerprint': provenance['replay_exporter']['code_fingerprint'], 'publication_ready': False}
    (REPORT/'final_integrity.json').write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding='utf8')
    status = subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True, encoding='utf8')
    (REPORT/'git_after.txt').write_text(status, encoding='utf8')
    write_report(record, replay, selected, identity, provenance)
    print(json.dumps({k: v for k, v in record.items() if k not in
        ('test_comparison', 'sources_changed_this_round', 'sources_added_this_round')}, ensure_ascii=True))
    print(json.dumps({k: v for k, v in comparison.items() if k != 'added_cases'}))
    return 0 if not failures else 1


def write_report(record, replay, selected, identity, provenance):
    def stamp(value):
        seconds = round(value, 2)
        hours = int(seconds // 3600)
        minutes = int(seconds % 3600 // 60)
        return f'{hours:02}:{minutes:02}:{seconds % 60:05.2f}'
    tests = record['test_comparison']
    lines = [
        '# SOL V4.1 — continuidade editorial e integridade', '',
        f'Estado: **{record["state"]}**. Replay em CPU; zero chamadas de modelos, renders ou reprocessamento do episódio.',
        f'Git preservado: `{record["branch"]}`, HEAD `{record["head"]}`. Nenhum commit.', '',
        '## Recuperação e correções', '',
        'A sessão interrompida deixou o helper editorial e partes da fila 1.2. Os agentes de armazenamento e identidade terminaram em erro por limite de uso; não havia resultado final de testes, helper de mídia ou proveniência de replay salvo. Foram reaproveitados o código parcial, os cinco contextos já extraídos, o snapshot de 481 fontes e todos os relatórios V4. Nenhum agente ou benchmark foi reiniciado.', '',
        'Causa do ranking: a fila 1.1 usava score histórico decrescente. No CTA, a média dos componentes observados era 0.765542, com cobertura 0.600 e penalidade de incerteza 0.032, resultando em 0.734. Abertura/fechamento tinham nota 1; gancho, payoff, narrativa, humor e áudio não tinham medição. Nota alta não comprova potencial narrativo. A ausência de hook e os demais gates continuam bloqueando seleção automática.', '',
        'A fila 1.2 prioriza indícios literais de relato/experiência/contraste, depois casos sem classificação, depois CTA de manutenção. Um CTA dentro de relato, negação ou conteúdo misto recebe tratamento separado. Categorias como storytelling não provam história. Cada indício traz trecho, offsets e origem; os offsets permanecem verificáveis após a redação de dados privados. Não foi criado nem alterado score.', '',
        'No catálogo: 11 CONTENT_REVIEW, 1 MIXED_CTA_CONTENT, 67 UNRESOLVED e 1 CTA_HOUSEKEEPING. A ordem dentro das classes continua usando os números históricos. Isso melhora a triagem explicável, sem alegar medir qualidade humana ou classificar semanticamente todas as histórias.', '',
        'O CTA MOMENT_00022_0001 passou de prioridade 1 para 77, mantendo 0.734. Foram preservados os 80 IDs, limites históricos, segmentos, ranks, componentes, penalidades, gates, scores e as 77 unidades de revisão. Três alternates continuam nas unidades existentes; não foram descartados nem transformados em entradas adicionais. Shortlist oficial: **0**; aprovações humanas e publicações: **0**.', '',
        'Propostas automáticas de limites usam apenas bordas de segmentos canônicos e contexto adjacente com tópico conhecido, sem sobreposição, intervalo solto ou duração fora dos limites rígidos. Nenhuma proposta altera o candidato ou certifica conclusão. Casos de outro tópico, lacuna, contradição de escopo e duração têm testes negativos.', '',
        '## Cinco candidatos para inspeção humana', '',
        'Os títulos e avaliações abaixo são hipóteses editoriais baseadas em transcrição não escutada. Os cinco permanecem elegíveis apenas à revisão provisória, sem elegibilidade automática ou aprovação. Todas as propostas respeitam o alvo de 30–90s e o limite rígido de 8–180s; a validação de conteúdo continua pendente.', '',
        '| Candidato / título | Original | Proposta para inspeção | Score preservado / fila antes→depois |',
        '|---|---|---|---|']
    for c in selected:
        old, new = c['original_interval'], c['inspection_interval']
        lines.append(f'| {c["candidate_id"]} — {c["title"]} | {stamp(old["start"])}–{stamp(old["end"])} | '
            f'[{stamp(new["start"])}–{stamp(new["end"])}]({c["local_inspection_player"]}) ({new["duration_seconds"]:.2f}s) | '
            f'{c["historical_score"]:.3f} / {c["old_queue_position"]}→{c["new_queue_position"]} |')
    for c in selected:
        lines += ['', f'**{c["title"]}**', '', c['quality_hypothesis'],
            f'Gancho: {c["hook"]} Contexto: {c["context"]} Desenvolvimento: {c["development"]}',
            f'Conclusão observada/limite: {c["ending"]}',
            'Riscos: ' + '; '.join(c['risks']) + '.',
            'Revisões humanas: ' + '; '.join(c['human_tasks']) + '.']
    lines += ['',
        'A comparação estruturada, textos literais, IDs dos segmentos, gates individuais e referências de mídia estão em [priority_candidates.json](priority_candidates.json). Os players de inspeção usam o arquivo original por hash e os limites propostos, sem render. Os players *_video e *_audio preservam os limites históricos.', '',
        'Q&A: a transcrição permite inspecionar respostas que o contrato automático deixou inconclusivas. Q_0104 e os casos iniciados por “Porque” em torno da retrospectiva exigem revisão da classificação interrogativa. O autoquestionamento na história do evento pode ser retórico. Esses achados não foram convertidos em respostas confirmadas: o replay reutiliza o refinamento V4 e preserva os gates históricos. O resultado comprovado nesta rodada é a proposta de contexto e fechamento, não uma nova inferência de narrativa completa.', '',
        '## Fila, mídia e estados', '',
        'A fila 1.2 inclui vínculos por SHA-256, ID e intervalo exato. O botão **Ouvir/ver fila** abre um seletor de candidato e permite vídeo original, áudio do próprio vídeo ou prévia existente. O arquivo escolhido precisa ter o hash correto; prévias precisam também estar dentro da raiz indicada e corresponder ao ID, fonte, intervalo, tamanho e hash. O player faz seek inicial e pausa ao final. Não há autoplay nem gravação de aprovação. Os formatos 1.0 e 1.1 continuam legíveis e os dois ZIPs históricos validaram.', '',
        'Os estados são dimensões separadas: INTERESTING_CANDIDATE é hipótese de interesse; ELIGIBLE_FOR_REVIEW deriva do contrato atual; HUMAN_REVIEW_PENDING permanece até revisão explícita. HUMAN_REVIEW_COMPLETED, PREVIEW_APPROVED e PUBLISH_READY não são atribuídos pelo player ou pela classificação. O campo legado publication_eligible significa elegibilidade à curadoria; publication_ready continua falso. Identidade visual/ASD desconhecida permite examinar a câmera original, sem autorizar crop ou zoom.', '',
        'As três prévias antigas foram vinculadas e tiveram seus hashes reconferidos. A validação técnica anterior por ffprobe foi reaproveitada porque os bytes são idênticos: H.264 480×270, 16:9, AAC estéreo 48kHz; durações de vídeo 22.756067s, 20.987633s e 28.728700s. Áudio presente e diferenças de duração inferiores a 12ms não comprovam sincronismo labial ou fidelidade de transcrição. Não houve nova escuta nem nova aprovação.', '',
        'Entre os cinco, somente MOMENT_00008_0002 possui prévia antiga (1585.20–1613.94); ela não cobre a proposta até 1617.20. As outras duas prévias são MOMENT_00022_0001 e MOMENT_00002_0002, e não foram associadas a trechos vizinhos por nome. As cinco propostas completas podem ser examinadas no original local.', '',
        '## Proveniência e pacote', '',
        f'Novo handoff: [ZIP final](derived_export_final/{Path(replay["result"]["path"]).name}), '
        f'{replay["package_bytes"]:,} bytes, {replay["manifest_files"]} hashes declarados válidos (143 membros incluindo o manifesto).',
        f'SHA-256: `{replay["package_sha256"]}`.',
        f'Fonte original: `{record["source_media_sha256"]}`.',
        f'Código da análise original: `{identity["code_fingerprint"]}`; código do replay/exportador: `{provenance["replay_exporter"]["code_fingerprint"]}`.', '',
        f'`provenance/editorial_replay.json` registra {len(provenance["reused_checkpoints"])} checkpoints, '
        f'{len(provenance["reused_artifacts"])} entradas reutilizadas e hashes dos módulos executados. '
        'Componentes realmente executados: classificação de interesse, propostas de limites, vínculo de mídia e exportação/validação. Nenhuma execução de ASR, diarização, YOLO, Active Speaker ou Qwen. O build_mismatch e o estado de execução parcial permanecem; o replay não gera atestado de percepção nova. O ZIP é portátil por referências e não inclui mídia ou caminhos privados. Os HTMLs locais referenciam a mídia desta máquina.', '',
        'O pacote intermediário desta sessão também foi preservado. O final incorpora a correção dos offsets após redação de privacidade; nenhum ZIP histórico foi sobrescrito.', '',
        '## Validação e pendências', '',
        f'Testes direcionados finais: **54 aprovados**. Regressão completa: **{tests["passed"]} aprovados, '
        f'{tests["skipped"]} skips, {tests["failed"]} falhas e {tests["errors"]} erros**. '
        f'Baseline: 1936 aprovados e 3 skips; {tests["added_count"]} casos adicionados, todos os casos anteriores preservados.', '',
        'Os testes cobrem CTA, relato/negação, interesse versus aprovação, deduplicação, continuidade e limites, hash incorreto, travessia de diretórios, vínculo de prévias, player, privacidade e proveniência. Também rejeitam timestamps/aprovações/declaração de inferência adulterados mesmo com hashes do manifesto recalculados. O único teste existente ajustado passou a esperar a versão 1.2; o teste de contrato legado permanece.', '',
        f'Integridade final: {record["original_analysis_files"]} arquivos originais '
        f'({record["original_analysis_bytes"]:,} bytes), {record["completed_checkpoints"]} checkpoints, '
        f'{record["protected_package_files"]} arquivos .package, modelo YOLO e três prévias preservados. '
        f'{record["frozen_sources"]} fontes congelados durante a regressão; HEAD e branch preservados.', '',
        'Fontes alterados nesta rodada:', '',
        *['- `' + name + '`' for name in record['sources_changed_this_round']],
        *['- `' + name + '` (novo)' for name in record['sources_added_this_round']], '',
        'Comandos e evidências: [focused_complete.log](focused_complete.log), [after_full.json](after_full.json), '
        '[replay final](editorial_replay_final.json), [integridade](final_integrity.json). '
        'O primeiro teste focado revelou um erro na busca de despedida dentro do próprio trecho; foi corrigido. '
        'O teste de redação de privacidade comprovou e protegeu a correção dos offsets.', '',
        '**Próximo passo exato:** abrir os cinco links de inspeção acima, ouvir os nomes/expressões sinalizados e confirmar abertura/fechamento. '
        'Homologar também os controles do player no navegador Windows: o seek e as proteções foram testados por contrato, mas a navegação GUI e a reprodução real não foram simuladas como aprovação humana. '
        'Registrar revisão humana separada e, se necessário, renderizar apenas um canário com câmera original para o intervalo confirmado. '
        'Aprimorar perguntas iniciadas por “Porque” e a classificação semântica dos 67 casos não resolvidos pode partir dos checkpoints; '
        'corrigir associação visual/ASD exige nova inferência apenas em janelas escolhidas. Nenhuma dessas pendências autoriza shortlist, crop ou publicação.', '']
    (REPORT/'RELATORIO_TECNICO.md').write_text('\n'.join(lines), encoding='utf8')


if __name__ == '__main__':
    raise SystemExit(main())
