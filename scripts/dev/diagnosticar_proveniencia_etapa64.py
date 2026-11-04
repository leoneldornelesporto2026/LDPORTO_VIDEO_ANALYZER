#!/usr/bin/env python3
"""Auditoria somente leitura da proveniência dos insumos da segunda curadoria.

Não modifica estado, prompts, cache nem analysis; não importa módulos do Analyzer;
não executa inferência e nunca imprime os valores de conteúdo/transcrição.
Python 3.11+. Exemplo:
 python scripts/dev/diagnosticar_proveniencia_etapa64.py --analysis analysis/video_31329be78ca4
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

SAFE_NAME = re.compile(r"^[A-Za-z0-9_\-.]{1,120}$")
IMPORTANT_INLINE = (
    "metadata", "analysis_status", "analysis_quality", "quality_gate", "run_manifest",
    "candidate_metrics", "issues", "stage_runtime", "semantic_metrics", "execution_scope",
    "editorial_shortlist", "video_understanding", "second_curation_package", "stories_manifest",
    "story_readiness", "subtitle_review", "editorial_integrity_ready",
)
IMPORTANT_SIGNED = (
    "second_curation_package.json", "CHATGPT_ANALYSIS_HANDOFF.compact.json",
    "camera_plan.json", "camera_director_timeline.json", "camera_director_debug.json",
    "camera_timeline.json", "analysis_summary.json", "master_timeline.json",
)
STAGES = ("18b_global_camera_planner", "19_camera_director", "20_handoff", "21_second_curation_handoff")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as src:
        for buf in iter(lambda: src.read(1024 * 1024), b""):
            h.update(buf)
    return h.hexdigest()


def safe_child(folder: Path, value: str) -> Path | None:
    if not isinstance(value, str) or value in (".", "..") or not SAFE_NAME.fullmatch(value):
        return None
    path = folder / value
    if path.is_symlink() or path.parent != folder:
        return None
    return path


def read_obj(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Arquivo obrigatório ausente ou link inseguro: {path.name}")
    with path.open("r", encoding="utf-8-sig") as file:
        result = json.load(file)
    if not isinstance(result, dict):
        raise ValueError(f"Objeto JSON esperado: {path.name}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", default="analysis/video_31329be78ca4", help="Pasta original da análise")
    args = parser.parse_args()
    root = Path(args.analysis).absolute()
    if not root.is_dir() or root.is_symlink():
        print("BLOQUEADO: diretório da análise ausente/inseguro.")
        return 2
    try:
        manifest = read_obj(root / "manifest.json")
        analysis = read_obj(root / "analysis.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("BLOQUEADO:", exc)
        return 2

    signed = manifest.get("artifact_checksums", {})
    if not isinstance(signed, dict):
        print("BLOQUEADO: manifesto sem artifact_checksums válido.")
        return 2
    print("=== INTEGRIDADE DOS ARTEFATOS COM RECIBO ===")
    total_ok = 0
    for name in IMPORTANT_SIGNED:
        path = safe_child(root, name)
        expected = signed.get(name)
        if path is None or not path.is_file():
            status = "ARQUIVO AUSENTE/INSEGURO"
        elif not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
            status = "SEM RECIBO HISTORICO"
        elif sha256(path).lower() == expected.lower():
            status = "HASH CONFERE NO MANIFESTO LOCAL"
            total_ok += 1
        else:
            status = "HASH DIVERGENTE"
        print(f"{name}: {status}")

    print("\n=== ANALYSIS.JSON E REFERENCIAS ===")
    input_receipt = signed.get("analysis.json")
    if input_receipt is None:
        print("analysis.json: SEM CHECKSUM HISTORICO NO MANIFESTO")
    elif isinstance(input_receipt, str) and input_receipt.lower() == sha256(root / "analysis.json"):
        print("analysis.json: CHECKSUM CONFERE NO MANIFESTO LOCAL (sem provar assinatura independente)")
    else:
        print("analysis.json: HASH INVALIDO/DIVERGENTE")

    refs = analysis.get("collection_refs", {})
    if not isinstance(refs, dict):
        print("collection_refs: FORMATO INVALIDO")
        refs = {}
    ok, missing, invalid = 0, 0, 0
    for key, ref in refs.items():
        if not isinstance(ref, dict):
            invalid += 1
            continue
        name = ref.get("path")
        path = safe_child(root, name)
        if path is None:
            invalid += 1
        elif not path.is_file():
            missing += 1
        else:
            expected_ref = ref.get("sha256")
            expected_manifest = signed.get(name)
            if (isinstance(expected_ref, str) and isinstance(expected_manifest, str)
                    and re.fullmatch(r"[0-9a-fA-F]{64}", expected_ref)
                    and expected_ref.lower() == expected_manifest.lower()
                    and sha256(path).lower() == expected_ref.lower()):
                ok += 1
            else:
                invalid += 1
    print(f"collection_refs com dupla consistencia local: {ok}; ausentes: {missing}; divergentes/inseguros: {invalid}")
    print("NOTA: os hashes do proprio diretorio nao constituem prova independente de origem.")

    print("\n=== CAMPOS INLINE RELEVANTES (NOMES, NAO VALORES) ===")
    for key in IMPORTANT_INLINE:
        if key not in analysis:
            continue
        referenced = key in refs and isinstance(refs[key], dict)
        state = "REFERENCIADO EM COLECAO" if referenced else "INLINE: ANALYSIS.JSON SEM RECIBO INDEPENDENTE"
        print(f"{key}: {state}")
    others = [key for key in analysis if key not in refs and key not in IMPORTANT_INLINE
              and not key.endswith("_ref") and key not in ("collection_refs", "collection_storage", "schema_version")]
    print(f"Outras chaves inline nao listadas (sem expor nomes/valores): {len(others)}")

    print("\n=== ETAPAS REPORTADAS PELO ANALYSIS.JSON ===")
    stages = analysis.get("run_manifest", {}).get("stage_status", {}) if isinstance(analysis.get("run_manifest"), dict) else {}
    for stage in STAGES:
        data = stages.get(stage, {}) if isinstance(stages, dict) else {}
        status = data.get("status") if isinstance(data, dict) else None
        print(f"{stage}: status relatado={status if status in ('ok','partial','failed','skipped') else 'desconhecido'}")
    print("STATUS DO PLANO: NAO ELEGIVEL PARA APPLY sem evidencias adicionais.")
    print("AUDITORIA SOMENTE LEITURA CONCLUIDA — NENHUM ARQUIVO MODIFICADO")
    return 0 if total_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
