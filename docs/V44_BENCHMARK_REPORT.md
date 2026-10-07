# V4.4 Benchmark Report

Baseline real reconciliado em [V44_BASELINE_RECONCILIATION.md](V44_BASELINE_RECONCILIATION.md).
Fonte e run V4.3 preservados. O full run V4.4 está IN_PROGRESS, retomando
checkpoints da própria tentativa V4.4 após correção de acesso ao cache de
diarização. A tentativa inicial terminou com parada segura (exit 130), após
ASR 731 s e cenas 894.6 s; seus logs e manifesto foram preservados. Nenhuma
métrica dessa tentativa foi tratada como full-run validada. O wall time da
retomada não será comparado isoladamente à execução completa V4.3.

| Métrica | V4.3 full run | V4.4 full run | Delta |
| --- | ---: | --- | --- |
| Tracklets brutos | 6085 | não executado | não medido |
| Hipóteses online no último log | 5755 em 8231s | não executado | não comparável a tracklets |
| Tracklets válidos / micro | 1818 / 4267 | não executado | não medido |
| Speaker/person | 3.2065% | não executado | não medido |
| Active speaker | 2.4560% | não executado | não medido |
| Foco de câmera / Smart Zoom | 0 / 0 | não executado | não medido |
| Semantic fallback | 26.0870% | não executado | não medido |
| Story payoff | 0 | não executado | não medido |
| Candidatos / shortlist | 213 / 12 | não executado | não medido |

Fixtures e replay serão relatados separadamente. Não há alegação de ganho de
performance de vídeo inteiro derivada de mocks, fixtures ou replay.

## P0-A — replay separado

87 testes verdes. Replay de áudio/mouth sobre WAV e observações reais preservadas:
speaker/person 15.0490% versus 3.2065%; active speaker legado 9.6733% versus 2.4560%.
Provável sem overlap 8.0853%, confirmado 0%. Conflito de mapping registrado 0.
Sem ASR, visão ou LLM reexecutados. Isto não mede falsos positivos contra identidade
anotada, nem runtime de full run. Evidência em `.cache/v44_validation/P0A_audio_replay`.

## P0-B — replay separado

Foco resolvido 15.1801%: 9.8220% face dominante visual e 5.3582% apoiado em
speaker/person. Fonte preservada 84.8199%. Trocas 2.75075/min, 556 resets de shot.
Sete propostas de zoom; **zero eventos entregues, máximo/médio 1.0x**.
Split/two-shot zero no replay. Não se infere identidade a partir de crop.
Evidência: `.cache/v44_validation/P0B_camera_replay_delivered`.

Diagnóstico das sete propostas: o teto geométrico/de qualidade era 1.125x,
portanto não bloqueava todo zoom. A evidência do mesmo alvo sustentou a
transição por apenas 0.25–2.069 s, contra a duração mínima de seis segundos.
Perda de confiança, retorno à fonte ou close da câmera original interromperam
a curva; nenhum keyframe ultrapassou 1.0x. Não remover dwell/deadzone nem
relaxar identidade para transformar propostas em eventos entregues.

## P0-C e P0-D — replay separado

Gate aplicado aos 209 principais: comerciais 2→7, incluindo os três falsos
negativos Havan/Openbox e dois outros reads Openbox conferidos no texto literal.
Shortlist elegível desse replay 12→11; candidatos restantes continuam disponíveis
à segunda curadoria. Recuperação de histórias: 154 arcos, dois completos,
seis payoffs (inclui quatro Q&A). ASR direcionado executou duas janelas, 9.34 s
de áudio, sem substituir a transcrição canônica. Fallback semântico V4.4 ainda
depende da nova inferência LLM no benchmark completo.

## Segunda curadoria e Curator — validação curta real

Pacote derivado READY contém 213 candidatos, shortlist 11, contato visual
adicional para MOMENT_00042_0001 (rank original 15). Import direto manteve IDs,
fonte e bounds; preview real de 89.22 s usou o candidato promovido, legendas,
refinamento local e 12 amostras do MP4 no verifier. Foco visual 41.47%, nenhum
speaker confirmado por percepção local, nenhuma aprovação humana fabricada.

Seis renders reais (preview/final): interview 3200–3208, comercial 7059–7067,
payoff 7800–7808. Foco visual 0%, 0%, 32.91%. Crop e split com uma faixa GC
inteira; inspeção visual identificou corte lateral do GC, corrigido no FFmpeg.
O verifier mede visibilidade/bordas em amostras, não acurácia anotada.
Os renders da revisão final serão conferidos após o benchmark para evitar
concorrência GPU durante a medição. O segundo preview de validação anterior
coincidiu brevemente com o início do ASR da primeira tentativa: seu tempo não
serve como comparação controlada de performance.

## Suites e limites atuais

Antes da retomada: 404 testes Analyzer e 34 Curator verdes; Curator passou a
35 com feedback opcional. Python 3.11.9/Windows nos dois ambientes. As regressões
incluem áudio curto, OpenCV e FFmpeg real nas duas resoluções, além de fixtures.
Não foi executada limpeza pesada real. Nenhum commit/push/merge/reset/clean.

Coverage representa extensão de evidência temporal, não medida de identificação
correta contra anotação humana. Smart Zoom entregue permanece zero no replay;
não se força movimento para atingir meta. Status full-run e deltas finais só
serão atualizados depois do término da execução e da validação dos artefatos.
