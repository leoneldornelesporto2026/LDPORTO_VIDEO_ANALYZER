# Etapa 65: recibos futuros e cadeia de proveniencia

## Base e causa

Implementacao realizada em 12/10/2026 no workspace atual. A etapa 64 permanece
**DEFERRED_NOT_APPROVED**; o controle de fila autoriza esta etapa sem aprovar a
recuperacao historica. Nenhuma analise existente foi regravada ou autenticada.
Os ZIPs historicos nao foram usados como fontes nem como resultados de testes.

Havia um checkpoint 65 e logs de uma tentativa anterior, mas os arquivos novos
de codigo/testes/documentacao nele descritos estavam ausentes. A inspecao do
codigo presente encontrou recibos 1.0 em build_provenance e Context basico nas
duas etapas de camera. Os resultados antigos nao validam esta implementacao.

O wrapper 1.0 registrava apenas source/module hashes e retorno zero; nao
identificava stage/status/dependencias/outputs. director_integration criava
Context basico, impedindo a geracao de recibos em 18b/19. ReportEngine escrevia
analysis.json antes e depois de 21, sem recibo externo dos bytes finais.
O loader fazia hash e parse em leituras diferentes.

## Antes e depois

| Antes | Depois |
|---|---|
| Camera executada sem receipt | Context produtor nas duas etapas |
| Receipt inserido antes dos checksums | Hook finaliza receipt junto ao checkpoint atomico |
| OK presumido por retorno do callable | Status preservado; partial/skipped/failed/unavailable/blocked distintos |
| Dependencias identificadas por key/status | Snapshots de conteudo, checksum, receipt e evidencia das dependencias |
| Checksum e consumo em leituras distintas | Parsing dos mesmos bytes verificados, copias isoladas dos argumentos de camera |
| analysis.json reescrito sem checksum original externo | Snapshot do input de 21 e indice externo final depois da reconciliacao |
| Cache antigo com leitura compativel | legacy_unattested, sem backfill nem autenticacao retrospectiva |

## Contratos e ordem de escrita

O recibo produtor **2.0** contem stage_id, execution_mode, status, retorno,
source_sha256, input/config fingerprints, checkpoint key, fingerprint do
cache_manifest, dependency_fingerprints, module_hashes/module_fingerprint,
output_checksums, timestamp UTC, metodo, trust_scope e receipt_sha256.
O retorno se refere ao callable local, nao a um exit code inventado de um
processo externo. Falhas e blocked conservam retorno null quando nao comprovado.
Blocked usa not_executed; cache hit usa cached nas metricas e conserva o recibo
original executado/skipped. Hashes nao convertem partial em OK.

O core chama hooks opcionais: valida recibos antes de consumir cache; finaliza
os recibos depois dos checksums e antes do write_json atomico. Estados e eventos
de conclusao sao atualizados depois do commit. fsync e replace ja existentes
continuam sendo usados. Todos os artefatos declarados pelo produtor entram nos
checksums, inclusive formatos binarios. Recibos corrompidos rejeitam o hit.

As dependencias sao lidas em snapshots privados de bytes, comparadas com seus
estados e verificadas antes/depois do callable. Conteudo alterado sob a mesma
key/status rejeita cache e commit. Ausencia de origem fica unverified ou
legacy_unattested. A atestacao completa exige a cadeia e politicas de status;
cache parcial nao recebe atestacao completa. Para testes sinteticos completos,
o fixture agora respeita a ordem topologica real de dependencias.

18b e 19 recebem copias profundas dos argumentos, com fingerprints dos inputs
consumidos; o planner inclui semantic/understanding no seu escopo. Isso evita
alteracao dos objetos originais por consumidores. Nao restaura caches antigos.

20 continua sendo exportacao de relatorios. Depois da serializacao inicial,
o produtor conserva o input integral isolado de 21 em
execution_inputs/20_handoff/<digest>.json e grava cache/20_handoff.json com seu
recibo. 21 interpreta os mesmos bytes previamente verificados desse snapshot,
em vez de voltar ao objeto mutavel de analise. Sua chave seletiva conserva a
identidade anterior de 20; o recibo valida separadamente o conteudo completo,
podendo rejeitar um hit mesmo quando a key e igual.

Depois da reconciliacao de 21, manifest.json inclui os hashes reais de
analysis.json, run_manifest.json e collection refs finais.
**report_execution_receipt.json** e escrito por ultimo, identificando os bytes
finais do documento, manifesto, run_manifest e arquivos referenciados. Nao
inclui hash de si mesmo. run_manifest aponta para ele por export_receipt_ref,
com hash_location=external_only. O receipt do input inicial de 21 continua
distinto do receipt dos relatorios finais; nao ha ciclo de hash nem recibo
retroativo do analysis historico.

O loader verifica o indice quando presente e hidrata as colecoes a partir das
copias verificadas. Sem indice, permanece leitura de compatibilidade, sem
atestado. Recovery verifica o novo contrato, conteudo de dependencias, identidade
da fonte e bytes finais, conservando os gates de replay e DERIVED_FROM da 64.

Os envelopes run_manifest e execution_attestation permanecem 1.0 com campos
aditivos; o recibo interno e 2.0. O documento compacto permanece 4.2, o pacote
de segunda curadoria 3.1 e os schemas de camera nao foram alterados. Nenhuma
mudanca em config/config.yaml ou gates editoriais/comerciais/privacidade.

## Escopo e limites de confianca

trust_scope explicita **local_producer_consistency_not_independent_signature**.
Hashes gravados pelo mesmo processo nao sao assinatura digital nem ancora
independente. Alguem com controle de todos os arquivos pode recalcular recibos.
Hashes dos modulos representam arquivos observados em disco, nao prova do
bytecode carregado, ambiente inteiro ou qualidade semantica das inferencias.
Atestacao completa 1.0 tem escopo das etapas de analise, nao aprovacao editorial
ou publicacao. 20/21 sao vinculados por recibos proprios.

As copias isolam JSON/argumentos e o input de exportacao. Nao se copiam videos
ou audios pesados inteiros para uma area imutavel; hashing local de artefatos
e verificacao antes/depois nao excluem ataque ABA transitorio a midia durante
consumo por bibliotecas externas. Essa origem nao possui garantia independente.
Nenhum teste de fixture prova homologacao de energia fisica, GPU ou modelos.

A mudanca de core modifica seu hash: etapas cujo escopo inclui core.py podem
invalidar caches em uma futura execucao explicitamente selecionada. Nao foi
executada invalidacao/reanalise em caches reais, nem convertido um miss em hit.
Leitura de caches com chaves compativeis continua suportada sem backfill.
Snapshots integrais de input podem aumentar memoria/disco e conter evidencias
locais privadas; nao fazem parte da distribuicao automatica do pacote. A
privacidade do exportador segue fail-closed e nao foi relaxada.

## Validacao e homologacao

Testes offline exercitam produtores reais de checkpoint, camera com stubs,
reports/export em fixtures, cadeia topologica completa, cache antigo,
partial/skipped, adulteracao de manifesto/fonte/ids, swap entre verificacao e
consumo, falha de disco/replace e interrupcao simulada. Resultados concretos,
comandos e exit codes desta retomada estao no checkpoint 65 e logs resume_*.
O teste preexistente de integracao usa somente midia sintetica curta e ASR
importado/modelos desabilitados; nao e benchmark real atualizado.

O benchmark de 19s e somente referencia: execution_attestation=null e caches
de camera nao autenticados nao foram consertados retrospectivamente. Fonte
320x240/15fps, baixa cobertura e candidatos rejeitados nao demonstram falha
semantica corrigida pelos recibos. A analise antiga permanece historica.
Publication_ready e preview_approved continuam false sem revisao/evidencia.

Homologacao futura: run real novo somente quando autorizado, medicao do custo
dos snapshots, junction/symlink Windows com privilegio e falha fisica de
energia/disco. A etapa 64 exige revisao posterior da dependencia historica,
sem reinterpretar recibos desta execucao como prova do video antigo.
