# Detector corporal local opcional (etapa 57)

O preflight fornecido antes desta etapa era HOG / CPU / degraded, com
`yolo_local_model_missing`; não foi reexecutado em vídeo real. Sem pesos locais
e inferência bem-sucedida, YOLO permanece `NOT_READY`. Carregar um modelo no
preflight não comprova execução, qualidade, identidade ou falante ativo.

## Arquivo e instalação manual

O app não instala dependências nem baixa pesos. `requirements/yolo.txt` é
opcional. Se o usuário optar por instalar, use o Python do ambiente do projeto
e um wheelhouse já provisionado, compatível com Windows/Python 3.11/PyTorch:

```powershell
python -m pip install --no-index --find-links "C:\wheelhouse" -r requirements/yolo.txt
python -m pip show ultralytics torch
Test-Path -LiteralPath "C:\pesos-confiaveis\yolo11n.pt" -PathType Leaf
Get-FileHash -LiteralPath "C:\pesos-confiaveis\yolo11n.pt" -Algorithm SHA256
```

Estes comandos são instruções, não foram executados nesta etapa. Não substitua
PyTorch do projeto sem conferir compatibilidade com Whisper/CUDA. A versão
instalada precisa reconhecer o checkpoint; arquivo inválido/incompatível gera
`model_load_error`. Aceitamos apenas `.pt` local não vazio, sem symlinks/reparse
points no caminho. Nunca passamos nome remoto/URL/nome de arquivo ausente ao
Ultralytics. Checkpoints PyTorch podem conter código: selecione somente arquivos
de origem confiável, com hash conferido. Validação de caminho não é sandbox de
desserialização. O hash real selecionado aparece no relatório de backend.
Desabilitamos `YOLO_AUTOINSTALL` no processo e `AUTOINSTALL` de checks já
importados: dependência ausente não pode disparar instalação automática.

Modelo precisa ter tarefa `detect` e classe 0 `person`, como YOLO11 detect COCO;
modelos customizados com outra taxonomia são rejeitados. Outras classes e caixas
inválidas são descartadas. Não há recomendação de ganho de qualidade mensurado.
As fixtures substituem completamente Ultralytics e CUDA; não provam compatibilidade
de um checkpoint real com o runtime instalado.

Antes de produção, revisar licenças do código e dos pesos. A documentação oficial
descreve opções AGPL-3.0 e Enterprise para YOLO11:
[licença Ultralytics](https://www.ultralytics.com/license) e
[YOLO11](https://docs.ultralytics.com/models/yolo11). Uso comercial/proprietário
precisa de avaliação das obrigações aplicáveis; esta etapa não concede licença.

## Escolhas preservadas e device

GUI: **Detector corporal local** abre escolhas atuais; salvar é ação explícita,
cancelar não altera configuração. Backend `auto`, `hog`, `yolo`; seleção manual
do `.pt`; device `cpu` padrão conservador ou `cuda` opt-in. Nada é instalado.
O status inicial é `NOT_READY`; o log real `body_backend_execution` atualiza a
GUI depois da execução. Diagnóstico geral exibe o preflight; `ok` com HOG permite
continuidade degradada e não significa que YOLO está pronto.

Configuração aditiva (exemplo a aplicar manualmente, sem alterar defaults atuais):

```yaml
vision:
  body_backend: auto
  yolo_model: models/yolo11n.pt
  yolo_device: cpu
  yolo_min_free_vram_mb: 2048
  yolo_confidence: 0.5
  body_max_frames: 100000
  body_frame_timeout_seconds: 30
  body_total_timeout_seconds: 3600
```

Em CUDA usamos GPU 0 somente após `torch.cuda.mem_get_info(0)` atingir o mínimo.
Rechecamos imediatamente antes de cada frame. VRAM compartilhada com Whisper/
Ollama não está reservada: existe corrida entre verificação e inferência.
Sem CUDA/VRAM/diagnóstico disponível, usamos HOG/CPU explicitamente. Falha de
inferência, OOM, device divergente ou timeout descarta resultado YOLO e ativa
HOG; não há retry GPU nem queda escondida de YOLO CUDA para YOLO CPU. Nunca
descarregamos Ollama, nem forçamos a RTX 5070 por capacidade nominal.

O primeiro frame efetivamente solicitado mede `benchmark_frame_seconds`;
inclui inicialização da primeira predição, não adiciona frames nem roda no
preflight. CUDA real deve informar `predictor.device`; divergência é falha.
`device` indica backend selecionado atual, `device_actually_used` registra a
última tentativa YOLO, `devices_used` discrimina backends com sucesso.

Limites são por processo: cap de chamadas corporais (não limita rostos), orçamento
de tempo corporal cumulativo e deadline **cooperativo** por frame. O tempo só é
checado após a chamada nativa retornar; não há garantia de interromper OpenCV/
PyTorch travado. HOG que excede deadline descarta caixas e para chamadas
corporais seguintes. Homologar watchdog externo no Windows se exigido timeout
de parede estrito. Em retomada, orçamento começa no novo processo; contagens
nunca representam chamadas antigas em cache. Para smoke autorizado use cap 1–3
em frame sintético; não rodar vídeo longo como benchmark.

## Evidência e cache

Motivos aditivos: `model_file_missing`, `model_file_invalid`, `dependency_missing`,
`model_load_error`, `insufficient_vram`, `cuda_unavailable`, `cuda_preflight_failed`,
`inference_error`, `inference_timeout`. Os `fallback_reason` legados permanecem.
`executed_backends`/`inference_calls` legados incluem tentativas;
`actually_executed_backend`/`successful_backends` distinguem sucesso. Um backend
com inferência vazia bem-sucedida executou, mas não provou pessoa presente.
`EXECUTED_NOT_VALIDATED` exige YOLO executado e ainda ativo; fallback é
`NOT_READY` / degraded. Qualidade de detecção real, recall sentado e validação
NVIDIA permanecem null/not_validated.

Caixas são normalizadas/clampadas [0,1]. Confiança YOLO é score do detector
filtrado por threshold, não probabilidade calibrada em goldset deste projeto;
HOG conserva `hog_score` bruto e confiança null. Corpos sem rosto não recebem
embedding/identidade comprovada; não promovem active speaker ou gates editoriais.

Hash de pesos integra dependência externa de `07_people_tracking` e checkpoints
visuais, invalidando visão/consumidores quando mudar, preservando audio/ASR.
Nenhum cache/artefato existente foi reescrito nesta etapa.

Homologação pendente: arquivo confiável real e runtime Ultralytics selecionado,
frame autorizado CPU e CUDA/VRAM concorrente, interface Tk no Windows, limite de
parede em biblioteca nativa. Testes offline são prova de contrato, não produção.
Curadoria READY não é publish_ready; nada nesta opção aprova publicação.
