# SOL V3 — GUI, diagnóstico corporal e conclusão

Data: 2026-10-13. Escopo: `app.py` e testes GUI focados. Scripts de inferência e sidecars de relatório são responsabilidade da integração principal.

A janela corporal mostra diagnóstico passivo de caminho solicitado/resolvido, versão instalada e condição do arquivo, sempre com `NOT_READY` e sem importar modelos ou executar inferência na abertura. O teste de quatro quadros exige clique e escolha de vídeo local; a GUI inicia somente `scripts/dev/smoke_body_detector.py` em worker, com lista de argumentos e pasta nova `.cache/body_smoke/<uuid>`. O subprocesso recebe política offline/sem instalação automática. Nenhuma escolha é salva por iniciar o teste.

O teste bloqueia concorrência com processamento, OCR ou outro smoke. Cancelar a escolha não cria saída. Parar/fechar termina exclusivamente seu subprocesso e preserva a saída parcial. A GUI exige saída exit 0, quatro quadros e todos os indicadores reais de carregamento/inferência bem-sucedida antes de mostrar `INFERENCE_EXECUTED`; isso continua explicitamente sem homologação de qualidade. Falha, cancelamento, relatório ausente ou malformado permanecem `NOT_READY`.

A conclusão lê causas tipadas de `quality_gate.json` (`reason_code`, com compatibilidade `code`), mostra revisão humana de áudio pendente de `source_audio_review.json`, distingue hipótese original `transcribe` de traduções separadas e mostra chamadas acústicas já medidas. O detector real vem de `video_analysis.quality.body_detection`; registros legados podem usar `vision_performance.body_backend_execution`, com leitura limitada a 4 MiB de `analysis.json`. Configuração/modelo presente não promove execução.

Prontidão editorial é descrita como “Editorial: pronta para revisao”. Aprovação de preview e publicação são campos separados do gate; `READY` de pacote legado não concede nenhum dos dois. Nenhum score, elegibilidade, política ou gate foi alterado.

## Verificação executada

- Novos testes: `src/tests/test_sol_v3_gui_review.py`, 13 passaram em 0,40 s.
- Regressão curta de GUI/OCR, incluindo os 13 novos casos: 29 passaram em 0,67 s.
- Comandos e saídas reais: [gui_focus.log](gui_focus.log).

Os testes novos cobrem abertura sem heavy imports, travas de concorrência, cancelamento, processo em worker e sinais no thread da GUI, caminhos com espaços, duas pastas de saída distintas, relatórios insuficientes/malformados, parada isolada e apresentação de causas/estados. O processo e relatórios do smoke são fixtures: nenhum vídeo foi decodificado, nenhuma chamada de GPU/Ollama/modelo foi feita e nenhuma dependência foi instalada nesta verificação. O teste corporal real de quatro quadros e sua avaliação humana continuam dependentes do clique explícito e do ambiente local preparado.
