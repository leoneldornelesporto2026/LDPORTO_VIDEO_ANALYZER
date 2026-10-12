# Recuperação da segunda curadoria — etapa 64

O replay recupera exclusivamente `21_second_curation_handoff`. Não executa
`pipeline.py`, não usa mídia e não inicializa ASR, diarização, visão ou Ollama.
Por padrão só valida dependências, registra hashes e informa o que seria
invalidado. Estados parciais são conservados; validar o pacote nunca autoriza
publicação, seleção de cortes ou Stories.

```powershell
.venv/Scripts/python.exe scripts/dev/recover_second_curation64.py --analysis analysis/video_31329be78ca4 --cache analysis/video_31329be78ca4/cache/302b92446d433fcf --report automacao/execucao/etapa64/plano_revisao.json
```

Exit 0 significa que o plano possui dependências verificadas; exit 2 significa
bloqueio. O comando não chama o exportador. `would_invalidate` contém somente
a etapa 21; não remove nem grava cache upstream. Cada etapa informa hit/miss,
motivo e origem da validação. O checksum de dados, contrato, recibo do estágio,
digest das dependências e checksums dos artefatos do cache são verificados.
Referências de coleção são verificadas por SHA-256 antes de serem hidratadas.

A etapa 20 é `uncached_export`, comprovada pelo snapshot aprovado
`LDPORTO_STAGE_63.zip`, SHA-256
`8b814c4501eb1441f3025ca635ddd8163de25bbdbab99974a6e4e3d90581d23b`.
O fingerprint dos módulos desse snapshot corresponde exatamente ao produtor
histórico: `f13cb5d27e9b280592247f2d5bd9fc5c10e8debebb359430da6be3f9bf52902f`.
O snapshot é lido em memória, sem extração sobre fontes. O planner fixa e
confere ambas as âncoras, origin, build e fingerprint; não confia apenas no
texto do manifesto. A confiança pressupõe a custódia do snapshot aprovado
pelo orquestrador; não se afirma assinatura de terceiro.

Nesse produtor, reports.py:696–705 assina collection_refs e replay_files,
incluindo second_curation_package.json e CHATGPT_ANALYSIS_HANDOFF.compact.json.
O completo é complementar, fora dessa lista; seu hash atual não é recibo
original. reports.py:566 passa analysis e o pacote diretamente ao exportador.
Nenhum consumidor dessa rota lê o handoff completo, portanto sua falta de hash
não bloqueia mais a etapa 20. Todos os hashes contratualmente assinados e as
referências de coleção continuam obrigatórios.
O pacote histórico é schema 3.1 (second_curation.py:239 no snapshot aprovado),
e o handoff compactado é schema 4.2. O planner valida essas versões efetivas.

O replay real ainda está BLOCKED: load_analysis_artifacts consome analysis.json,
inclusive campos inline metadata, quality_gate, social_output, subtitle_review_s7
e broadcast_graphics. O recibo não autentica esse documento; comparar coleções
não autentica esses campos. Motivo: consumed_analysis_document_without_original_checksum.
Dois caches (18b_global_camera_planner e 19_camera_director) não têm
execution_receipt verificável. Hashes de dados não provam execução/código.
Os recibos locais são consistência interna, não âncoras independentes contra
adulteração conjunta. Nenhum checksum retrospectivo foi criado no original.

cached_stage verifica input/params/output_version, dados, recibo de execução,
fingerprint dos módulos, presença e digest de dependências e hashes de artefatos.
Preserva versões históricas, sem exigir o código atual de inferência. O digest
versions deve existir; o ambiente histórico completo não é recuperável desses
digests e não se declara validado integralmente.

Somente após revisão explícita do plano e das dependências, um usuário pode
selecionar reparo com `--apply --snapshot <plano.json> --output <diretorio-novo>`.
Os hashes atuais devem coincidir exatamente com `reference_hashes` do plano.
Saída existente ou dentro da análise original é rejeitada. A exportação fica
em `SECOND_CURATION_DERIVED/`, sem ZIP, previews ou processamento de mídia;
o diretório deve passar pelo validador integral. Não há gravação de relatórios
ou caches originais. Uma segunda leitura de hashes confirma sua preservação.
Não executar esse comando no caso atual. Recuperação futura exige recibos
originais confiáveis dos campos inline e caches ausentes, ou reconstrução
controlada desses campos a partir de entradas independentemente verificadas,
com nova proveniência DERIVED_FROM. Não inserir hashes atuais como recibos
históricos. O prompt desta etapa não autoriza apply real.

## Contrato de privacidade e compatibilidade

O sanitizador e o validador percorrem valores JSON decodificados, inclusive
listas, chaves, JSONL, metadados e manifesto principal. Escapes da serialização
não são evidência de caminho privado: uma barra OCR isolada não é UNC. Caminhos
Windows/UNC reais, segredos reconhecidos, campos sensíveis, e-mails, telefones
formatados, CPF formatado e URLs com credenciais são removidos ou substituídos
na versão exportada. Marcas, percentuais, preços e timestamps públicos não
disparam esses padrões. Contatos encontrados em anúncios são conservadoramente
redigidos; o reconhecimento sintático não prova titularidade ou privacidade.

`summary/privacy_redactions.json` registra estado `redacted`, campo, regra e
hash, sem guardar valores. O original local permanece intacto. A sanitização é
idempotente e mantém null e tipos escalares editoriais. Links públicos sem
credenciais são conservados. Não é uma garantia de identificação semântica
universal de PII: contatos sem formatação e conteúdo privado sem padrão
reconhecível continuam sujeitos à revisão humana.

Checksums são calculados dos bytes UTF-8 efetivamente exportados. A serialização
é determinística para a mesma ordem e os mesmos valores de entrada; timestamps
do novo export continuam sendo metadados do momento de execução. São rejeitados
traversal, links simbólicos e reparse points Windows. Falhas de schema, disco,
privacidade e checksum bloqueiam a validação. Os contratos existentes da GUI e
dos relatórios continuam; `directory_only` é uma opção aditiva ao exportador.
O fingerprint da etapa 21 inclui o novo módulo de privacidade. Não mudam os
fingerprints das etapas pesadas nem a configuração local.

Evidências e limitações da execução estão em
`automacao/execucao/checkpoints/CHECKPOINT_ETAPA_64.md` e
`automacao/execucao/etapa64/`. A etapa não está aprovada para publicação.

## Retomada: consumo verificado e confirmação atômica

Cada JSON de análise/cache/recibo é decodificado dos mesmos bytes comparados
com o inventário inicial. Um segundo inventário impede confirmar alterações
durante a validação. Apply verifica as cópias temporárias e passa o pacote
existente explicitamente ao exportador, sem recalcular candidatos por omissão
do argumento package. Confirma upstream antes de renomear atomicamente a saída
para destino novo. Falha não confirma pacote final. DERIVED_FROM.json registra
inputs e hashes derivados, sempre com publication_ready=false. Timestamps de
exportação são novos; não se promete igualdade de bytes em execuções em horas
diferentes. Reaplicar no mesmo destino é recusado, preservando o primeiro.

## Gates editoriais observados

155 candidatos sem medição comercial são distintos de 11 anúncios confirmados,
15 medidos sem evidência de anúncio e 12 que exigem revisão. 165 dependências
visuais indisponíveis não contradizem 48 frames OCR comercial processados:
medição global não assegura evidência propagada em cada candidato. Há 126
blockers de unidade Q&A incompleta e payoff não resolvido, 99 perguntas sem
resposta completa, 63 fronteiras de tópico e 55 frases/handoffs incompletos.
As contagens se sobrepõem. 23 durações abaixo do mínimo sem unidade completa
comprovada e 2 acima do orçamento também bloqueiam. 204 arcos brutos não
equivalem a unidades publicáveis: métricas têm zero arcos completos, 13 parciais,
zero Q&A completo e zero Stories selecionados. Scores ausentes conservam null.

selection_report confirma 193 avaliados e 193 rejeitados: todos com
ineligible_by_quality_gate, 175 com below_editorial_quality_floor (mínimo 0.5),
11 com commercial_selection_gate. Não se atribui toda rejeição aos scores
ausentes: há 17 clarezas e 91 hooks medidos, frente a 176/102 ausentes.
Mapeamento falante/pessoa observado: 0.07045024476304296 (~7,05%). Agregados
seguros, sem exemplos privados, estão em resume_editorial_selection.json.

Prioridades futuras, sem execução nesta etapa: provar os inputs inline,
recuperar recibos de câmera, investigar propagação comercial, medir clareza/hooks,
completar unidades narrativas e homologar associação falante/pessoa. Nenhum
critério editorial foi alterado nesta etapa.

## Complemento — recuperação derivada para revisão (2026-10-10)

O projeto agora dispõe de **dois caminhos separados**, sem degradar o contrato
histórico:

- `scripts/dev/recover_second_curation64.py`: **estrito**. Continua bloqueado
  enquanto `analysis.json` não tiver prova histórica de origem e as etapas
  18b/19 não tiverem recibos de execução. Não transformar `miss` em `hit` por
  semelhança de conteúdo.
- `scripts/dev/legacy_review64.py`: **somente evidências para revisão**.
  Reconstrói campos conhecidos a partir de `analysis_summary.json` e verifica,
  de maneira independente entre arquivos do mesmo diretório, os SHA-256 de
  44 coleções e artefatos de câmera contra `manifest.json`. Preserva os
  campos ausentes como não comprovados. O resultado **não** autentica o passado,
  **não** executa `21_second_curation_handoff` nem habilita publicação.

### Diagnóstico somente leitura (primeiro comando)

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/dev/legacy_review64.py `
  --analysis analysis/video_31329be78ca4 `
  --report automacao/execucao/etapa64/legacy_review_plan.json
```

Verificar `review_input_possible`, `inline_fields`, `run_manifest_stage_status`,
`blockers` e `historical_authentication` no plano. A disponibilidade de uma
entrada de **revisão** não significa que o replay estrito ficou elegível.
Se o código produtor não tiver assinado os campos, a classificação continuará
`not_established` mesmo com hashes que conferem localmente.

### Criação isolada da entrada de revisão (apenas por decisão explícita)

Se o plano tiver sido revisado e os arquivos de saída não existirem:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/dev/legacy_review64.py `
  --analysis analysis/video_31329be78ca4 `
  --apply-review `
  --reviewed-plan automacao/execucao/etapa64/legacy_review_plan.json `
  --output automacao/execucao/etapa64/entrada_revisao_derivada
```

A cópia vai para um diretório NOVO, fora da análise. Faz sanitização conservadora
de dados sensíveis, reescreve os checksums da versão **derivada**, gera
`DERIVED_FROM.json` com as proveniências e mantém `publication_ready=false`.
A assinatura histórica **não** é recriada. Não inicializa GPU, Whisper,
Pyannote, ffmpeg, Ollama, OCR ou downloads. O comando não altera a análise.
Revisão humana ainda é obrigatória; a privacidade semântica de dados sem padrão
não pode ser garantida apenas pelo detector de PII.

**Limitações:** os campos de `analysis_summary.json` só cobrem parte do
`analysis.json`. Saídas de `18b_global_camera_planner` e `19_camera_director`
sem `execution_receipt` continuam com status **não atestado**. A entrada derivada
é destinada à investigação/curadoria assistida e não substitui o pacote de
segunda curadoria validado. Não promover o estado do orquestrador para `DONE`
sem satisfazer o critério estrito do prompt ETAPA_64.

Os testes de `src/tests/test_stage64_legacy_review.py` cobrem divergência de
hash, referência insegura, conflito de plano, mudanças concorrentes, sanitização
realista e reconstrução legível por `load_analysis_artifacts()`. Os testes do
contrato histórico passam a usar snapshot **sintético isolado** quando o ZIP
exportado não contém os snapshots reais, mantendo as constantes fixas de
produção inalteradas.
