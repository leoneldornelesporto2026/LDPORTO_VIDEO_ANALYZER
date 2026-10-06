> **Atualizacao V4.3:** a orientacao principal e o [README](../../README.md).
> Runtime oficial: Python 3.11.x. O instalador normal inclui diarizacao/visao e preflight obrigatorio.
> Leia o [relatorio V4.2 historico](../V4_2_IMPLEMENTATION_REPORT.md).
> As instrucoes historicas abaixo sobre fallback/instalacao avancada nao substituem
> o contrato V4.2: recurso habilitado quebrado aborta ANTES de baixar/processar video.
> **Camera Director v3 historico:** leia [CAMERA_DIRECTOR_V3.md](../CAMERA_DIRECTOR_V3.md).
> Novo `camera_director_timeline.json`, perfis na GUI e `--director-only` para ajustar câmera sem repetir percepção.
> Relatório historico: [TEST_REPORT_V3.md](../TEST_REPORT_V3.md). Documentação v1/v2 abaixo preservada como referência.

# L.D.PORTO VIDEO ANALYZER — começar aqui

Este pacote implementa a **fase de análise**. Recebe um arquivo de vídeo ou um link
do YouTube, transcreve, gera timestamps por palavra e organiza informações para
planejar a edição depois. Não renderiza Shorts, cortes, crops, títulos ou CTAs.

## 1. Instalar no Windows

1. Extraia o ZIP inteiro para uma pasta, por exemplo C:\LDPORTO_VIDEO_ANALYZER.
2. Tenha **Python 3.11.x, de 64 bits**, com o launcher "py" e suporte a Tcl/Tk.
   Instalações oficiais: https://www.python.org/downloads/windows/
3. Execute **INSTALAR_WINDOWS.bat**. Ele cria um ambiente isolado, instala os
   pacotes e tenta instalar FFmpeg e Deno via winget quando faltarem.
4. Depois da instalação, feche e reabra o terminal/janela. Execute
   **DIAGNOSTICO_WINDOWS.bat**. FFmpeg, FFprobe e base_ready devem estar disponíveis.
5. Execute **ABRIR_ANALYZER.bat**. Selecione um arquivo ou cole a URL do YouTube.

Não há cobrança por API nesta implementação. Os modelos e o vídeo são baixados
quando necessário; a análise acontece localmente. Para trabalhar offline, os
modelos devem estar disponíveis antes e a entrada precisa ser um arquivo local.

Se o instalador apresentar erro, ele não comprova instalação completa. Copie a
mensagem do terminal e o diagnóstico para resolver a dependência que faltou.

## 2. Ativar as funções avançadas

Execute **INSTALAR_AVANCADO_WINDOWS.bat**. Ele instala diarização, MediaPipe e o
wrapper de OCR, e baixa os modelos oficiais de visão.

### Diarização

1. Aceite os termos de acesso do modelo em
   https://huggingface.co/pyannote/speaker-diarization-community-1
2. Crie um token de leitura em https://huggingface.co/settings/tokens
3. Cole o token no campo **HF_TOKEN** da janela. Ele fica somente em memória na
   sessão e é passado ao processo local; o programa não o salva no config.yaml.

Alternativa pelo PowerShell, somente na sessão atual:

    $env:HF_TOKEN = "SEU_TOKEN"
    .\.venv\Scripts\python.exe analyze.py "C:\Videos\entrevista.mp4"

O modelo community-1 executa localmente. Sem acesso/dependencias, o preflight
interrompe antes do video. Para trabalhar sem diarizacao de forma explicita,
desmarque Diarizacao na GUI ou use `--no-diarization`; locutores permanecem null.

### Análise semântica detalhada com Ollama — modo recomendado

A forma mais simples no Windows é executar **CONFIGURAR_OLLAMA_MAXIMO_WINDOWS.bat**.
Esse script instala o Ollama via winget quando necessário, mantém o servidor em loopback,
detecta VRAM NVIDIA e escolhe automaticamente um Qwen3 adequado: 8B para máquinas
menores, 14B quando há pelo menos ~12 GB de VRAM e 30B quando há pelo menos ~22 GB.
Ele também atualiza `config/config.yaml` para `backend: ollama` e `profile: max`.

Para forçar um modelo específico:

    CONFIGURAR_OLLAMA_MAXIMO_WINDOWS.bat qwen3:14b

O Analyzer usa somente `http://127.0.0.1:11434`. A transcrição é enviada em blocos ao
modelo local usando **JSON Schema**, e cada tópico/momento precisa citar IDs reais. O perfil
`max` usa contexto de 32768 tokens, `keep_alive: 30m` e uma segunda passada de revisão
editorial global. Essa revisão gera `ollama_editorial_review.json` com candidatos fortes,
justificativas, hooks e ideias de título; hooks/títulos são texto editorial novo, nunca fala
atribuída ao vídeo.

A interface mostra os modelos instalados e permite trocar entre `max`, `balanced` e `fast`.
Se faltar RAM/VRAM no `max`, use `balanced`; o diagnóstico exibe GPU NVIDIA, modelos
instalados, modelos atualmente carregados e opções efetivas do Ollama. Use `ollama ps` para
confirmar se o modelo está em GPU, CPU ou dividido.

Sem Ollama ou se um bloco falhar, o pipeline preserva a análise e cai explicitamente para
heurística naquele trecho. **A heurística não faz compreensão semântica profunda.**

### OCR

Além do extra Python, é necessário instalar Tesseract e os idiomas por e eng.
Depois, edite config/config.yaml:

    ocr:
      enabled: true
      languages: por+eng
      tesseract_cmd: "C:/Program Files/Tesseract-OCR/tesseract.exe"

O OCR é amostrado nas miniaturas. A duração de um texto na tela não é inventada.

## 3. Primeiro processamento

Use primeiro um vídeo curto para confirmar ambiente, download dos modelos e
qualidade. Depois processe o vídeo inteiro.

- **large-v3:** configuração padrão para priorizar transcrição. CPU funciona,
  mas vídeos longos podem levar horas; o tempo depende do seu computador.
- **auto:** usa o dispositivo disponivel; NVIDIA com CUDA quebrada nao cai para CPU
  sem `transcription.allow_cpu_fallback: true`. `--device cpu` e uma escolha explicita.
- **medium/small:** alternativas com custo menor de processamento; revise a fala.
- **tiny:** útil para testar instalação, não é a configuração recomendada para
  a transcrição final de entrevistas em português.

O texto reconhecido não passa por reescrita do LLM. Gírias e repetições reconhecidas
ficam no resultado. Nenhum ASR garante reconhecer toda hesitação ou toda palavra;
trechos incertos e hipóteses alternativas precisam ser ouvidos.

## 4. Onde ficam os resultados

Pelo terminal, o padrão é analysis/NOME_HASH/. Pela janela, é analysis/video_ID/.
A janela reutiliza a mesma pasta para a mesma entrada e permite retomar checkpoints.

Arquivos principais:

| Arquivo | Uso |
|---|---|
| llm_insights.json | Pacote completo para ChatGPT/segunda fase |
| ollama_editorial_review.json | Revisão global local: melhores candidatos, hooks e ideias de título |
| PARA_ENVIAR_AO_CHATGPT.txt | Instrução pronta para acompanhar os insights |
| report.html | Relatório local pesquisável; abre no navegador sem servidor |
| report.md | Relatório completo em texto |
| transcript.txt | Transcrição por intervalo e locutor |
| transcript.srt | Legenda legível, com blocos curtos |
| words.json | Palavras, timestamps, probabilidade e alertas |
| caption_segments.json | Blocos com palavras individuais para destaque futuro |
| analysis.json | Metadados e referencias com checksum; modo completo apenas por opcao explicita |
| people_observations.json | Caixas e amostras de tracking para o editor futuro |

**Depois do processamento, use SECOND_CURATION_READY/PARTIAL em pacotes_para_enviar/.** Se houver dúvidas
visuais, envie as miniaturas relevantes e, para palavras incertas, o trecho de áudio.

## 5. Limites desta versão

- Timestamps de palavras são estimativas do alinhamento Whisper, não medição
  acústica infalível nem forced alignment externo.
- Probabilidade ASR não é confiança calibrada. Uma palavra errada pode ter
  probabilidade alta; uma correta pode ter probabilidade baixa.
- IDs PERSON_XXX são anônimos. Com SFace, o sistema compara embeddings para manter
  IDs; sem SFace, uma troca de câmera pode fragmentar a mesma pessoa.
- Detecção HOG de corpo é básica e costuma perder pessoas sentadas. O rosto pode
  ter caixa própria sem que uma caixa de corpo seja estimada artificialmente.
- Associação voz/rosto usa correlação de abertura da boca com áudio. É uma
  heurística conservadora, **não um modelo audiovisual ASD treinado e calibrado**.
  Quando faltam evidências, visible_person permanece null.
- Tela dividida é uma recomendação candidata. Duas pessoas só aparecerem na
  imagem não é suficiente para o programa recomendar split screen.
- Emoção, humor e controvérsia são avaliações editoriais baseadas no texto quando
  há análise semântica; não diagnósticos psicológicos ou fatos verificados.
- Ruído, inteligibilidade e nível relativo da música ficam null quando não há
  evidência. Volume não é usado para inventar essas métricas.
- Nenhum vídeo final é criado. Não há envio a redes sociais nem seleção definitiva.

## 6. Historico De Validacao

Veja docs/VALIDACAO.md. Os testes automatizados usam vídeo e áudio sintéticos e
anotações explícitas. Isso valida o pipeline, sincronismo, cache e regras de
incerteza. Não substitui validar os modelos no seu computador com uma entrevista real.

Na entrega historica V4.2, a interface nativa Windows, CUDA, reconhecimento real large-v3, diarização real,
MediaPipe com vídeo real, Ollama e downloads de vídeo não foram executados em
ponta a ponta neste ambiente de entrega. As integrações foram implementadas com
APIs verificadas e diagnósticos para conferir essas etapas no seu computador.

Na V4.3, Tk/GUI e previews sinteticos foram exercitados em Windows/Python 3.11.
Consulte o README e docs/V43_REAL_BENCHMARK.md para separar replay real de modelos nao reexecutados.
Mais detalhes: docs/ARQUITETURA.md e docs/AUDIO_AVANCADO.md, a partir da raiz do projeto.
