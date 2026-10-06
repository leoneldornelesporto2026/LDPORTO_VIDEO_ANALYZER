#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ldporto.gpu_runtime import configure_windows_nvidia_runtime, ctranslate2_cuda_info


def make_silence(path: Path, seconds=1.5, rate=16000):
    frames = b"\x00\x00" * int(seconds * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--compute", default="int8_float16")
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args()

    runtime = configure_windows_nvidia_runtime()
    info = ctranslate2_cuda_info()
    report = {"runtime": runtime, "ctranslate2": info, "smoke_test": None}
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if (info.get("device_count") or 0) < 1:
        print("\nERRO: CTranslate2 nao detectou GPU CUDA.", file=sys.stderr)
        return 2
    if args.check_only:
        return 0

    try:
        from faster_whisper import WhisperModel
        print(f"\n[GPU TEST] Carregando {args.model} em cuda/{args.compute}...")
        model = WhisperModel(
            args.model,
            device="cuda",
            compute_type=args.compute,
            download_root=str(ROOT / "models" / "whisper"),
        )
        with tempfile.TemporaryDirectory(prefix="ldporto_gpu_") as td:
            wav = Path(td) / "silence.wav"
            make_silence(wav)
            segments, info_asr = model.transcribe(
                str(wav), language="pt", beam_size=1, word_timestamps=True,
                vad_filter=False, condition_on_previous_text=False, temperature=0,
            )
            list(segments)
        print("[GPU TEST] OK - inferencia faster-whisper executada em CUDA.")
        return 0
    except Exception as exc:
        print(f"\n[GPU TEST] FALHOU: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Execute novamente CORRIGIR_GPU_WINDOWS.bat ou confira as DLLs listadas acima.", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
