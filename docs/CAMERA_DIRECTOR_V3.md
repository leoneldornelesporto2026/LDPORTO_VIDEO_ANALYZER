# Camera Director v3 — uso, contratos e limites

Esta entrega evolui o projeto recebido. O Analyzer recomenda câmera; o Curator
continua responsável pela curadoria, crop, legendas e renderização. Não foi
introduzido serviço em nuvem ou modelo pesado. Os módulos ASR, áudio, semântica,
instalação e GPU existentes foram preservados.

## Uso no Windows

Atualização: faça backup do projeto e extraia o conteúdo deste ZIP na raiz do
projeto existente. Preserve sua `.venv`, modelos, vídeos e análises locais; esses
itens não são distribuídos aqui. Compare seu YAML personalizado antes de substituir
`config/config.yaml`. Nenhuma nova dependência de produção foi adicionada.

Instalação nova: `INSTALAR_WINDOWS.bat`, os extras já documentados em
`LEIA_PRIMEIRO.md`, e `ABRIR_ANALYZER.bat`. A etapa de câmera funciona em CPU.

Na GUI: marque Camera Director, escolha o perfil e execute ANALISAR. A configuração
avançada permite alterar hold e máximo de zoom; campos vazios usam o YAML/perfil.
O resumo mostra cobertura de active speaker, cobertura visual do Director, plano
médio, trocas/minuto, split e foco incerto. O log registra status da etapa 19.

```powershell
.\.venv\Scripts\python.exe analyze.py "C:\Meus Vídeos\entrevista.mp4" --camera-profile natural
.\.venv\Scripts\python.exe analyze.py "https://www.youtube.com/watch?v=VIDEO_ID" --camera-profile podcast
.\.venv\Scripts\python.exe analyze.py "C:\Meus Vídeos\entrevista.mp4" --no-camera-director
```

## Reprocessar somente o Director

```powershell
.\.venv\Scripts\python.exe analyze.py --director-only "analysis\video_ID" --camera-profile podcast
```

Também disponível no botão **Reprocessar só câmera**. Exige `analysis.json`
completo produzido pelo Analyzer; não exige o vídeo original disponível. Reutiliza
observações, shots, active speaker, movimentos e semântica salvos. Reescreve os
exports/handoff para refletir a nova decisão. Não executa ASR, diarização, tracking,
OCR, download nem extração de áudio. `--force` nessa modalidade força somente o
Director; na análise normal, `--force` mantém seu significado anterior (todas as etapas).

A amostra enxuta recebida não contém `analysis.json`/`people_observations.json`;
ela não pode ser usada como análise completa neste comando. O teste de compatibilidade
lê as caixas amostradas existentes em `timeline.json` sem fabricar novas observações.

## Cache

`19_camera_director` fica depois de `18_analysis_quality`, portanto mudanças somente
na configuração/código do Director não invalidam etapas caras anteriores. Sua chave
inclui assinatura do vídeo herdada, schema 3.0, parâmetros, hashes de implementação
e digest das entradas efetivamente consumidas (observações, frames, shots, active
speaker, movimento, Q&A, arcs e momentos). A exportação é barata e recriada.

A atualização da percepção nesta entrega invalida uma vez seus checkpoints alterados
(05 em diante, conforme dependências); isso é necessário para não reutilizar a lógica
antiga. ASR/extração não foram alterados. Alterar apenas o perfil depois da atualização
não repete percepção. Cache parcial/indisponível mantém o comportamento legado;
use `--force` em director-only para tentar novamente após corrigir falha.

## Perfis

| Perfil | Intenção | Defaults principais |
|---|---|---|
| natural | Padrão estável | Hold 3 s, cooldown 3 s, zoom nominal 1.18 |
| podcast | Planos mais longos | Hold 4 s, preferido 9 s, reação menos frequente |
| dynamic_short | Mais ativo, ainda conservador | Hold 2.5 s, nominal 1.22 |
| documentary | Preservar enquadramento | Hold 5 s, nominal 1.05, sem reaction shots |
| conservative | Poucas intervenções | Hold 6 s, nominal 1.05, sem split/reaction |

Um único engine usa esses parâmetros. Overrides YAML não nulos prevalecem sobre o
perfil; `null` em parâmetro opcional significa herdar o perfil/default. Valores,
tipos, números finitos e relações entre limites são validados. `enabled` e `profile`
não precisam existir no YAML antigo: os defaults são adicionados no carregamento.

```yaml
camera_director:
  enabled: true
  profile: natural
  debug_output: true
  min_hold_seconds: 3.0
  preferred_hold_seconds: 6.0
  switch_cooldown_seconds: 3.0
  speaker_confirm_seconds: 0.9
  short_interruption_seconds: 1.0
  switch_margin: 0.15
  horizontal_deadzone: 0.06
  vertical_deadzone: 0.05
  max_zoom_default: 1.35
  max_zoom_hard: 1.40
  enable_split: true
  enable_reaction_shots: true
  enable_lookahead: true
  lookahead_seconds: 1.8
```

A lista completa de parâmetros/defaults está em `CAMERA_PARAMETERS.md`.

## Evidência e active speaker

A correlação labial/áudio existente agora é avaliada em janelas independentes de
até 3 s. O consenso exige pelo menos duas janelas não sobrepostas, suporte dominante
e score mínimo; duplicatas não contam. Empates permanecem sem associação. Mapping
manual é respeitado apenas nos intervalos fornecidos. Visibilidade local continua
obrigatória mesmo para mapping manual. Overlap é recalculado pelas vozes simultâneas,
sem marcar um turno inteiro como fala simultânea só porque houve uma interrupção.

`active_speaker.json` conserva o array e os campos legados, enriquecidos com
`mapping_confidence`, `mouth_activity_score`, `mouth_audio_score`, `visibility_score`,
`visual_observed_at`, `unresolved_reason`, `confidence_is_calibrated`.
`mouth_activity_score` é variação de abertura/segundo, **não** probabilidade normalizada.
O resumo adiciona contagens de evidência, conflito, cobertura e consistência.
Não há identidade civil inferida. A ausência de diarização não cria locutor fictício.

## Política de direção

- Confirmação de locutor, hold, cooldown, custo de troca e margem sobre o atual.
- Memória de foco/layout/posição/zoom, histerese de entrada/saída e bônus de persistência.
- Modos MONOLOGUE, DIALOGUE, QUICK_EXCHANGE, QUESTION_ANSWER, OVERLAP,
  REACTION, GROUP_DISCUSSION, B_ROLL e NO_CLEAR_SPEAKER.
- Alternância rápida privilegia two-shot quando os dois participantes relevantes
  cabem no crop; caso contrário, split somente se as duas faces contemporâneas
  tiverem crops seguros e disponibilidade futura suficiente para o hold.
- Não cria split com pessoas de câmeras alternadas ou somente porque há duas faces.
  Atribuição esquerda/direita é estável. Painéis são crops estáticos conservadores;
  se a pessoa sair da região segura, o Director abre para full-frame.
- Fala longa pode abrir lentamente com contexto de história, Q&A ou enquadramento
  medium/wide. Momento editorial fundamentado pode sugerir push-in. Não é timer
  de zoom periódico e não alterna close/aberto arbitrariamente a cada janela.
- Reaction shots usam pico de movimento do listener, mantendo áudio do locutor.
  Não nomeiam emoção. São curtos, têm cooldown próprio e retorno ao locutor.
- Safety exit (pessoa invisível/crop inviável/overlap/corte da fonte) pode interromper
  hold. Isso é registrado como decisão de segurança, não uma troca normal.

## Geometria e movimento

Coordenadas normalizadas no frame fonte orientado. Zoom é relativo ao maior crop
com proporção da saída (padrão 9:16), não relativo à largura inteira do vídeo horizontal.
`full_frame` significa preservar toda a fonte com **fit_with_padding**, não executar
um crop 9:16 central que poderia remover pessoas.

Máximo considera resolução de origem/saída, bbox com headroom/torso observado,
sharpness disponível e limites configurados. Fonte 1080p horizontal para saída
1080×1920 tem cap de zoom digital 1; `baseline_requires_upscale=true` explicita que
até o crop vertical de base exige ampliação. Nitidez ausente limita zoom a 1.
Não se estima blur/olhos/pose quando não há medição válida.

Pan e zoom usam integração amortecida com velocidade, aceleração e jerk limitados.
Deadzone e confirmação de movimento evitam seguir jitter. Lead room usa movimento
medido, não direção de olhar inventada. Saltos de foco são **cortes explícitos**;
não se interpola atravessando outra pessoa ou um hard cut. A segurança é conferida
nas amostras; o Curator ainda deve validar frames reais ao renderizar.

Lookahead antecipa abertura para futura troca de locutor, sem atribuir a fala antes
que aconteça. O horizonte para na borda do shot. Perto do corte não começa novo pan;
movimento já iniciado pode desacelerar/concluir no mesmo shot.

## Artefatos e consumo pelo Curator

| Artefato | Contrato |
|---|---|
| camera_timeline.json | Percepção local v2; mantém campos/array; janelas limitadas por shots e fala |
| camera_director_timeline.json | Array de decisões com `schema_version: "3.0"` em cada intervalo |
| camera_director_debug.json | Objeto v3, opcional; eventos, candidatos, scores, razões e estado |
| master_timeline.json | Mantém v2; adiciona `camera_director_intervals` com IDs e interseções temporais |
| analysis_quality.json | Mantém métricas existentes; acrescenta métricas do Director |
| video_understanding.json | Acrescenta resumo `camera_director` e referência para arquivos |
| CHATGPT_ANALYSIS_HANDOFF.json/.md | Mantém contrato v2; acrescenta extensão Director v3 e resumo legível |

Schemas publicados em `schemas/`. Campos legados não foram removidos nem renomeados.
O schema geral/versão do engine v2 permanece para compatibilidade e cache; a extensão
é identificada por `camera_director_schema_version` e metadata `camera_director_version`.

Cada decisão tem intervalo `[start,end)`, `director_id`, `source_shot_id`, modo,
foco, pessoas visíveis, layout, framing, razões, crop, split e câmera. Intervalos
iguais são compactados; mudanças de áudio preservadas em `audio_events` e trajetórias
em `camera.keyframes`. O consumidor deve usar os **keyframes**, não interpolar apenas
entre começo/fim ignorando a trajetória. Não interpolar através de `source_cut`,
`cut` ou `safety_cut`. Para full-frame usar fit/padding; para split usar ambos os crops
registrados no mesmo período. As recomendações são editáveis, não cortes finais.

Handoff inclui timeline compactada completa, configuração efetiva, métricas, referência
do debug, motivos de supressão, áudio versus foco, source shot, Q&A/arcs/momentos,
framing, trajetórias, segurança geométrica, incerteza e candidatos split/two-shot.
Não duplica o debug inteiro no handoff para evitar crescimento desnecessário.

## Métricas

`camera_director_coverage` mede disponibilidade de evidência visual amostrada;
`camera_director_timeline_coverage` inclui fallback full-frame e pode chegar a 1
sem significar que todos os focos foram resolvidos. `unresolved_focus_fraction`
mede tempo sem pessoa de fala resolvida fora de regiões preservadas/sem evidência.
Trocas/minuto contam mudanças entregues de foco/layout no mesmo source shot;
plano médio considera cortes da fonte e mudanças virtuais, não simples mudança de
modo de conversa. Contagens de supressão/deadzone são por janela de avaliação,
não número de turnos distintos. Não confundir ausência de evidência com qualidade alta.

## Performance e passagens visuais

O Director não abre vídeo, não carrega modelos e usa cursores/índices temporais.
A amostragem adaptativa usa a passagem visual existente: transição de speaker,
fronteira de cena, movimento e múltiplas faces aumentam temporariamente a frequência.
Sem evidência labial, registra o motivo; não faz uma segunda passagem para tentar ASD.
Mantém PySceneDetect em passagem própria, pois mudar esse backend alteraria a detecção
existente. Frames de momentos usam seeks pontuais de FFmpeg já existentes, não uma
nova análise inteira por feature. `DIRECTOR_BENCHMARK.json` traz medida sintética de
600 s, incluindo instrumentação tracemalloc (não um benchmark GPU/ASR).

## Limitações e diagnóstico

- Active speaker continua heurístico; não foi treinado/calibrado um modelo ASD.
- O detector de shots existente classifica geometria e vazio; não há classificador
  semântico geral novo de logos/B-roll. Quando esses rótulos chegam, são respeitados;
  rótulos desconhecidos não são inventados. Sem mapping confiável, preserva o frame.
- Split seguro significa segurança nas observações amostradas, não prova frame a frame.
- Reaction detection usa movimento, não sentimento, risada comprovada ou gaze.
- Vídeos/GPUs/modelos reais e GUI nativa Windows exigem validação local, descrita no
  relatório desta entrega. Sintaxe foi verificada para Python 3.11; runtime aqui é 3.12.
- Para foco null: confira diarização, landmarks, consenso e observações. Não reduza
  limiares cegamente para forçar uma associação.
- Para zoom 1: confira resolução/saída, `quality_unknown`, headroom e nitidez.
- Para split rejeitado: consulte `split_eligibility` no debug.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements/dev.txt
.\.venv\Scripts\python.exe -m pytest src\tests -q
.\.venv\Scripts\python.exe analyze.py --doctor
```

Ou execute `TESTAR_WINDOWS.bat`. Os testes requerem as dependências base e FFmpeg;
não baixam Whisper/pyannote/Ollama. Gerador visual opcional:

```powershell
.\.venv\Scripts\python.exe scripts\generate_director_fixture.py --output "temp\fixture"
```

Ele cria vídeo de figuras geométricas com anotações explícitas, não fala humana nem
resultado de um detector treinado. Vídeos gerados não estão incluídos no ZIP.

## ASD opcional avaliado

Foi consultado o projeto primário TalkNet-ASD. O código publica licença MIT;
a instalação documentada parte de Python 3.7.9 e dependências pouco restritas
(incluindo torch/torchaudio e youtube-dl). Não foi estabelecida compatibilidade
validada Windows/Python 3.11 com a pilha recebida, nem foram executados seus pesos.
Decisão: não adicionar esse backend/dependência nesta entrega. Mantém-se fallback
local determinístico e a futura substituição modular da etapa de active speaker.

Fontes consultadas em 04/10/2026:
- https://github.com/TaoRuijie/TalkNet-ASD
- https://github.com/TaoRuijie/TalkNet-ASD/blob/main/requirement.txt
- https://github.com/TaoRuijie/TalkNet-ASD/blob/main/LICENSE.md
