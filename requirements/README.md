# Dependency Groups

Runtime: Python 3.11.x, 64-bit. The root requirements.txt is the base installation.

- dev.txt: canonical pytest suite.
- diarization.txt: Pyannote, Torch and optional TorchCodec file decoder.
- vision.txt: face landmarks and OpenCV.
- gpu-windows.txt: NVIDIA runtime DLLs in the project venv.
- yolo.txt: optional body detector.
- ocr.txt: optional OCR wrapper; Tesseract is an external executable.
- audio-events.txt: optional audio event classifier and local checkpoint.
- demucs.txt: a separate environment, never merged into the analyzer environment.

Use the root install.py for normal installation. Optional groups remain separate;
moving the files did not upgrade or merge their dependencies.