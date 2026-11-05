# L.D.PORTO VIDEO ANALYZER

**Analyzer / Perception Engine** — aplicacao local para Windows 10/11 e Python
3.11, com analise de videos, transcricao, diarizacao, visao, OCR, curadoria
editorial e geracao de pacotes para revisao humana. Nao publica conteudo
automaticamente.

## Inicio rapido

1. Instale Python 3.11 de 64 bits e prepare FFmpeg/FFprobe.
2. Na pasta do projeto, execute `INSTALAR_WINDOWS.bat` (instala dependencias).
3. Execute `DIAGNOSTICO_WINDOWS.bat` para verificar o ambiente.
4. Execute `ABRIR_ANALYZER.bat` para abrir a interface.

Para consultar comandos sem instalar dependencias:

```powershell
.\.venv\Scripts\python.exe analyze.py --help
```

Os scripts `INSTALAR_AVANCADO_WINDOWS.bat`, `CORRIGIR_GPU_WINDOWS.bat` e
`CONFIGURAR_OLLAMA_MAXIMO_WINDOWS.bat` sao opcionais e podem modificar o
ambiente. Os modelos de IA, os videos e as credenciais ficam fora do Git.

## Documentacao

A documentacao detalhada fica centralizada pelo indice:

**[Abrir documentacao completa (.docs/README.md)](.docs/README.md)**

La estao o guia de instalacao, execucao, diagnosticos, arquitetura,
dependencias, testes, exportacao, changelogs e registros historicos.

## Desenvolvimento

A branch de trabalho e `develop`. `release` e `main` so devem receber
promocoes apos validacao. Os resultados de testes automatizados offline nao
substituem homologacao em Windows com videos e modelos reais.

Os arquivos `AGENTS.md` (instrucoes de agentes), `src/`, `scripts/`,
`config/` e `schemas/` continuam nos caminhos tecnicos originais por
compatibilidade com o codigo e as ferramentas.
