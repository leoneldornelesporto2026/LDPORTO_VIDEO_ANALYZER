# Canário inferencial local (etapa 60)

`--doctor` continua verificando disponibilidade/carga, sem executar estes
canários. `Model load verified` e `Actual inference executed` são provas
diferentes. A interface possui botão explícito para canário e opção separada
para executá-lo antes de ANALISAR; falha bloqueia a análise. A consulta anterior
não aprova automaticamente uma nova execução longa.

Comandos para homologação local **somente após autorização explícita**:

```powershell
python analyze.py --inference-smoke --offline --device cuda --smoke-test-seconds 30 --smoke-total-seconds 120 --smoke-output diagnostics/canary60_local.json
python analyze.py --smoke-replay diagnostics/canary60_local.json
```

O primeiro comando executa os modelos habilitados pela configuração atual.
Para escolher outra configuração, acrescente `--config caminho.yaml`.
Para bloquear uma análise longa por canários atuais, use `--inference-smoke`
junto ao source, por exemplo `python analyze.py AMOSTRA_LOCAL.mp4 --offline
--inference-smoke --output analysis/NOVA_EXECUCAO`. Esse comando também inicia
o pipeline se passar; não foi executado nesta etapa. Sem source, o canário usa
somente fixtures temporárias. A saída explícita deve ser um arquivo novo;
sem `--smoke-output`, grava recibo com timestamp em `diagnostics/`.

Estados: `available` indica rota configurada sem inferência (importação de
transcrição/turnos ou heurística); `executed_pass` exige conclusão da chamada;
`executed_fail` inclui ausência de pré-condições e timeout; `skipped_user_disabled`
não reprova a base; `untested` conserva ausência de prova. Uma capacidade
habilitada e solicitada não concluída bloqueia `long_execution_allowed`.

Whisper consome efetivamente o gerador com VAD desligado em WAV de silêncio
de dois segundos. Pyannote recebe tensor da mesma duração. Isso não mede texto,
atribuição, número correto de falantes nem identidade. Pyannote exige cache
completo: aceite manualmente Community-1 e prepare todos os pesos dependentes
em procedimento separado; depois refaça o canário. Nenhum token entra no worker.
Cache incompleto falha sem pedir token ou baixar assets.
Whisper consulta apenas snapshots já existentes, sem copiar pesos para
`models/whisper`; uma instalação nesse diretório pode ser indicada explicitamente
com `--model models/whisper`. Exige model.bin/config.json/tokenizer.json locais,
evitando a busca alternativa de tokenizer feita pela biblioteca quando ausente.

Visão usa frame geométrico sintético e crop 112x112 para executar YuNet/SFace;
MediaPipe executa se active_speaker estiver habilitado. Sem rosto detectado
a chamada pode passar, mas acurácia/identidade permanecem desconhecidas. O
detector corporal habilitado também recebe um frame; fallback não é aprovado
silenciosamente: escolha HOG explicitamente se não houver YOLO local funcional.
O OCR reutiliza a imagem controlada e os limites da etapa 53, se habilitado.
Fontes sem acentos geram aviso; texto divergente ou fixture impossível falha.
Ollama recebe um único prompt com JSON `{ "ok": true }`, 512 tokens de contexto,
32 tokens de saída, sem thinking, timeout interno de 15s e keep_alive=0.
Não há loop de qwen3:14b nem alegação de qualidade editorial.

Cada capacidade roda em subprocesso sequencial. Prazo inclui imports/carga,
inferência, medição e hashes; limite por teste e total configuráveis entre
0 e 300s (exclusivo em zero). No Windows, Job Object elimina descendentes
(inclusive OCR) ao fechar; POSIX usa grupo de processos. Recursos nativos são
liberados por término do processo. Falha de Job Object fecha o processo sem
executar inferência. O tempo de encerramento/serialização tem pequena sobrecarga
fora do orçamento; não há promessa de deadline de tempo real do sistema.

Snapshots NVIDIA antes/depois não são pico de VRAM nem reserva. Ollama roda em
servidor externo: timeout do worker não garante cancelamento da requisição no
servidor; confira e interrompa manualmente antes de repetir. Device Ollama pode
ficar null após unload, e o aviso conserva essa lacuna. Hashes locais/Ollama
são registrados quando obtidos; hashes/picos desconhecidos permanecem null.
Hashes de diretórios grandes podem consumir o prazo e reprovar o canário.

Recibos incluem timestamp UTC, duração, configuração/código, shapes, devices,
hashes, avisos e checksum. Replay verifica checksum e conserva o recibo original,
marcando inferência atual false e autorização longa false. Checksum não é
assinatura criptográfica de uma autoridade. Artefatos antigos de análise não
são reescritos. Nenhum recibo libera publicação, curadoria ou aprovação humana.

Homologar ainda: CUDA/CTranslate2, cache Community-1 sem token, YuNet/SFace/
MediaPipe/YOLO locais, Tesseract/fonts, Ollama e encerramento de chamadas
nativas reais no Windows/Tk. A regressão desta etapa utiliza backends falsos;
não houve execução real desses modelos.
