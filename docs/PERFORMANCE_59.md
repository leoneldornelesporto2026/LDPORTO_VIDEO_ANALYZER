# Orçamento visual — etapa 59

CUDA para YOLO continua opt-in (`vision.yolo_device: cuda`). O orçamento agora
exige VRAM livre >= `yolo_min_free_vram_mb` (2048 MiB) +
`yolo_reserve_vram_mb` (1024 MiB). A primeira parcela é margem configurada para
o backend, não uma previsão de alocação medida do modelo. Consulta device 0
com timestamp UTC antes da carga e de cada chamada CUDA. Não reserva memória;
Ollama, Whisper, pyannote e outros processos podem alterar a disponibilidade
logo após a consulta. Contagem e mínimo/máximo dos snapshots tornam essa
variabilidade visível. Pico do allocator PyTorch, quando disponível, tem escopo
do processo desde sua criação; não representa pico global nem todo o YOLO.

`yolo_resource_policy: cpu_fallback` preserva o fallback CPU HOG existente.
`blocked` é opt-in e interrompe diante de falha de orçamento ou inferência,
sem produzir deteções corporais substitutas. Erros de assets continuam usando
o contrato de disponibilidade local da etapa 57. Nenhuma política aprova
identidades, qualidade ou publicação. Reserva inválida ou VRAM desconhecida
falha fechada. Não altera scores, sampling, ROI, thresholds ou parâmetros HOG.

Whisper → pyannote → visão → Ollama continuam sequenciais no pipeline atual.
FaceLandmarker permanece no delegate CPU padrão. Não há executor GPU novo.
A política não descarrega modelos de processos externos nem promete exclusão
global de GPU. Orçamentos/peaks reais de áudio e semântica continuam a homologar;
o preflight os identifica como requires_local_measurement, sem valores fictícios.
As métricas de etapa/cache/CPU de Context permanecem intactas.

Visão mantém um frame em voo. HOG paralelo continua desligado por padrão;
opt-in admite apenas um worker conforme RAM/carga CPU já verificadas. OpenCV
usa `vision.opencv_threads: 1` (configurável entre 1 e 4) no loop e restaura a
configuração após aguardar cleanup do worker. Não usa multiprocessing/spawn.
Cancelamento é consultado no loop; filas pendentes são canceladas no shutdown.
Chamadas nativas ativas não são preemptíveis: deadlines corporais são soft.
Checkpoints concluídos permanecem disponíveis; o contrato de hashes rejeita
dependências alteradas, sem apagar o cache. performance.py passa a integrar o
hash dos chunks visuais, como já integrava o cache de people_tracking.

Telemetria distingue frames attempted/succeeded nesta execução de frames
recarregados de checkpoints. FPS inclui o loop atual; latências p50/p95 cobrem
os últimos 512 frames bem sucedidos, de retrieve até checkpoint. A UI só
formata eventos recebidos do subprocesso: não consulta GPU nem faz inferência
no main thread. Exibe counts, fps, p95, backend/device comprovados, VRAM livre
de snapshot e motivo de fallback. ETA permanece sob o estimador existente:
calculando antes de três amostras; estimativas futuras de baseline são rotuladas.
Sem embedding disponível não há prova visual de identidade; embedding disponível
também não confirma identidade. Percentual reportado tem esse escopo explícito.

Smoke reproduzível (inputs fixos, tempos variáveis reais, nenhum ganho inferido):

```powershell
python scripts/dev/benchmark_resources59.py --output novo_smoke59.json
```

Default: três frames sintéticos 64×128, HOG CPU real, um thread, nenhum peso
local/neural. Não é um goldset humano ou estimativa da RTX 5070. Máximo oito
frames. Saída exclusiva, sem sobrescrita. Clip opcional, apenas por ação local:

```powershell
python scripts/dev/benchmark_resources59.py --clip clipe_local.mp4 --sha256 HASH_SHA256_REAL --consent-local --frames 3 --output novo_clipe59.json
```

Exige duração 10–30s, hash válido antes/depois do decode e frames <=8 MiB.
Não redimensiona para fingir A/B equivalente. O benchmark usa CPU HOG, não
executa Whisper/pyannote/Ollama/YOLO. GPU sem memória e fallback são testes
determinísticos com mocks, sem alegar performance GPU. Para comparar qualidade
YOLO/HOG use o protocolo da etapa 58 e revisão humana; nenhum knob foi ajustado
nesta etapa. Speedup, qualidade e métricas reais do vídeo continuam null.

Homologar no Windows com fonte curta autorizada: cancelamento durante chamada
nativa, responsividade Tk em hardware real, picos por processo/sistema, variação
com Ollama residente e custo das margens na RTX 5070. Não disparar pipeline longo.

Na retomada da etapa 59, o snapshot CUDA explícito do preflight também ocorre
quando faltam assets visuais: o relatório distingue orçamento de disponibilidade
de modelos, sem carregar YOLO para essa consulta. FPS final usa somente sucessos
da execução atual, excluindo frames retomados. A API de clipe limita 1–8 frames
antes de acessar a fonte e rejeita FPS/contagem não finitos e frames menores que
a janela HOG, liberando o decoder. Falhas de abertura/seek liberam também os
recursos do detector e landmarker já inicializados.
