import argparse
from pathlib import Path
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import json
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "config.yaml"


def find_ollama():
    found = shutil.which("ollama")
    if found:
        return found
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "Ollama" / "ollama.exe",
        ]
        for p in candidates:
            if p.is_file():
                return str(p)
    return None


def max_vram_mib():
    exe = shutil.which("nvidia-smi")
    if not exe:
        return 0
    try:
        cp = subprocess.run([exe, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                            capture_output=True, text=True, check=True, timeout=5)
        vals = [int(float(x.strip())) for x in cp.stdout.splitlines() if x.strip()]
        return max(vals, default=0)
    except Exception:
        return 0


def choose_model(explicit=None):
    if explicit:
        return explicit
    vram = max_vram_mib()
    if vram >= 22000:
        return "qwen3:30b"
    if vram >= 12000:
        return "qwen3:14b"
    return "qwen3:8b"


def service_up():
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/version", timeout=1.5):
            return True
    except Exception:
        return False


def start_service(exe):
    if service_up():
        return
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, start_new_session=os.name != "nt")
    for _ in range(12):
        if service_up():
            return
        time.sleep(0.5)
    raise SystemExit("Ollama foi encontrado, mas o servidor local não iniciou em 127.0.0.1:11434.")



def preload_model(model):
    payload = {
        "model": model, "prompt": "", "stream": False, "keep_alive": "30m",
        "options": {"num_ctx": 32768, "num_predict": 1, "temperature": 0},
    }
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as response:
        json.load(response)


def update_config(model):
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    sem = cfg.setdefault("semantic_analysis", {})
    sem.update({
        "enabled": True,
        "backend": "ollama",
        "ollama_url": "http://127.0.0.1:11434",
        "model": model,
        "profile": "max",
        "timeout_seconds": 600,
        "keep_alive": "30m",
        "global_review": True,
    })
    CONFIG.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="Força um modelo, ex.: qwen3:14b")
    args = ap.parse_args()
    exe = find_ollama()
    if not exe:
        raise SystemExit("Ollama não foi encontrado. Instale via winget ou https://ollama.com/download e execute novamente.")
    model = choose_model(args.model)
    print(f"Modelo selecionado para esta máquina: {model}", flush=True)
    start_service(exe)
    subprocess.run([exe, "pull", model], check=True)
    # Preload with the same context used by profile=max so `ollama ps` is meaningful.
    preload_model(model)
    update_config(model)
    print("\nOllama configurado em modo local + profile=max.")
    print(f"Config atualizado para: {model}")
    subprocess.run([exe, "ps"], check=False)


if __name__ == "__main__":
    main()
