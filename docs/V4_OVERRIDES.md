# Manual overrides V4

Overrides automáticos não são sobrescritos. `review_overrides.py` mantém documento separado, com `origin=manual`, timestamp, intervalo, valor e versão.

Tipos suportados no backend: label de pessoa, speaker↔person mapping, focus, layout, forbid split, forbid zoom, max zoom, force source, approve/reject candidate e candidate boundary. O backend implementa undo, redo e reset e calcula os módulos descendentes invalidados.

A GUI atual não recebeu nesta execução um editor visual completo de todos esses overrides. O contrato/backend está preparado; integrar todos os controles na GUI permanece `IMPLEMENTED + LOCAL/GUI VALIDATION REQUIRED`.
