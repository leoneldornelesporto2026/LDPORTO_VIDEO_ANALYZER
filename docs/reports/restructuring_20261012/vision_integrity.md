# Visão, active speaker e decisões de câmera — 2026-10-12

## Escopo e evidência

Auditoria e correções feitas nos fontes atuais após autorização da regressão inicial pelo agente principal. Não houve execução de análise real, carregamento de pesos reais, utilização de GPU, download, instalação ou mudança de política editorial. Fixtures novos usam apenas dados sintéticos e marcadores de arquivo, sem reivindicar acurácia em pessoas ou vídeos reais.

O backend YOLO existente exige checkpoint local `.pt`, tarefa `detect` e classe 0 `person`. HOG continua sendo fallback identificado. A implementação existente já distingue identidade global de fala contemporânea, exige evidência audiovisual local, verifica lag e cortes, abstém em sobreposição e mantém `active_person=null` quando necessário. O Camera Director já mantém segurança de crop, estabilização, auditoria por janela e bloqueios de Smart Zoom; esses mecanismos foram preservados.

## Correções

- `src/ldporto/active_speaker.py`: duas vozes simultâneas associadas à mesma pessoa já perdiam o mapping estável, porém o resumo permanecia `PROVISIONAL` e a afinidade mantinha confiança aceita. A colisão agora gera `UNRESOLVED`, retira a confiança aceita da afinidade, preserva a causa específica nos intervalos e participa da métrica de conflito. O suporte medido e suas referências continuam disponíveis. Labels de diarização sequenciais ainda podem compartilhar uma pessoa sem criar conflito.
- `src/ldporto/vision.py`: o relatório local de YOLO agora informa configuração e caminho resolvido mesmo quando o arquivo falta, formato/tarefa/classe esperados e política sem download/instalação. Motivos específicos distinguem arquivo ausente, formato incompatível, arquivo vazio, link/reparse point, tarefa incompatível e classe de pessoa ausente. Os motivos antigos de fallback e diagnóstico continuam válidos para os consumidores existentes.
- `src/ldporto/camera_evidence.py` e `src/ldporto/camera_director.py`: cada entrada de `focus_window_audit` recebe `candidate_delivery`, comparando proposta pontuada e enquadramento efetivamente recomendado após todos os gates. Registra resultado, pessoa solicitada, supressão aplicada, motivos e semântica heurística do score. Agregados contabilizam resultados e motivos/segundos de supressão por janela, inclusive quando a timeline é compactada. Um crop rejeitado ao final registra `FULL_FRAME` como candidato entregue. Esses dados descrevem recomendação de câmera, não renderização ou homologação de preview.
- `src/tests/test_vision_decision_integrity.py`: 12 regressões sintéticas exercitam colisão, ausência de colisão sequencial, diagnósticos de YOLO sem carregar pesos, decisão aceita, fonte preservada, challenger breve suprimido, substituição por segurança temporal e coerência da auditoria com os agregados.

## Comandos e resultados reais

Primeira execução dos novos testes:

```powershell
.venv/Scripts/python.exe -m pytest -q src/tests/test_vision_decision_integrity.py
```

Resultado: **2 failed, 10 passed in 0.52s**, exit code 1. As falhas eram nos fixtures/asserts novos: comparação exata de fração em ponto flutuante e perda facial ocorrendo antes de expirar o hold inicial. Corrigidos com comparação aproximada e perda facial sintética posterior ao hold, sem alterar políticas de produção.

Reexecução do mesmo comando: **12 passed in 1.10s**, exit code 0.

Regressão focada dos contratos existentes e das novas correções:

```powershell
.venv/Scripts/python.exe -m pytest -q src/tests/test_vision_decision_integrity.py src/tests/test_stage57_local_yolo.py src/tests/test_s5_speaker_person_active.py src/tests/test_stage28_voice_person_evidence.py src/tests/test_stage29_active_speaker_consensus.py src/tests/test_stage31_focus_audit.py src/tests/test_stage32_safe_camera.py src/tests/test_camera_director.py src/tests/test_stage30_shot_continuity.py
```

Resultado: **155 passed in 1.50s**, exit code 0. Somente regressões focadas; nenhum pipeline completo.

```powershell
git diff --check -- src/ldporto/active_speaker.py src/ldporto/vision.py src/ldporto/camera_evidence.py src/ldporto/camera_director.py src/tests/test_vision_decision_integrity.py
```

Resultado: sem erro de whitespace; Git emite avisos de conversão futura LF → CRLF conforme configuração local.

## Homologação pendente

YOLO com checkpoint real, dispositivo NVIDIA, recall de pessoas sentadas/ocultas, reentrada de pessoas e sincronização audiovisual em vídeos humanos permanecem pendentes de avaliação controlada no Windows. Não foi implementado nem homologado novo backend neural ASD. Zero foco/zoom pode ser uma preservação correta da fonte em material curto, de baixa resolução ou com evidência insuficiente. A nova telemetria permite distinguir essas causas sem forçar resultados.
