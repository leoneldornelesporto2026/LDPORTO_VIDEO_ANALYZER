> Relatório histórico da entrega anterior. Resultados desta entrega v3: [TEST_REPORT_V3.md](TEST_REPORT_V3.md). A suíte recebida tinha 10 testes v2; a contagem antiga abaixo não foi reconstituída.

# Validação desta entrega

Data: 2 de outubro de 2026.

## Executado

- 27 casos de teste automatizado, cobrindo:
  - URLs de vídeo e rejeição de entradas inválidas;
  - configuração YAML e erros de digitação;
  - timestamps e transporte de milissegundos;
  - manutenção de falas sobrepostas e locutor ambíguo sem atribuição artificial;
  - preservação de repetição de palavras;
  - importação sem inventar alinhamento de texto;
  - blocos de legenda, pontuação e troca de locutor;
  - caixas normalizadas e geometria de crop futuro;
  - identidade temporal limitada à mesma câmera;
  - reidentificação por embedding sem duas caixas com um mesmo ID;
  - timeline sem buracos cobrindo a duração inteira;
  - duas pessoas visíveis sem participação comprovada não geram split screen;
  - semântica sem omitir segmentos e rejeição de IDs/tópicos inválidos do LLM;
  - heurísticas sem scores editoriais fictícios;
  - invalidação de cache por parâmetros e artifact ausente;
  - lock de execução;
  - ownership de chunks ASR sem duplicar contexto ou apagar repetições.
- Pipeline com FFmpeg/FFprobe/PySceneDetect/OpenCV reais sobre fixture de duas cenas,
  áudio sintético e anotações explicitamente importadas.
- Extração/tratamento com duração preservada.
- Caso real de arquivo com trilha de áudio deslocada +0,5s.
- Reexecução que usa cache e recria relatório removido.
- Compilação dos arquivos Python.
- Resolução das dependências base/visão para Windows amd64 / Python 3.11 por
  pip dry-run, sem executar a instalação Windows.
- Resolução de dependências base + diarização + visão + OCR para Python 3.12 / Linux
  por pip dry-run, sem carregar esses modelos opcionais.

## Não executado em ponta a ponta

- Reconhecimento real large-v3 de entrevista PT-BR.
- Diarização real community-1 com token/modelo autorizado.
- MediaPipe/YuNet/SFace aplicados a uma entrevista real.
- LLM Ollama real, qualidade semântica e retenção/viralização.
- OCR Tesseract real ou classificador PANNs real.
- Separação Demucs real.
- Download YouTube de vídeo real.
- Interface nativa em um desktop Windows e execução CUDA.

O teste de ASR em chunks substitui o backend por hipóteses controladas. A
importação da fixture testa o restante do pipeline, sem se passar por transcrição
de fala humana.

Um download de modelo tiny foi tentado no ambiente de teste, mas não ficou
disponível por incompatibilidade de transporte HTTP/proxy da sessão. Portanto não
há alegação de validação acústica real.

## Ambiente dos testes

Python 3.12.14, Linux, CPU, NumPy 2.2.6, OpenCV 4.11.0.86,
PySceneDetect 0.7.1, SoundFile 0.13.1, FFmpeg/FFprobe disponíveis.

## Executar no seu ambiente

    .\.venv\Scripts\python.exe -m pip install -r requirements/dev.txt
    .\.venv\Scripts\python.exe -m pytest tests -q
    .\.venv\Scripts\python.exe analyze.py --doctor

Para a primeira entrevista real, ouça trechos do início/meio/fim, confirme as
palavras marcadas e compare as miniaturas com os locutores antes de planejar crops.

## Etapa 52 — homologação final auditável (2026-10-09)

O histórico acima registra verificações anteriores; os resultados desta etapa estão
em `automacao/execucao/etapa52/` e no checkpoint 52. Homologação automática não
substitui parecer humano. READY_FOR_REVIEW, PREVIEW_APPROVED e PUBLISH_READY são
gates separados. Esta auditoria sempre mantém `publication_ready=false`.

### offline_verified

- Auditoria somente leitura, sem extração: `python scripts/dev/audit_homologation52.py
  --package <pacote.zip> --output <novo_relatorio.json>`.
- O comando verifica orçamento/tamanho, caminhos, symlinks e membros duplicados;
  hashes e bytes do manifesto; contratos atuais de IDs, Q&A, fila, estados e gates.
  Pacotes antigos conservam sua versão e seus problemas, sem migração implícita.
- `--feedback <feedback.json>` importa para validação local o contrato 4.4.0 com
  provider `manual_json`, source_sha256 e input_package_sha256 correspondentes.
  Um `approve` nesse JSON é proposta editorial; não é aprovação por hash de preview.
  Não ocorre upload remoto, renderização ou geração de ZIP. A integração de upload
  humano na interface requer homologação manual; a saída ZIP do exportador é
  verificada pelos testes sintéticos e pelo mesmo validador de pacote.
- `--baseline <analysis.json> --current <analysis.json>` só calcula deltas se
  metadata.sha256 e configuração completa coincidirem. A configuração deve estar
  em `config` ou ter `configuration_sha256` registrado. Nome, URL e hash de apenas
  uma etapa não provam equivalência. Diretórios contendo analysis.json são aceitos.
- As cifras 217/193/0/0, 4.080 flags, 7,05%, 0,058%, 4,31%, 6/0 zooms e dois clips
  de cabeça são alegações históricas fornecidas para comparação, não medições novas.
  Sem outputs comparáveis: pós e delta são null, status `not_measured`.
- A regressão usa fixtures controladas para export, replays, previews, hash de
  aprovação e entradas ZIP maliciosas. ZIPs temporários de fixtures não são
  snapshots do projeto. O teste que exporta o projeto completo é reservado ao
  orquestrador por proibição de snapshots nesta etapa; registrar sua exclusão.

### requires_real_media — checklist Windows / Python 3.11

- [ ] Registrar build, SHA256 da fonte e configuração antes/depois; usar a mesma
  fonte sem modificar os artefatos antigos. Não repetir a entrevista inteira por padrão.
- [ ] Conferir Tesseract instalado e idioma português; executar OCR em amostras
  autorizadas de tarja/QR, Openbox e Copa. Registrar texto, timestamps e status real.
  Contact sheets não provam OCR executado; skipped/ausente permanece desconhecido.
- [ ] Selecionar 10–20 goldsets anotados por pessoa, com pergunta/resposta, payoff,
  propaganda, fala ambígua, corte inicial/final e mudanças de câmera; guardar IDs e
  razões. Medir erros e cobertura; não promover heurísticas a probabilidades.
- [ ] Ouvir começo/meio/fim e trechos editados: literalidade, nomes, negações,
  hesitações, risadas comprovadas, sobreposição, sincronismo e legenda.
- [ ] Conferir QR/GC/tarjas e safe areas no quadro renderizado; evitar crops que
  transformem propaganda em conteúdo aprovado ou atribuam identidade sem prova.
- [ ] Renderizar canários curtos autorizados (vertical 1080x1920 e source_preserve),
  verificar frames, áudio, duração, SHA, recibos e origem. Não publicar MP4.
- [ ] Validar interface Windows, importação/upload local de feedback e ZIP de saída
  autorizado, Ollama/CUDA apenas em sessão manual própria; registrar falhas/skips.

### human_review_pending

- [ ] Revisar cada item da fila humana com transcrição, contexto e referências;
  manter publicidade excluída ou em revisão, nunca auto-aprovada.
- [ ] Conferir independência da avaliação de Q&A, payoff, legenda, crop e propaganda.
- [ ] Vincular decisão humana identificada ao SHA256 do pacote, fonte e preview
  exatos; alterar qualquer artefato exige nova aprovação. Testar hash divergente.
- [ ] Emitir parecer assinado/identificado e registrar bugs abertos antes de avaliar
  o gate de publicação. Relatório offline e testes verdes não aprovam publicação.

Os arquivos `AUDITORIA_CLOVIS_20261009.md` e
`SEGUNDA_CURADORIA_CLOVIS_PARCIAL.zip` não estavam disponíveis nos caminhos
informados nesta execução. A obtenção desses arquivos e de outputs pós comparáveis
permanece pendente; não há alegação de homologação real do vídeo Clóvis.
