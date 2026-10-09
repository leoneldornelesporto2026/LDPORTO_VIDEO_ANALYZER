# L.D.PORTO AUTOPILOT — 42 microetapas em uma única pasta

## O que este pacote contém

- **orquestrador.py** na raiz do projeto (um único arquivo Python de automação).
- **automacao/prompts/ETAPA_01.txt ... ETAPA_42.txt**: tarefas em ordem, retiradas do plano original.
- **automacao/MAPA_ETAPAS.json**: índice e critérios de cada tarefa.
- **automacao/evidencias/**: dois ZIPs da MESMA execução antiga João Gordo (somente leitura).
- **automacao/referencias_metodologia/**: auditoria e prompts D01–D12 para consulta, não executados automaticamente.
- **automacao/execucao/**: criado pelo script no Windows para backups, JSON de estado, logs e checkpoints.

## ATENÇÃO: como instalar em sua pasta REAL do VS Code

Se sua pasta `LDPORTO_VIDEO_ANALYZER` já tem alterações mais novas, **não a substitua pelo ZIP completo**.
Extraia APENAS o `LDPORTO_CODEX_AUTOPILOT_OVERLAY.zip` sobre a raiz do seu projeto atual.
O overlay acrescenta `orquestrador.py`, `AGENTS.md`, `automacao/`, um teste novo e a correção da allowlist em `src/tests/test_v43_runtime.py`. Antes de extrair, confira se esse teste não recebeu mudanças locais próprias; caso tenha recebido, integre somente as duas entradas novas da allowlist. As linhas de `.gitignore` estão em `automacao/GITIGNORE_TRECHO.txt`; não sobrescreva seu `.gitignore`.
O orquestrador NÃO copia o projeto para outro workspace. O Codex edita os arquivos da pasta em que você já trabalha.

## Antes de começar

```powershell
cd "C:\Users\leone\Documentos\Meus Projetos\LDPORTO_VIDEO_ANALYZER"
.venv\Scripts\python.exe orquestrador.py --doctor
.venv\Scripts\python.exe orquestrador.py --init
.venv\Scripts\python.exe orquestrador.py --status
.venv\Scripts\python.exe orquestrador.py --prepare
```

- `--doctor`: verifica Python, Codex CLI, pytest e prompts, **sem tokens de IA**.
- `--init`: executa `python -m pytest -q` na base, cria `ETAPA_00_BASELINE.zip` + manifest/hashes se os testes passarem e nunca sobrescreve estado preexistente.
- `--prepare`: grava o texto do próximo prompt, sem executá-lo.

## Execução recomendada

```powershell
.venv\Scripts\python.exe orquestrador.py --once
.venv\Scripts\python.exe orquestrador.py --status
.venv\Scripts\python.exe orquestrador.py --batch 6
```

Após validar o primeiro lote, para tentar as 42 etapas automaticamente:

```powershell
.venv\Scripts\python.exe orquestrador.py --auto
```

O script PARA se Codex falhar, atingir limites de uso, faltar checkpoint, mudar o próprio orquestrador, falhar sintaxe ou `python -m pytest -q`. Em caso de falha os arquivos parciais NÃO são perdidos:

```powershell
.venv\Scripts\python.exe orquestrador.py --status
.venv\Scripts\python.exe orquestrador.py --retry
```

Em `--retry`, o agente retoma a **mesma etapa** e usa as alterações parciais; não volta à etapa 1.

## Checkpoints e proteção

- `automacao/execucao/estado.json` registra etapa, resumo, hashes e caminhos dos ZIPs.
- `automacao/execucao/snapshots/ANTES_ETAPA_NN.zip`: cópia do código ANTES do agente.
- `automacao/execucao/snapshots/LDPORTO_STAGE_NN.zip`: cópia APROVADA DEPOIS da regressão.
- `automacao/execucao/snapshots/PARCIAL_ETAPA_NN_*.zip`: código recuperável após erro.
- `automacao/execucao/checkpoints/CHECKPOINT_ETAPA_NN.md`: conclusões e testes escritos pelo agente.
- `automacao/execucao/logs/`: saída do Codex e do pytest para diagnóstico.
- `.venv`, mídia, modelos, análises, ZIPs de evidências e tokens NÃO entram nos snapshots.

Se você alterar o código manualmente entre as etapas, a próxima execução BLOQUEIA por drift. Após revisar a mudança, execute uma etapa com `--accept-drift` para registrá-la como nova baseline antes de prosseguir. Não use em alterações suspeitas.

Se cair energia e sobrar `automacao/execucao/orquestrador.lock`, confirme no Gerenciador de Tarefas que **não há outro orquestrador ou Codex atuando**, então use `--unlock --confirm-unlock`. Pode ser necessário `--retry` em seguida.

## Segurança e limitações

- Cada etapa roda em modo `workspace-write`, sem bypass de sandbox, com aprovação do CLI desabilitada. As proteções de sandbox no Windows devem ser confirmadas no ambiente local.
- O login do ChatGPT não garante franquia; o script NÃO compra créditos e não contorna limites.
- Testes pytest e sintaxe verificam regressão técnica, **não** comprovam que cortes, humor, câmera e legendas têm boa qualidade humana.
- Testes com vídeo real, NVIDIA, Ollama e o Curator externo precisam acontecer no seu próprio computador.
- Evite executar junto com um Codex interativo editando os mesmos arquivos. Não edite enquanto `--auto` estiver ativo.
- O orquestrador não faz commits nem `git reset`, e nunca elimina automaticamente mudanças parciais.
