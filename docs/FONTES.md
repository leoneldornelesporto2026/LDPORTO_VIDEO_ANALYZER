# Fontes primárias consultadas

Consulta de APIs e dependências feita em 2 de outubro de 2026.
Não foram usadas páginas de terceiros como autoridade para integrar as APIs.

| Componente | Documentação oficial |
|---|---|
| faster-whisper | https://github.com/SYSTRAN/faster-whisper |
| community-1 local e condições de acesso | https://huggingface.co/pyannote/speaker-diarization-community-1 |
| pyannote.audio 4 | https://github.com/pyannote/pyannote-audio |
| pyannote-core e NumPy 2 | https://github.com/pyannote/pyannote-core/blob/develop/pyproject.toml |
| yt-dlp e runtimes JS | https://github.com/yt-dlp/yt-dlp |
| PySceneDetect | https://www.scenedetect.com/docs/latest/api.html |
| MediaPipe FaceLandmarker | https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python |
| YuNet e SFace | https://docs.opencv.org/doc/doxygen/html/d0/dd4/tutorial_dnn_face.html |
| Modelos OpenCV Zoo | https://github.com/opencv/opencv_zoo |
| Ollama Chat API / JSON Schema | https://docs.ollama.com/api/chat |
| Ollama Structured Outputs | https://docs.ollama.com/capabilities/structured-outputs |
| Ollama Context Length | https://docs.ollama.com/context-length |
| Ollama FAQ / GPU / keep_alive | https://docs.ollama.com/faq |
| Qwen3 no Ollama | https://ollama.com/library/qwen3 |
| Demucs — integração opcional | https://github.com/facebookresearch/demucs |
| PANNs | https://github.com/qiuqiangkong/panns_inference |
| FFmpeg | https://ffmpeg.org/ffmpeg.html |

As fontes sustentam as APIs e condições dos componentes. Não comprovam a qualidade
do pacote com qualquer vídeo específico. Métricas de qualidade precisam de dados
reais e revisão própria.

Os pesos/modelos são externos e seguem suas licenças. O pacote não os redistribui.
O código de integração YOLO é opcional; consulte a licença do projeto Ultralytics
antes de incorporar esse backend a um produto comercial.
