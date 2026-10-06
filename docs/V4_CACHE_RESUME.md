# Cache e resume V4

A visão longa possui checkpoints internos atômicos por chunk temporal. Cada chunk registra intervalo, hashes de input/config, versão de implementação/schema/backend, checksum, observações e estado mínimo do tracker necessário para retomada.

Um chunk incompleto, checksum inválido, hash/config incompatível ou versão diferente é rejeitado. Na retomada, apenas a sequência contígua íntegra é reutilizada; observações não são duplicadas.

Alterações no Camera Planner/Director não invalidam ASR/visão. Overrides são não destrutivos e possuem mapa de descendentes: por exemplo, alterar `speaker_person_mapping` invalida active speaker → Planner → Director → handoff, sem reexecutar transcrição.
