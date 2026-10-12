# OCR na GUI — Windows

O checkbox **OCR comercial / texto na tela (Tesseract)** lê `ocr.enabled` do
perfil atual. Não habilita OCR por padrão. Cada escolha explícita salva somente
o escalar OCR alterado, preservando as outras opções e comentários YAML. Cancelar
a seleção do executável não salva nem muda o caminho. **Usar PATH** salva null
somente em `ocr.tesseract_cmd`, sem alterar o PATH do Windows.

Selecione um `tesseract.exe` local existente. O Python utilizado pelo launcher
precisa ter pytesseract disponível. O tessdata selecionado pelo executável deve
conter `por.traineddata` e `eng.traineddata` para `por+eng`; os arquivos precisam
ser legíveis, não vazios e carregáveis. Confira permissões de leitura e execução.
O aplicativo não instala dependências, executáveis ou idiomas.

**Verificar OCR** testa dependências, executável e idiomas em worker. **Pronto**
significa configuração verificada, sem inferência em vídeo. **Smoke sintético**
é uma ação explícita separada, executada em worker, usando a fixture curta da
etapa 53. Seu sucesso não homologa mídia real. Alterar uma opção durante o teste
invalida seu resultado; ANALISAR verifica novamente antes de lançar a CLI. O
preflight da CLI continua sendo a segunda barreira. OCR solicitado com dependência
ausente permanece habilitado e bloqueado, sem fallback silencioso.

Para um teste local, selecione executável e idiomas, habilite conscientemente,
verifique e opcionalmente execute smoke. Isso não altera ASR/CUDA, Ollama, câmera,
Stories, diarização, visão ou force. Não existe perfil global novo nem reprocessamento
automático. Ao concluir o teste, desabilite voluntariamente se esse for seu perfil
usual. Desligado implica visual comercial `not_measured / requires_review`.

Execuções futuras incluem `ocr_execution.json`, `analysis_summary.json` e
`llm_insights.json` com OCR geral 13 e comercial 17c separados: estado, frames
medidos, falhas, idiomas e tempo de execução da rotina (não permanência do texto).
Os recibos também ficam nos payloads de cache. Sem recibo em cache antigo,
idiomas/tempo e contagens ausentes permanecem null. A tela de execução exibe o
resumo salvo ao concluir; antes disso mostra solicitado/ignorado e as etapas.
Nenhum estado OCR aprova publicação; revisão humana e canários continuam exigidos.
