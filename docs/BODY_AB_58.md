# A/B corporal local — etapa 58

`src/ldporto/body_ab.py` acrescenta um protocolo independente ao goldset visual
da etapa 50. Os contratos de produção, tracking, Re-ID, active speaker, cortes,
safe area, preview e thresholds permanecem os atuais. Nenhum comando abaixo foi
executado em mídia real nesta etapa. Executar apenas amostras autorizadas.

## Manifest e consentimento

`python scripts/dev/body_ab_stage58.py manifest --source-metadata source.json --output manifest.json`

`source.json` contém `sha256`, `duration` (segundos medidos) e `filename` da mesma
fonte. Default: 14 janelas, máximo 20; `--count` aceita 10–20.
`--windows windows.json` aceita uma lista editável de objetos `start`, `end`,
`requested_stratum`. Regenerar o manifest após editar as janelas. Cada janela
tem um frame explícito no ponto médio. A lista cobre pedidos de wide-shot,
sentado, corpo parcial, rosto oculto, duas pessoas, corte e vozes sobrepostas.
**Esses pedidos não são constatações do conteúdo.** Ajustar timestamps usando
revisão local; a distribuição inicial uniforme não garante essas cenas.
Janelas sobrepostas e IDs duplicados são rejeitados. Sem anotação humana,
`bodies=null`, nunca caixas ou identidades presumidas.

Derivação é uma ação separada e exige consentimento local explícito:

`python scripts/dev/body_ab_stage58.py derive --manifest manifest.json --video fonte.mp4 --images-dir nova_pasta --consent-local --output derived.json`

A função recalcula SHA256 da fonte antes de abrir o decoder, realiza no máximo
20 seeks/reads, grava PNGs em **diretório novo** e vincula hash, fonte, timestamp
pedido e posição reportada pelo decoder. Não interpreta posição como prova de
seek exato: homologar frame/PTS no Windows para os cortes anotados. Em erro,
PNGs parciais podem permanecer no diretório novo; não usar como goldset pronto.
Não há áudio, Whisper, diarização, Ollama, upload ou vídeo longo A/B automático.

## Baseline e candidate

`python scripts/dev/body_ab_stage58.py run --manifest derived.json --vision-config vision.json --mode baseline --consent-local --output baseline.json`

`python scripts/dev/body_ab_stage58.py run --manifest derived.json --vision-config vision.json --mode candidate --consent-local --output candidate.json`

`vision.json` é o objeto de opções `vision` da configuração atual, fornecido
localmente (não a configuração inteira). Usar exatamente o mesmo JSON nos dois
comandos; a função seleciona apenas `body_backend=hog/yolo`. YOLO usa somente peso
local e políticas/limites da etapa 57. Não provisiona dependências ou pesos.
O runtime verifica todos os hashes das imagens antes de carregar o detector,
reconfere cada PNG antes de decodificar, executa cada frame uma vez e registra
backend bem-sucedido por frame. Fallback HOG, cap ou execução omitida impedem
atestar substituição completa por YOLO, inclusive nos frames sem detecções.
As opções de cascata e face são idênticas; se pularem detecção corporal, isso
aparece na auditoria. Carregamento/disponibilidade não é execução.

O runner mede wall time e CPU process time, e mantém tempo corporal/dispositivo
efetivo reportados pelo detector. Wall time inclui faces/embedding/decodificação;
CPU process time pode somar threads. `gpu_kernel_seconds=null`: não se usa profiler
nem se inventa tempo de kernel. Tempos do carregamento do detector não estão
incluídos; o benchmark do primeiro frame continua disponível no execution.
Não interpretar mocks como benchmark de CPU ou RTX 5070.

O runner corporal preserva caixas de rosto e **não gera track IDs/person IDs**.
Re-ID/associação speaker-person exigem previsões rastreáveis de uma execução de
tracking separada sobre esses mesmos frames, anexadas por um consumidor local:
`detections[].person_id` (ou null) e `frames[].speaker_person` (speaker ID para
person ID previsto). Estes são resultados propostos, nunca identidade certificada.
Sem tais previsões, a avaliação humana contabiliza abstinências; o runner não
constrói vínculos a partir da localização corporal ou de vozes simultâneas.

## Revisão e relatório

Após conferir os PNGs, editar somente `ground_truth_consent` e `samples[].human`.
Consentimento: `allowed=true`, `reviewer`, `source_sha256` e `manifest_sha256`
iguais aos anchors do manifest derivado. Não reutilizar consentimento após
regenerar imagens/anchors. A anotação de cada frame exige `status=verified`,
`reviewer` e lista completa `bodies`: `[]` significa frame vazio confirmado,
`null` significa não medido. Cada corpo tem `bbox={x,y,width,height}` normalizado,
`instance_id` humano e opcional `identity_label` anônima confirmada. Instâncias
distintas de uma pessoa em tracklets distintos podem compartilhar identity_label;
a mesma instância persistente pode repetir instance_id em vários frames.
Não copiar identidade/detecção prevista para os campos humanos.

`human.speaker_person` opcional mapeia speaker ID para identity_label revisada.
Vários speakers podem constar no mesmo frame; isso não confirma active speaker
nem sincronia audiovisual. Labels incertos não medem Re-ID. Conflitos humanos,
IDs de instância repetidos no mesmo frame ou caixas inválidas falham explicitamente.

`python scripts/dev/body_ab_stage58.py compare --manifest reviewed.json --baseline baseline.json --candidate candidate.json --output report.json`

O comparador exige mesma fonte, anchors, parâmetros, conjunto completo de frames,
timestamps e hashes PNG. Rótulos não alteram o manifest_sha256; o goldset completo
e cada run têm hashes próprios no relatório. Não abre mídia nem roda inferência.
Recall/precision corporal usam somente frames humanos completos e consentidos,
matching bipartido máximo por IoU (default .5, protocolo de avaliação, não threshold
de produção). Detecções duplicadas contam FP; frames não anotados ficam fora dos
denominadores. O relatório informa o número de frames revisados.

Instâncias humanas permitem comparar backend-specific tracklets sem assumir IDs
iguais. Falso merge: identidades humanas distintas no mesmo cluster previsto.
Falso split: mesma pessoa humana em clusters previstos distintos. Previsão ausente
ou conflitante de uma instância é abstinência, não falso split. Binding errado ou
cluster misturado é falso vínculo; cluster desconhecido é abstinência. Sem prova,
as métricas ficam `null/NOT_MEASURED`; contagem de detecções continua descritiva.

`improvement_accepted` refere-se somente à amostra fornecida: exige execução
completa dos backends corretos, goldset corporal/Re-ID/binding, zero falsos merges
e vínculos no candidate, nenhum erro/abstinência maior e ao menos uma redução.
Não estima acurácia populacional nem certifica segurança fora dos frames anotados.
`editorial_benefit` permanece `null/NOT_MEASURED`: entrega editorial exige revisão
independente de canário/preview e evidência de benefício, fora deste comparador.
`publish_ready=false`, `preview_approved=null`; nenhum gate é promovido.
Arquivos JSON de saída são criados exclusivamente, sem sobrescrever análises.

Homologação pendente: timestamps/PTS do decoder Windows, YOLO/HOG reais em trechos
consentidos, origem/licença/hash dos pesos, GPU compartilhada, anotação humana e
tracking/Re-ID/ROI reais. Regressão independente permanece com o orquestrador.
