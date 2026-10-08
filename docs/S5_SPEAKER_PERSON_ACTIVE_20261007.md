# R4.9 — Sessão 5: Speaker ↔ Person e Active Speaker

## Contrato técnico

**Identidade global não é prova de fala contemporânea.**

- `mapping_summary[].person_id`: hipótese de associação persistente por speaker, sujeita a consenso e conflitos temporais.
- `intervals[].person_id`: pessoa global mapeada, **se vista naquele intervalo**. Pode existir em janelas sem comprovação audiovisual de fala; não direcionar a câmera usando apenas este campo.
- `intervals[].active_person`: **somente** uma pessoa com `CONFIRMED` e face observada contemporaneamente; do contrário `null`.
- `intervals[].active_speaker_state`: `CONFIRMED`, `PROBABLE` (identidade + face, fala local não verificada), `UNCERTAIN` ou `OFFSCREEN` (face mapeada não observada, **não** prova ausência física).
- `person_roles`: `SPEAKING` exige evidência positiva ou verificação humana. `LISTENING` indica presença quando outra pessoa é confirmada; não prova atenção psicológica. `REACTING` exige indicador explicitamente presente na observação (`reaction_detected` e `reaction_type`); no pipeline padrão pode permanecer não observado. `VISIBLE_UNDETERMINED` quando faltam provas.
- `audio_video_sync`: mediana e desvio de lag calculados a partir de janelas **não sobrepostas** e com limite inferior de correlação positivo. Trata-se de proxy heurístico, não probabilidade calibrada nem prova de separação de fontes de áudio.

## Regras de segurança

1. A detecção boca/áudio usa amostras locais, qualidade de sinal, limite inferior de correlação, offset tolerado, cobertura facial, continuidade de track, margem para outros rostos e consenso temporal.
2. Janelas com fala simultânea **não** são atribuídas automaticamente pelo áudio misturado. Mapeamento manual explicitamente verificado pode ser usado, mas conflitos manuais anulam o resultado.
3. Limites de shots interrompem associação por proximidade visual. Ausência de rosto, visão distante e pessoa fora de quadro geram motivos de diagnóstico, nunca person_id inventado.
4. Camera Timeline, Planner e Camera Director só usam `active_person` confirmado quando disponível. Entradas legadas sem este campo continuam compatíveis, porém recomenda-se replay com S5.
5. O procedimento não instala novos pesos, não altera diarização, não baixa modelos e não reprocessa trechos caros por padrão.

## Diagnosticar os cinco locutores não resolvidos

O projeto entregue contém **código e fixtures**, não a execução benchmark com os cinco locutores. Assim não há contagem pós-S5 nem confirmação de suas identidades. No Windows, aponte para a análise REAL (ou ZIP com artefatos de estágios):

```powershell
python scripts/dev/audit_speaker_s5.py "C:\analyses\EMERSON_CLOVIS" --output "C:\analyses\s5_audit"
```

O comando procura `05_diarization.json`, `08_person_reid.json`, `10_active_speaker.json` ou seus equivalentes legados `speaker_turns.json`, `people_observations.json`, `active_speaker_evidence.json`. **Não executa reconhecimento facial, diarização, FFmpeg nem Whisper**; usa o cache existente. Para medir efetiva melhora do áudio/boca, gere novas evidências da etapa `10_active_speaker` com a mesma `mono.wav`, ou rode a etapa no pipeline com um vídeo real.

Saídas:

- `speaker_s5_diagnostics.json`: quantidade de locutores sem identidade global versus sem fala local confirmada, razões, amostras temporais, durações, janelas com overlap, motivos das falhas de correlação e consistência de lag.
- `active_speaker_s5.json`: janelas reavaliadas, com `active_person` e `person_roles`.
- `speaker_annotations.csv`: janelas revisáveis dos locutores sem confirmação — preencher `human_person_id`, `human_role` e `annotation_status=verified`. Para ausência de pessoa, deixar ID vazio e selecionar `offscreen`; para dúvida escolher `uncertain`.

Após revisão humana:

```powershell
python scripts/dev/audit_speaker_s5.py "C:\analyses\EMERSON_CLOVIS" --output "C:\analyses\s5_audit" --evaluate "C:\analyses\s5_audit\speaker_annotations.csv"
```

`--neural-predictions piloto.json` aceita inferências de um backend externo com registros `{speaker_id,start,end,person_id}` (mesmas janelas) **somente para comparação**. Não integra automaticamente seus resultados ao pipeline.

## Piloto opcional com modelo neural ASD

Candidatos oficiais pesquisados:

- **LR-ASD** (IJCV 2025): https://github.com/Profysr/Active-Speaker-Detection
- **Light-ASD** (CVPR 2023): https://github.com/Junhua-Liao/Light-ASD
- **TalkNet** (ACM MM 2021): https://github.com/TaoRuijie/TalkNet-ASD

Ordem proposta: montar rótulos em trechos de plano aberto, close, fala simultânea, cortes curtos, reação e offscreen; medir *false positive / wrong person*, recall, F1, abstention, latency, memória, precisão do tempo A/V por perfil. Rodar modelos sob mesma amostra. Só promover backend após testes Windows/Python 3.11, licenças/pesos verificados, melhora significativa de erros e *sem* deteriorar o veto a associações ambíguas.

A heurística atual usa energia do áudio do mix; ela **não separa as vozes** nem executa um detector neural audiovisual. Não há comparação quantitativa de backends nesta entrega.

## Invalidação e replay

- `10_active_speaker` agora inclui `speaker_roles.py` nos arquivos de cache, invalidando seletivamente esta etapa e dependentes. Permanecem intactas transcrição/diarização e evidências visuais prévias.
- Reprocessar só o Active Speaker requer áudio mono em cache (salvar artefatos originais) e dados visuais da Sessão 4. O auditor offline usa evidências antigas mas aplica novo consenso; não melhora o sinal de boca retroativamente.
- Testes locais em Linux/Python 3.13 exercitam integração e fixtures; **Windows/Python 3.11 e vídeo real ainda requerem homologação**.
