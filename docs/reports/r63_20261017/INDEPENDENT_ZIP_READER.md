# Leitor independente do ZIP compacto R6.3

API: `ldporto.compact_handoff_reader.inspect_compact_handoff(path, reconstruct=True)`.

O leitor não importa o exportador, os resolvedores de mídia ou a análise local. Abre somente o ZIP indicado, sem extrair arquivos e sem modelos. Retorna `status=valid/failed`, erros, contagens e, quando válido, a reconstrução dos índices de cenas/Reels/Stories, transcrição, frames, trajetórias, câmera, áreas protegidas, cobertura e limitações. `reconstruct=False` retorna um relatório pequeno, exercitando as mesmas validações e a reconstrução internamente.

As validações incluem limites de arquivo/container, paths POSIX relativos únicos, ausência de links, schema R6.3, SHA256 completo da fonte, revisão, gates humanos, cobertura exata de FILE_INDEX e checksums, hashes internos, dimensões reais das imagens, IDs resolvidos, intervalos originais/relativos, bbox normalizada, keyframes ordenados, separação por shot e inventários declarados. A identidade não é deduzida do nome do ZIP ou de prefixo de hash; `video_id=null` permanece desconhecido.

Geometria pode estar inline ou em `storage=indexed_shards`. No formato particionado, o leitor confirma bytes/SHA/IDs de cada shard, igualdade exata de `trajectory_index`, ausência de trajetória duplicada e correspondência entre os IDs da peça e `trajectory_shard_refs`. Cada shard é lido no próprio ZIP. Os registros reconstruídos são compartilhados por referência em memória para não multiplicar coordenadas em Reels/Stories sobrepostos. A representação compacta pode ser consultada por peça sem abrir um JSON global com todas as coordenadas.

Convenções de coordenadas são declaradas como `coordinate_contract.bbox=normalized_source_xywh`. Essa declaração textual é distinta de uma caixa observada; uma string usada como bbox de keyframe continua inválida. Referências JSON com fragmento são verificadas, inclusive `arquivo.json#campo` e JSON Pointer.

Teste focado real executado:

```powershell
./.venv/Scripts/python.exe -m pytest src/tests/test_r63_compact_handoff_reader.py -q --junitxml=docs/reports/r63_20261017/reader_focused.junit.xml
```

Resultado: **44 PASS**, zero falhas, 0,79 s no resultado exibido pelo pytest. O JUnit registra seu próprio tempo da suíte. As fixtures são construídas sem chamar o producer. Há testes adversariais de hashes, paths, fontes divergentes, arquivos ausentes, contagens, texto canônico, referências, crop, trajetória cruzando shot, imagem inválida, gates e shards. O teste independente proíbe `Path.read_text` e `Path.read_bytes` de buscar dados locais depois de construir o ZIP.

Esses testes sintéticos não substituem a abertura do pacote real, a inspeção das imagens/PDF ou a revisão editorial humana. O resultado do ZIP real será registrado separadamente.
