# R4.9 — Sessão 8 | Commercial Gate, Broadcast Graphics, OCR e Stories

## Objetivo
Evitar que anúncios e autopromoções de convidados entrem como cortes editoriais, mantendo provas observadas e protegendo diversidade, título, texto em tela e exportação à segunda curadoria. Incremental sobre R4.9/S7. **Não é resultado de execução/homologação do vídeo Emerson/Clóvis**: o ZIP de código não contém os artefatos de benchmark completos.

## 1. Commercial Gate, fonte e propagação

- `src/ldporto/commercial_gate.py` mantém transcrição canônica imutável; valida janelas com timestamps e usa sinais comerciais (CTA, desconto, preço, parcelas, produto, patrocínio, evento etc.).
- `build_commercial_blocks`: encontra trechos ASR fortes; reconhece anúncios cujo CTA e preço caíram em até quatro segmentos temporalmente próximos; une janelas contíguas; identifica por `COMMERCIAL_NNNN`, mantendo IDs e evidências textuais. O algoritmo também incorpora, de forma limitada, uma frase anterior adjacente com pelo menos dois sinais comerciais. **Não exclui genericamente os 25 segundos anteriores**, pois isso produziria falsos positivos em entrevistas.
- Se parte de um corte intersecta o bloco confirmado, o corte perde elegibilidade; se só há indícios não confirmados, `eligibility=review` e bloqueio da shortlist até revisão. Uma menção neutra a marca não vira comercial automaticamente.
- Bloqueio/esclarecimento preservados no mapeamento `main_moments -> second_curation candidates -> core ZIP -> Stories`. O exportador nunca converte `review/excluded` automaticamente em elegível.
- Métricas explícitas em `candidate_metrics`: `commercial_block_count`, `excluded_commercial_count`, `commercial_review_count`, `commercial_gate_reasons`. A métrica de exclusão do pacote final continua calculada dos candidatos efetivamente exportados.
- Limitações: heurísticas lexicais não provam cobertura total nem classificam publicidade silenciosa. Fragmentos com OCR suspeito são bloqueados para revisão; a publicação requer curadoria humana.

## 2. Broadcast Graphics e Commercial Visual

- Estágios existentes **17b Broadcast Graphics** e **17c Commercial Visual** preservados e validados no encadeamento após Understanding. O resultado interno `measured/skipped/partial/unavailable` agora é propagado ao checkpoint; o projeto não anuncia etapa OK quando o backend opcional requisitado falhou.
- `broadcast_graphics.py` mede bordas fixas no tempo em 8 frames por candidato, zonas (lower third/banner) e amostragem. Detecção de região *não* significa reconhecimento do texto nem ausência comprovada de GC nos demais instantes.
- OCR Tesseract **opcional** no `commercial_gate.targeted_ocr`: três observações por candidato (`12%`, `50%`, `88%`), com `bbox` normalizado, confidence, método, timestamp e dica textual (`offer_or_price`, `lower_third_gc` ou outra). Não atribui duração entre amostras nem reconhece logos não textuais como marcas comprovadas.
- OCR isolado que parece anúncio gera `review`, não exclusão confirmada com base no áudio inexistente; a saída registra a incerteza. Em Windows, instalar binário Tesseract e dados `por`/`eng`, `pip install -r requirements/ocr.txt` e ligar `ocr.enabled` no `config/config.yaml`. O default permanece `false`. Se for habilitado mas o binário não estiver disponível, o estágio fica `unavailable` e o manifesto sinaliza degradação.
- Evidência de saída: `broadcast_graphics.json`, `commercial_blocks_s8.json`, `commercial_visual_s8.json` e equivalentes em `SECOND_CURATION` (`editorial/commercial_blocks_s8.json`, `editorial/commercial_review_s8.json`, `visual/broadcast_graphics_s8.json`, `visual/commercial_ocr_s8.json`).

## 3. Áudio de eventos

- Mantido o detector opcional PANNs existente (`14_audio_events`), com checkpoint local explicitamente configurado em `audio_events.checkpoint`; **não foi ligado sem modelo nem medição**. Se houver evento registrado com label de risada/aplauso e timestamp dentro do Story, o dado é referenciado por `audio_reaction_evidence`; ausência de evidência não é prova de que ninguém riu. Nunca infere speaker, punchline ou timing fino por um rótulo de janela larga.

## 4. Stories

- `social_output.select_story_set`: prioriza **distribuição temporal do episódio** por fases, depois acrescenta outros momentos se ainda atenderem restrições de tópico, categoria, duplicação de arc, espaçamento e não sobreposição. Sem preencher vagas artificialmente; os limites de candidatos determinam o horizonte observável, que pode não cobrir a abertura/encerramento da mídia inteira.
- Story com comercial `excluded`, `review` ou bloqueio editorial **não entra** no conjunto.
- `title_variants`: prioriza perguntas ou trechos literais; sugestões por IA exigem termos sustentados no transcript, com bloqueio de promessas textuais não apoiadas. Isso é um filtro lexical conservador, **não verificação semântica completa**; o título sempre requer revisão humana.
- Cada Story recebe `visual_plan`: preset de humor, pergunta/resposta, história, emoção, informação, curiosidade ou impacto; política explícita de zoom não decorativo; `layout_mode=source_preserve` salvo evidência temporal de reação/split; **nenhum crop é declarado aprovado antes do render final**.
- `caption_plan` contém retângulos normalizados propostos, zonas de GC, textos pontuais OCR, verificação de sobreposição e status `pending_frame_and_final_render`. Recalcular após crop, aspecto, rosto e áreas de UI da plataforma.
- Preservado bloqueio de karaokê por ausência de revisão de palavras/timestamps da S7.

## 5. Auditoria offline e homologação

```powershell
.venv\Scripts\python.exe scripts\dev\audit_commercial_stories_s8.py "C:\analises\EMERSON_CLOVIS" --output "C:\analises\s8_audit"
```

Também aceita um ZIP de análise que contenha os artefatos. Saídas: `commercial_stories_s8_audit.json` e `commercial_human_review_s8.csv`; não reroda OCR, ASR, visão, PANNs ou LLM. CSV vazio para anotações humanas; não são calculadas taxas de precisão/recall sem rótulos de referência.

Homologação real: executar no Windows Python 3.11 com vídeo original, verificar comercial completo, merchandising informal e falas promocionais do convidado, falsos positivos com marcas mencionadas, OCR de GC/preço, presença e legibilidade de overlays após render, distribuição de Stories por todo o episódio, e exame auditivo dos clímax/reações. Só depois comparar quantitativamente *antes vs depois*.

## Testes e limites

- Regressão de S1–S7 preservada; novos testes de bloco multi-segmento, autopromoção, fragmento de anúncio, vizinhança de marcas neutras, OCR pontual com bbox, stage status, detecção temporal de GC sintético, títulos, seleção no início/meio/fim, eventos opcionais, caixas de texto, auditoria em pasta/ZIP, exclusão preservada no export.
- Validação de sintaxe Python 3.11 via AST; isso **não substitui** teste de dependências, OCR/Tesseract e render no Windows.
- **Não é possível provar que nenhum anúncio acidental escapou** só com os testes unitários. Falsos negativos, OCR em cenas reais e interface de títulos/overlays precisam de mídia e revisão manual.

### Cobertura limitada das janelas visuais

O limite padrão `export.second_curation_visual_candidate_limit=16` é um **orçamento por estágio**, não prova de que o vídeo inteiro foi inspecionado para GC/comerciais visuais. O resultado S8 inclui `requested_candidate_count`, `inspected_candidate_ids` e `uninspected_candidate_count`. Cada Story marca se sua janela foi amostrada; não amostrado/sem backend requer revisão visual manual. O usuário pode elevar o limite (config admite até 100), ciente do custo de OCR e seeks em vídeo. O classificador lexical ASR continua avaliando todos os segmentos comerciais processados, independentemente desse limite.
