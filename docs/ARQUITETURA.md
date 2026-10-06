> Evolução v3: [CAMERA_DIRECTOR_V3.md](CAMERA_DIRECTOR_V3.md). Etapa 19 separada, cache próprio e exportação 20.
> V4.2: preflight obrigatorio, camadas tracklet/person/participant e analysis.json
> por referencias. As descricoes antigas de "todas as etapas anteriores" no cache
> e fallback automatico sao historicas; consulte V4_2_IMPLEMENTATION_REPORT.md.

# Arquitetura e decisões

## Contrato desta primeira fase

Não há seleção final nem renderização. O pipeline retorna fatos medidos, hipóteses
de modelos, sinais heurísticos e lacunas explícitas.

Engine.run devolve status, data, notes e artifacts. Estados possíveis:

| Estado | Significado |
|---|---|
| ok | A etapa habilitada produziu o resultado esperado |
| partial | A etapa produziu dados com fallback ou limitações relevantes |
| skipped | Etapa explicitamente desativada |
| unavailable | Etapa opcional não conseguiu executar |

Metadados, extração de áudio e transcrição são indispensáveis e abortam em falha.
Etapas opcionais falham separadamente e registram o motivo. --strict exige que as
etapas habilitadas executem sem exceções.

Status complete não significa "verdade comprovada" nem cobertura de funções
desativadas. Consulte stage_status, issues e os métodos de cada observação.

## Engines

| Engine | Implementação | Limite principal |
|---|---|---|
| TranscriptionEngine | faster-whisper / CTranslate2 | ASR e alinhamento têm erros; sem forced align externo |
| DiarizationEngine | pyannote community-1 | Token, aceite do modelo e dependências; confiança null |
| SceneEngine | PySceneDetect ContentDetector | Mudança visual não é mudança semântica |
| PersonDetectionEngine | YuNet/Haar e HOG/YOLO | Perfis, oclusões e corpos sentados podem ser perdidos |
| Tracker | Matching global de IoU + SFace opcional | Crossing/oclusão podem fragmentar/trocar tracks |
| LipEngine | MediaPipe FaceLandmarker | Modelo local e faces suficientemente nítidas |
| ActiveSpeakerEngine | Correlação boca/RMS original | Heurística, exige amostras e margem; revisão necessária |
| OcrEngine | Tesseract em keyframes | Não estima permanência contínua do texto |
| SemanticEngine | Regras ou Ollama local | LLM pode errar mesmo citando IDs válidos |
| ReportEngine | JSON, Markdown, HTML local e SRT | Dados incertos permanecem identificados |

Não existe identificação civil automática. Embeddings faciais são usados somente
para continuidade de identidades anônimas dentro da análise do vídeo.

## Tempos e áudio

A referência é o início da trilha de vídeo, em segundos de precisão float.
Quando a trilha de áudio começa antes/depois do vídeo, a diferença de start_time
é compensada na extração. O original PCM mantém canais e sample rate.

Derivados não usam time stretching nem remoção de silêncio. Somente o decoder
interno ASR usa VAD, que devolve coordenadas de fala na referência do áudio.
WAV usa RF64 automático quando o tamanho exige.

Whisper pode deslocar timestamps. O programa conserva estimativas com método
explícito, e não transforma três casas decimais em garantia de precisão de 1 ms.

## Transcrição em blocos

Cada bloco central de 240 segundos lê 4 segundos adicionais dos dois lados.
Uma palavra pertence ao bloco cujo intervalo central contém seu ponto médio.
Isso evita duplicar o contexto compartilhado sem remover repetições legítimas.

Fonte original/clean é escolhida por pequenas amostras e diferença de probabilidade
do modelo. A escolha é registrada; probabilidade maior não garante texto correto.

Em multipass, hipóteses das regiões de baixa confiança são guardadas. Não há
reescrita do texto por plausibilidade. A reconciliação de discrepâncias fica
explicitamente para revisão humana.

## Sobreposição

Turns originais de diarização são preservados. Uma varredura temporal identifica
intervalos com mais de um speaker. Não se usa exclusive diarization para apagar
falas simultâneas.

Na associação por palavra, se dois locutores têm sobreposição comparável, speaker
fica null e speaker_candidates lista os candidatos. Uma transcrição mono comum
pode não recuperar integralmente as duas falas; a presença de overlap não garante
transcrição separada de cada voz.

## Pessoas e prioridade visual

Bounding boxes usam coordenadas 0–1. bbox_kind distingue body de face.
Quando só um rosto é detectado, não se inventa uma caixa de corpo.

A continuidade por IoU vale apenas dentro da mesma cena e de uma lacuna pequena.
Na troca de câmera, só embeddings suficientemente semelhantes permitem reusar
o ID. Um track não pode ser atribuído a duas detecções simultâneas.

safe_crop_possible significa somente que a caixa-alvo observada cabe num retângulo
9:16 de altura integral. Não garante composição artística, espaço para legenda,
corpo completo ou ausência de obstruções.

O speaker recebe foco quando há pessoa associada visível. Uma pessoa centralizada
sem vínculo não recebe automaticamente o papel de locutor.

Split screen exige duas vozes participantes e vínculos para pessoas distintas.
A extensão Director v3 exige presença contemporânea e crops seguros. Alternância de câmeras não autoriza split simultâneo. Recomendações legadas são locais; o Curator deve priorizar a timeline do Director v3.

## Cache e checkpoints

Assinatura de entrada: SHA-256 do arquivo completo, não só nome/tamanho/mtime.
Assinatura de etapa inclui:

- assinatura do vídeo;
- configuração relevante;
- estados das etapas anteriores;
- versões dos pacotes;
- hashes dos módulos Python;
- hashes de arquivos externos, quando aplicável.

Cada etapa salva JSON atomicamente em cache/VIDEO_HASH/. As etapas caras não
reexecutam se a assinatura e seus artifacts continuam válidos.
Chunks ASR também têm checkpoint próprio com hash da trilha usada.

Outputs leves são reescritos a cada retomada. Arquivo ausente invalida artifacts
da etapa correspondente. Use --force para repetir análise após instalar um backend
que anteriormente caiu em fallback, ou após mudar manualmente um serviço Ollama.

RUNNING.lock impede duas execuções na mesma saída. Após interrupção abrupta pelo
terminal, confira se não há processo ativo e remova apenas o lock.

## Memória e desempenho

Vídeo é decodificado sequencialmente. Só frames amostrados são recuperados para
detecção; frames completos não ficam todos na RAM. Cenas examinam o stream em
PySceneDetect. Há um limite para miniaturas.

ASR usa áudio por bloco e libera o modelo antes da diarização.
O backend community-1 recebe o áudio mono inteiro para manter identidade global;
float32 de duas horas a 16 kHz ocupa aproximadamente 460 MB, além dos modelos.
Não é correto diarizar blocos isoladamente e fingir que IDs locais são globais.

Observações, palavras e resultados estruturados ficam em memória. Vídeos muito
longos ou com muitas pessoas podem exigir bastante RAM/disco. Nesta versão não
há banco de dados de streaming para milhões de observações.

## Evolução recomendada

1. Validação com entrevistas reais PT-BR e métricas de erro ASR/diarização.
2. Forced alignment opcional para trechos que exigem sincronização mais precisa.
3. Modelo ASD audiovisual treinado, com benchmark e calibração para substituir a heurística.
4. Detector/tracker de corpo apropriado a pessoas sentadas e múltiplas câmeras.
5. Classificação de som e qualidade de fala calibrada para música sob entrevistas.
6. Armazenamento incremental de observações em vídeos muito longos.
7. Contrato do cut_plan.json e editor futuro, após selecionar e revisar os insights.
