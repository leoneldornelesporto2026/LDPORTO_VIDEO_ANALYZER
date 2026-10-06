# Active Speaker Detection — candidatos pesquisados em fontes primárias (2026-10-04)

O V4 mantém o backend heurístico atual como default e apenas prepara a interface/arquitetura para um ASD opcional. Nenhum modelo novo foi tornado obrigatório sem benchmark local.

## LR-ASD

Fonte primária: https://github.com/Junhua-Liao/LR-ASD

O repositório oficial do trabalho IJCV 2025 fornece código e pesos, reporta mAP 94.45% no AVA validation e deriva do ecossistema Light-ASD/TalkNet. É o candidato principal para benchmark local por combinar pesos publicados e arquitetura leve. Há sinais de compatibilidade Python moderna ainda a validar (existe PR público de compatibilidade Python 3.12+); portanto Python 3.11/Windows não é declarado validado neste projeto sem execução real.

## Light-ASD

Fonte primária: https://github.com/Junhua-Liao/Light-ASD

Repositório oficial CVPR 2023, código + pesos. Continua candidato leve e maduro. Há issue de 2026 pedindo esclarecimento sobre redistribuição comercial de um peso fine-tuned; por isso qualquer empacotamento de pesos deve passar por revisão de licença separada.

## TalkNet

Fonte primária: https://github.com/TaoRuijie/TalkNet-ASD

Baseline consolidado de ASD audiovisual (ACM MM 2021), útil como benchmark de qualidade e referência de implementação, mas o stack original é mais antigo e não é assumido compatível com o alvo Python 3.11/Windows sem adaptação/testes.

## C3ASD

Fonte primária: https://github.com/jisoo-o/C3ASD

Implementação oficial ECCV 2026, licença MIT, baseada em Light-ASD e focada em robustez a corrupção audiovisual. O README declara Python 3.6+ e PyTorch 1.7+, mas isso não equivale a validação específica em Python 3.11/Windows. Deve entrar como candidato de pesquisa/benchmark, não default automático.

## Decisão V4

Default permanece heurístico e conservador. Próximo gate recomendado: adapter ASD com interface comum + benchmark no mesmo conjunto local, medindo precisão de associação, cobertura, tempo, RAM/VRAM e falhas. Só promover LR-ASD/C3ASD após ganho medido no hardware real.
