# Plano de organização e limpeza R6

Data: 16/10/2026. Escopo: storage.py, storage_dialog.py e regressões isoladas. Nenhuma limpeza, movimentação ou restauração foi executada sobre análises, documentos, exportações ou mídias reais do usuário.

## Causa-raiz e correção P0

O código anterior aceitava cleanup_preview(root, source, include_source=True). A função _removable podia autorizar uma fonte MP4/MKV/MOV/WEBM fora da pasta da análise. O diálogo oferecia seleção da fonte original e um checkbox para incluí-la na exclusão definitiva.

Agora o argumento legado include_source não autoriza fontes. Vídeos permanecem fora da whitelist. Uma fonte informada apenas acrescenta proteção, inclusive para áudio WAV na pasta audio. O diálogo não possui seletor nem checkbox para excluir a fonte.

Não existe exclusão definitiva no gerenciador R6. execute_cleanup confirmado movimenta apenas arquivos regeneráveis para quarentena dentro da própria análise. Isso retira arquivos da árvore ativa, preserva a possibilidade de restauração e **não libera espaço físico em disco**.

## Implementação reaproveitada e evolução

- As APIs cleanup_preview, execute_cleanup, media_lease e media_in_use continuam em storage.py. O mesmo botão da aplicação pode continuar chamando show_cleanup; não foi criada uma segunda ferramenta de limpeza.
- list_projects(base, export_verifier=None) oferece inventário somente leitura, sem persistir índices ou atualizar análises. Reconhece pastas com run_manifest.json, analysis.json, analysis.compact.json ou metadata.json.
- O inventário exibe título/ID quando registrados, estado, tamanho, arquivos regeneráveis/protegidos, quarentena, exportação externa e integridade. A última utilização é aproximada pela modificação mais recente de artefato; não prova abertura ou revisão.
- project_export.json é um ponteiro opcional para o export organizado. Existência não implica integridade. Sem callback de validação, o estado é not_verified. Com verificador, também são conferidos o hash do manifest registrado no ponteiro e o SHA-256 da fonte, quando disponíveis.
- O diálogo usa worker e fila para inventário, hashes, quarentena e restauração. O modo inicial é leitura. Movimentação e restauração exigem confirmações separadas.
- A ação de exportar antes da limpeza aceita callback da GUI. Sem callback, permanece desabilitada; não existe exportação implícita.

## Caminhos, posse e dados protegidos

A validação ocorre antes de resolver caminhos: bloqueia travessia por dois pontos, referências absolutas em recibos e qualquer symlink/junction/reparse point na folha ou nos antecessores. A raiz do aplicativo, raiz de volume, home e árvores de modelos, Git, revisões, aprovações, renders ou quarentena não são aceitas como alvo de limpeza.

O percurso não segue links/reparse points. Arquivos fora da análise nunca entram na rotina. Fontes fornecidas, transcrições, JSONs, SRT, pacotes ZIP, relatórios, planos editoriais, manifests, aprovações e renders finais não são elegíveis.

A whitelist herdada é restrita a:

| Local relativo à análise | Tipos potencialmente regeneráveis |
| --- | --- |
| audio/ | .wav, preservando uma fonte explicitamente informada |
| temporary_frames/, render_staging/ | .png, .wav, .tmp |
| .cache/ | .npz, .npy, .pkl |

Subárvores de revisões, aprovações e renders finais continuam protegidas mesmo dentro dessas pastas. Não se presume que qualquer arquivo em cache/, qualquer vídeo pesado ou qualquer documento antigo seja descartável.

RUNNING.lock ativo ou de posse desconhecida bloqueia movimentação. PID inválido/não positivo e erros que não comprovem a morte do processo são conservadoramente tratados como uso. Leases ativos ou ilegíveis também bloqueiam o arquivo.

O preview registra tamanho, mtime e SHA-256. A execução revalida conteúdo, caminhos, whitelist, locks e leases. Alterar o conteúdo mantendo tamanho e mtime não autoriza o movimento.

## Quarentena, recuperação e cancelamento

Estrutura: análise/.ldporto_quarantine/UUID/manifest.json e files/caminho-relativo-original.

O diretório da operação é reservado exclusivamente; colisões não sobrescrevem recibos anteriores. Antes de cada movimento é persistido um recibo pending. Após o movimento, o item passa a quarantined. Se falhar a gravação posterior, o recibo pendente permite localizar e restaurar o arquivo pelo hash.

O movimento é local ao mesmo filesystem. Não existe fallback de cópia entre volumes, nem remoção ampla. No Windows, o rename falha quando o destino existe. Em outros sistemas, a transferência utiliza hard link exclusivo seguido de unlink da origem regenerável, preservando o destino quando uma etapa falha.

restore_preview é somente leitura. restore_quarantine(..., confirmed=True) revalida root/UUID/recibo, caminhos relativos, hash, whitelist e uso. Um destino já existente nunca é sobrescrito. Arquivos alterados permanecem na quarentena, com motivo explícito.

O cancelamento é cooperativo: ocorre antes e entre unidades de movimento; uma unidade iniciada é finalizada e registrada. Fechar o diálogo durante um worker solicita cancelamento e aguarda sua conclusão segura.

Compatibilidade de métricas:

- removed_bytes continua existindo, mas significa bytes retirados da árvore ativa.
- quarantined_bytes explicita os bytes preservados na quarentena.
- reclaimed_bytes é 0; a interface apresenta essa informação.
- reclaimable_bytes legado no preview representa a whitelist elegível, sem promessa de espaço liberado.

Não foram implementadas exclusão definitiva de quarentena, remoção de projeto inteiro ou migração de mídias reais. Essas ações não são necessárias para consultar/exportar uma análise e permanecem fora da rotina.

## Classificar antes de organizar documentos

O inventário de referência é BASELINE_R6.json, produzido antes das alterações. Ele registrou docs/ com 856 arquivos e 110.023.138 bytes no escopo documentado no próprio baseline. Isso não representa espaço autorizado para limpeza.

| Classe | Referências e tratamento |
| --- | --- |
| Essencial | Fontes ativos, schemas, contratos, documentação atual e relatórios desta entrega: preservar. |
| Histórico útil | docs/archive/, auditorias anteriores de docs/reports/ e ZIPs em src/tests/fixtures/historical_evidence/: preservar como evidência histórica; nunca extrair sobre fontes. |
| Regenerável potencial | .pyc, __pycache__, caches de teste e intermediários: classificar por escopo; não foram removidos nem incluídos automaticamente na whitelist de análises. |
| Exportado | Exige ponteiro, manifest e integridade verificados. Um ZIP existente ou um nome READY isolado não autoriza remoção da origem. |
| Obsoleto confirmado | Nenhum artefato real foi declarado obsoleto nesta etapa. |
| Uso desconhecido | Snapshots, ZIPs antigos na raiz, logs e duplicações sem cadeia de referência: preservar até revisão. |

Não houve reorganização automática de docs/, scripts, módulos Python, ZIPs históricos ou mídias locais. Migrar material audiovisual para Vídeos requer escopo autorizado, hashes conferidos e referências atualizadas; o export organizado é tratado separadamente.

## Verificação efetivamente executada

Comando inicial:

    .\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider src\tests\test_r6_storage_safety.py src\tests\test_v44_ops.py --junitxml=docs\reports\r6_20261016\storage_focused.junit.xml

Resultado real: **31 passed, 1 skipped**, 32 coletados, 1,06 s. Artefatos: storage_focused.log e storage_focused.junit.xml.

Após cobrir novas bordas:

    .\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider src\tests\test_r6_storage_safety.py src\tests\test_v44_ops.py --junitxml=docs\reports\r6_20261016\storage_focused_final.junit.xml

Resultado real: **37 passed, 1 skipped**, 38 coletados, 1,22 s. Artefatos: storage_focused_final.log e storage_focused_final.junit.xml.

Os testes criam somente arquivos sintéticos em tmp_path. Cobrem fonte dentro/fora do projeto e WAV informado, leitura sem mutação, confirmação exata, round-trip por hash, tamanho/mtime adulterados, locks ativos/desconhecidos, leases, reparse simulado, candidatos externos forjados, revisões protegidas, cancelamento, falha de disco/movimento/recibo, colisões, recibo pendente recuperável e ponteiro externo com hash divergente.

O teste com symlink real foi **skipped**, porque o Windows retornou WinError 1314 (privilégio de symlink indisponível). O teste de antecessor reparse simulado passou; isso não substitui homologação de junction/symlink real.

Também foram executados git diff --check -- src/ldporto/storage.py src/ldporto/storage_dialog.py (exit 0; apenas aviso de normalização futura LF/CRLF) e compilação sintática em memória de ambos os módulos, sem gerar bytecode (exit 0).

## Homologação remanescente no Windows

- Abrir o diálogo nativo e conferir tabela, seleção, progresso de leitura, fechamento/cancelamento e mensagens de quarentena/restauração em escala de interface real.
- Validar junction/symlink reais em cópias isoladas com privilégio adequado; não testar sobre projetos/mídias originais.
- Validar falhas reais de permissões, disco, interrupção de processo e antivírus em cópias descartáveis. Os cenários automatizados de falha foram simulados.
- Integrar o callback de exportação da central de resultados e executar o verificador real do export organizado. Os testes deste módulo não afirmam homologação integral do export nem do Curator.
- Uma verificação de posse por PID/lease e revalidações de caminho não fornecem exclusão mútua contra alterações hostis concorrentes do filesystem. Não foi criado executor, fila de desenvolvimento, estado ou lock adicional.

Não foram usados GPU/Ollama, modelos, download, serviços pagos, pipeline completo, publicação, commit ou push.

## Revisão independente e verificação final do escopo

Após a primeira entrega, a revisão independente identificou que erros de gravação do recibo depois de um movimento concluído faziam o mesmo arquivo constar simultaneamente como movido/restaurado e ignorado. A contagem foi corrigida: o movimento real é preservado no resultado e a falha de recibo aparece separadamente em errors. Um teste adicional confirma que a restauração efetivamente concluída não é apresentada como ignorada.

O diálogo também aceita application_busy opcional. A aplicação pode manter leitura/inventário disponíveis e bloquear exportação, quarentena e restauração enquanto outro trabalho estiver ativo. Se a aplicação iniciar trabalho durante uma operação do gerenciador, o callback participa do cancelamento cooperativo. Nenhum lock novo foi introduzido.

Na revisão do export organizado foram acrescentadas 19 regressões independentes em test_r6_project_integrity_safety.py. Elas verificam consumo do mesmo snapshot ZIP validado, vínculos pacote/fonte/run, schema/estado, arquivos obrigatórios, reparse da folha do manifest e compatibilidade da análise opcional.

Uma lacuna de completude foi reproduzida antes da correção: a ausência de cada um dos três PDFs obrigatórios, após reindexação dos arquivos de uma fixture, ainda recebia valid. O comando com filtro required_pdf produziu **3 failed, 12 deselected**, em 5,36 s; evidências em project_required_pdf_review.log e .junit.xml. A correção do verificador foi realizada no escopo principal, e esses três casos passaram na verificação final abaixo.

Os nomes project_integrity_review_before.log e .junit.xml não indicam teste do código anterior: a primeira execução dos 12 casos já consumiu as correções presentes e registrou 12 passed em 19,53 s. A verificação de quatro incompatibilidades da análise também já consumiu os ajustes presentes e registrou 4 passed, 15 deselected em 4,03 s, em project_analysis_binding_review.log e .junit.xml.

Comando final deste escopo:

    .\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider src\tests\test_r6_storage_safety.py src\tests\test_v44_ops.py src\tests\test_r6_project_integrity_safety.py --junitxml=docs\reports\r6_20261016\storage_export_review_final.junit.xml

Resultado real: **57 passed, 1 skipped**, 58 coletados, 29,68 s. Artefatos: storage_export_review_final.log e storage_export_review_final.junit.xml. O skip continua sendo o symlink real sem privilégio no Windows; o reparse simulado passou.

Essa execução não equivale à homologação visual da GUI nem à importação no Curator. Todos os movimentos, falhas e remoções das regressões ocorreram exclusivamente sobre arquivos sintéticos de tmp_path.
