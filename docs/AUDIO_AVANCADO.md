# Áudio, instrumental e revisão

## Padrão seguro de análise

O original permanece intocado no arquivo de entrada.
São criadas cópias:

| Derivado | Função |
|---|---|
| audio/original.wav | Referência PCM com sample rate/canais originais e sincronismo de vídeo |
| audio/original_mono_16k.wav | Diarização, RMS/active speaker e ASR original |
| audio/speech_clean.wav | ASR com high-pass leve e normalização conservadora |
| audio/speech_isolated.wav | Opcional: trilha isolada externa sincronizada |

Denoise está desativado por padrão. Para ativar redução espectral moderada:

    audio:
      denoise: true

Não há redução automática de reverberação agressiva. O objetivo é preservar
consoantes, finais de palavras e timbre suficiente para reconhecer o texto.

## Voz isolada fornecida por você

É possível gerar a trilha fora do Analyzer e apontar:

    audio:
      isolated_file: "C:/Audio/entrevista_vocals.wav"
      isolated_offset_seconds: 0.0

A trilha precisa representar o vídeo inteiro, na mesma velocidade e duração.
A checagem de duração não prova ausência de atraso interno: ouça um ponto no início,
no meio e no fim. Não use uma faixa encurtada pela remoção de silêncios.

O ASR de revisão consulta isolated apenas em regiões duvidosas. O original continua
na diarização, overlap e correlação audiovisual.

## Demucs em regiões difíceis

Esta integração é opcional e **não é ligada por padrão**. O projeto upstream
foi arquivado; a separação pode introduzir artefatos e destruir consoantes.

Crie outro ambiente Python 3.11:

    py -3.11 -m venv venv-demucs
    .\venv-demucs\Scripts\python.exe -m pip install -r requirements/demucs.txt

No YAML:

    audio:
      separation: "demucs"
      demucs_python: "C:/LDPORTO_VIDEO_ANALYZER/venv-demucs/Scripts/python.exe"

O programa chama Demucs somente em regiões de baixa confiança selecionadas para
revisão. A separação é feita em trechos pequenos com segmentos de 7 segundos,
evitando separar o vídeo inteiro sem necessidade.

Não há criação de uma trilha isolada completa quando se usa Demucs por região.
As faixas dessas regiões ficam em cache/review/. A faixa completa só existe
quando isolated_file foi fornecido.

Use --force após ativar/configurar Demucs. Offline não dispara essa separação,
pois a primeira execução do backend pode tentar baixar pesos.

## Detecção de música e sons

O extra PANNs pode classificar speech, music, laughter, applause e noise em janelas
de áudio original. Necessita checkpoint Cnn14 local:

    audio_events:
      enabled: true
      checkpoint: "C:/Modelos/Cnn14_mAP=0.431.pth"

A API e instruções oficiais para o checkpoint estão em:
https://github.com/qiuqiangkong/panns_inference

Esses são scores de classificação por janela, não limites exatos de cada risada,
nem uma medição de quantos dB a música está abaixo da voz.

**Nesta versão, a revisão/separação é acionada pela baixa confiança ASR e pela
configuração do usuário. Não há gatilho automático de Demucs baseado exclusivamente
na estimativa PANNs de música**, e não há estimador calibrado de relação voz/música.
Quando indisponível, music_under_speech permanece null.

## Consenso

Transcription_alternatives guarda fonte, trecho original selecionado e hipóteses
de revisão com timestamps. replacement_applied é false.

Divergência entre duas fontes exige revisão. O sistema não decide que a hipótese
mais bonita ou formal é correta. Não há comparação semântica que reescreva fala.
