# Biblioteca permanente — cópia aditiva comprovada

A cópia real de `input/youtube/9UCGZia2p1k/9UCGZia2p1k.mp4` foi registrada em `C:\Users\leone\Videos\LDPORTO_MEDIA_LIBRARY\9UCGZia2p1k\original.mp4`. O original legado permanece no mesmo local, com 2.663.231.970 bytes, mtime preservado e SHA256 `5d089e1825b396dafd6b5918274f3a785eb2d8be2f622497cb7d06fdd7b3b7ea` em ambas as cópias. Nenhuma remoção foi autorizada ou executada.

Comando real: `.\.venv\Scripts\python.exe docs/reports/r6_20261016/R6_2_FINAL_HANDOFF/migrate_verified_original.py`. Resultado detalhado e comandos FFprobe em `MEDIA_LIBRARY_RECEIPT.json`: container reaberto, VP9 1920×1080, áudio Opus, 5.840,094 s. A resolução real do Analyzer, em modo offline e sem permitir download, retornou a biblioteca externa. yt-dlp e modelos não foram chamados.

O resolvedor prioriza seleção explícita, referência de projeto, biblioteca, input legado e busca registrada. A seleção divergente do SHA esperado falha, sem escolher silenciosamente outra cópia. A migração verifica SHA antes e depois da cópia temporária e publica por criação exclusiva; uma interrupção após copiar o original pode ser retomada para registrar manifests ausentes. Conteúdo divergente, links e junctions são bloqueados. A validação de container é separada da simples resolução por extensão e hash.

O dossiê contém `MEDIA_REFERENCE.json`, sem duplicar o original de 97 minutos. O Curator instalado ainda recebe o caminho da mídia explicitamente; a importação real desta entrega registra a verificação desse caminho e SHA. A descoberta automática do novo MEDIA_REFERENCE pelo Curator continua pendente; nenhuma alteração de código do Curator foi realizada.

Na GUI, a verificação roda em thread de leitura, informa origem/SHA e download desnecessário, e permite escolher o arquivo mantendo o ID da URL. Download exige checkbox explícito, desmarcado por padrão; a CLI exige `--allow-download`. `--media-path` e `--media-sha256` transportam a escolha. Cobertura de interação disponível em `MEDIA_LIBRARY_MIGRATION_UI.md`; a abertura e interação manual da GUI não foi homologada nesta execução.

Rollback: selecionar o original legado preservado; as novas referências e a biblioteca não substituem nem movem o projeto ativo. A limpeza existente é dry-run por padrão e mantém mídias, output histórico, pacotes, aprovações e rastreabilidade protegidos. Não foi executada limpeza nem contabilizada economia de disco; a cópia aumenta o uso em aproximadamente 2,66 GB.
