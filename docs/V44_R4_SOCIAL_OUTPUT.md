# V4.4 R4-SOCIAL

## Escopo

Revisão downstream para preparar Stories/Reels/Shorts sem alterar o motor pesado da V4.4 R3.

## Stories

`Stories` = conjunto de vários momentos independentes do vídeo inteiro. O seletor usa:

- janela de 15–60 s por padrão;
- exclusão comercial;
- score editorial + hook + emoção/humor/curiosidade/story/Q&A + viabilidade visual;
- limite por tópico;
- espaçamento temporal;
- limite de Stories por janela de 10 minutos;
- diversidade de categorias.

O modo opcional `Story Compilation` permanece explicitamente desabilitado; ele é diferente do Story Set.

## Formatos e estilo

Proporções: 9:16, 4:5, 1:1 e 16:9.

A GUI ganhou seleção de:

- proporção;
- preset de legenda;
- modo de conteúdo;
- número máximo de Stories;
- fonte;
- escala;
- cor principal;
- cor de destaque.

Essas escolhas são passadas por CLI/config e não invalidam etapas pesadas.

## Legenda segura

O plano de legenda registra `avoid_faces`, `avoid_mouth`, `avoid_broadcast_graphics`, posição preferencial, fallbacks e necessidade de reposicionamento dinâmico. Lower-thirds/tickers persistentes empurram a legenda para zona superior; banners superiores preferem zona inferior. A verificação final continua responsabilidade do Curator após crop/câmera.

## Títulos

As sugestões priorizam copy editorial já grounded pelo Analyzer, pergunta literal e trecho literal. Copy não literal continua marcada como `requires_review`; o Analyzer não transforma sugestão em fato.

## Handoff

Novos arquivos no output e no pacote de segunda curadoria:

- `stories_manifest.json`
- `stories_candidates.json`
- `title_suggestions.json`
- `caption_style_recommendations.json`
- `social_render_profiles.json`
- `social/*` dentro do `SECOND_CURATION_*`.

## Validação

- 414 testes passaram;
- 2 skips ambientais já conhecidos (display Tk/.git em pacote);
- `py_compile` passou;
- core package expõe o contrato social e mantém integridade.
