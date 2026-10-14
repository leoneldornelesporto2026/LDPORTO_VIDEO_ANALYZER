# SOL V4 — pacote C: armazenamento e proveniência

Implementado após o encerramento da análise e a validação dos pacotes A/B. Nenhuma mídia, modelo, análise anterior ou checkpoint histórico foi modificado por este pacote. Nenhuma inferência, chamada Ollama, instalação ou download foi executado.

## Alterações

- Novo codec físico `asd_mapping_projection_v1`, versão 1.0, em `checkpoint_storage.py`. Aplica-se somente às novas escritas de `10_active_speaker` quando todos os intervalos correspondem exatamente aos mappings sem os três aliases legados. Qualquer divergência, incluindo tipos JSON diferentes ou zero com sinal diferente, preserva o documento completo. Evidência adicional nunca é descartada.
- `data.intervals` físico contém referência estrita; o leitor restaura a lista e containers aninhados independentes. Marcadores desconhecidos, referências inválidas e contagens incompatíveis causam erro. Documentos legados sem marcador permanecem intactos. Checksum lógico e recibo continuam sobre os dados completos; SHA de arquivo continua sobre os bytes físicos.
- Leitores centrais e auditorias S5/S6 suportam a hidratação, inclusive em ZIP. Não há caminhos externos, avaliação de expressões ou referências executáveis no codec.
- `write_json` agrupa tokens antes de escrever, mantendo os mesmos bytes, arquivo temporário exclusivo, substituição atômica, cleanup de temporários, flush e fsync.
- `verify_receipt` calcula o checksum do payload uma vez por chamada. Comparações de recibo, verificações do manifesto e ambas as barreiras de checksum dos artefatos continuam ativas.
- Snapshot de entrada do relatório é serializado sincronicamente antes de qualquer mutação das decisões finais. Fingerprint lógico e hash do arquivo são calculados uma vez. Etapa 21 continua consumindo exclusivamente o snapshot isolado e verificado de disco.
- `artifact_metrics.json`, diagnóstico externo já existente, registra fingerprint, escrita e hash do snapshot, geração do recibo inicial e finalização incluindo etapa 21/recibo final. O escopo exclui a escrita desse próprio diagnóstico; nenhum documento protegido pelo recibo final é reescrito após sua emissão.
- Seis sidecars existentes passam a referências: evidência ASD, diagnósticos e afinidade speaker/person, perfil semântico, revisão editorial Ollama e gráficos de broadcast. A versão aditiva das referências é 1.1. Coleções cujo sidecar esteja ausente permanecem inline.
- Caches semânticos 4.3 guardam metadados originais opcionais com checksum, duração e escopo. Cache hit mostra estes dados em campo histórico separado, sem contabilizá-los como novas chamadas/tokens. Caches antigos continuam reutilizáveis; metadados adulterados não são apresentados. Prompt, modelo, perfil, modo compacto e orçamento de chamadas foram preservados.

## Validação real

Comando executado em `storage_focused_run.json`: sete arquivos de testes, incluindo `test_sol_v4_checkpoint_storage.py`, com `pytest -q -rs` e JUnit.

**131 passed em 28,39 s; exit code 0. São 35 casos novos do pacote C.** Wall time do wrapper: 28,8406 s. Artefatos: `storage_focused.log`, `storage_focused.xml`, `storage_focused_run.json`; hashes dos fontes congelados: `storage_freeze.json`.

Os casos exercitam equivalência lógica, isolamento após mutação, fallback que preserva diferenças, marcadores inválidos, hashes físicos adulterados, checkpoint real do produtor com cache hit sem reescrita, manutenção das duas barreiras dos artefatos, igualdade dos bytes UTF-8 acima do limite do buffer, leitores S5/S6 de diretório/ZIP, sidecars/hidratação/corrupção, snapshot isolado do relatório, gates e custos históricos de cache separados dos custos atuais. São testes offline com fixtures declaradas, sem precisão audiovisual presumida.

## Limites e estado

Compatibilidade e integridade focadas: **VERIFIED**. Benchmark local do checkpoint longo concluído pela raiz em processos isolados, sem inferência e sem editar a fonte histórica:

| Medição | Antes | Depois | Estado |
|---|---:|---:|---|
| Bytes físicos | 331.319.797 | 172.939.789 | VERIFIED: redução de 47,8028% |
| Escrita, incluindo compactação no novo caminho | 21,03596 s | 3,96198 s + 10,61788 s = 14,57986 s | VERIFIED neste ensaio |
| Verificação do recibo sobre o mesmo payload lógico | 27,24666 s | 8,61160 s | VERIFIED neste ensaio |
| Pico de RAM da transformação completa | 1.501.851.648 B | 1.501.179.904 B | Praticamente igual; ganho relevante não demonstrado |
| Mappings/intervals após hidratação | 92.974 / 92.974 | 92.974 / 92.974 | VERIFIED |

Evidências: `storage_before/result.json`, `storage_after/result.json` e `storage_encoded_read/result.json`. A releitura do arquivo compacto em outro processo produziu o mesmo SHA lógico `cec3c62a675a94a2fa6501eb946f4dcaf32a5dda47ea7005200e345577ee7ba3`; recibo `verified_partial`, preservando o estado anterior. SHA físico original `33b372104fcc0aabad064b04929502263c9d68441cbb5385ad3787d587a962c1`; SHA físico compacto `ecc5f00a133b4bcf7fb0defd8f007f32ce4836924a7af824c9559c9aaf9b7d0a`. Bytes diferentes são esperados; conteúdo lógico e evidência foram preservados.

São observações de um ensaio por caminho, sem estimativa de variância, controle de cache do sistema operacional ou garantia de aceleração da análise completa. A transformação parte do JSON legado já hidratado, por isso a redução de disco não implicou redução relevante de seu pico de RAM. A releitura compacta foi medida separadamente; seu escopo não é idêntico ao da transformação completa. Não há alegação de ganho de inferência Qwen, identidade, ASD ou qualidade editorial por estas mudanças de armazenamento.

A regressão completa pertence à validação integrada coordenada pela raiz. O resultado de 131 testes acima corresponde ao pacote C antes do canário adicional de compatibilidade S6, cuja inclusão foi coordenada pelo revisor B; o freeze final integrado deve prevalecer sobre `storage_freeze.json` inicial.

A alteração de `core.py` modifica o fingerprint dos estágios que o incluem. Escritas futuras registram este invalidator no mecanismo existente; a análise concluída não foi retomada nem recomposta. A leitura compatível de históricos não transforma evidência antiga em execução do código atual.

## Fechamento integrado

O canário S6 foi seguido do canário de exportação de fontes: checkpoints brutos de benchmark em `docs/reports` permanecem no disco e são excluídos do pacote de fontes, com política explícita e sem aumentar limites. Total C: **37 casos novos**. Foco corretivo: 39 passed (37 C + dois testes antigos do exportador); final completa: **1.892 passed, três skipped, zero falhas**, 100 novos e todos os 1.795 anteriores preservados. Freeze integrado em `sources_frozen_final.json`; preservação integral em `final_integrity.json`; relatório final em `RELATORIO_TECNICO.md`.
