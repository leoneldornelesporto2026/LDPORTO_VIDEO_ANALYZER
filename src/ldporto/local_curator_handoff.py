"""Validated and atomic Analyzer -> local Video Curator inbox handoff.

An evidence transfer, NOT an R57 import, render, editorial approval or publish.
Reuses the official build_core_package ZIP and validate_core_package contracts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import zipfile

from .core import file_hash
from .paths import PROJECT_ROOT
from .second_curation_export import validate_core_package

CONTRACT_VERSION = "1.0"
HANDOFF_NAME = "ANALYZER_TO_CURATOR_HANDOFF.json"
GUIDE_NAME = "README_HANDOFF.md"
EVIDENCE_INDEX_NAME = "VIDEO_EVIDENCE_INDEX.json"
DELIVERY_SUCCESS = "DELIVERED"
DELIVERY_BLOCKED = "DELIVERY_BLOCKED"
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{x}" for x in range(1, 10)),
                     *(f"LPT{x}" for x in range(1, 10))}


def curator_directory(config=None, override=None):
    """Explicit override > config > environment > sibling discovery."""
    config = config or {}
    choice = override or config.get("curator_delivery_root") or os.environ.get("LDPORTO_VIDEO_CURATOR_ROOT")
    return Path(choice).expanduser() if choice else PROJECT_ROOT.parent / "LDPORTO_VIDEO_CURATOR"


def _component(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", value):
        raise ValueError("unsafe_" + label)
    if value.endswith((".", " ")) or ".." in value or value.split(".")[0].upper() in _WINDOWS_RESERVED:
        raise ValueError("unsafe_" + label)
    return value


def _not_linked(path):
    """Deny junctions, symlinks and reparse points in the destination ancestry."""
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if not part.exists() and not part.is_symlink():
            continue
        info = part.lstat()
        if part.is_symlink() or (
            getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)
        ):
            raise ValueError("unsafe_destination_reparse_point")


def _read_member(archive, name):
    if name not in archive.namelist():
        return None
    return json.loads(archive.read(name))


def _facts(package):
    """Read only the canonical, already validated original ZIP. No extraction."""
    with zipfile.ZipFile(package) as archive:
        manifest = _read_member(archive, "SECOND_CURATION_MANIFEST.json")
        index = _read_member(archive, "CURATION_INDEX.json")
        brief = _read_member(archive, "SECOND_CURATOR_BRIEF.json")
        metadata = _read_member(archive, "source/metadata.json")
        catalog = _read_member(archive, "editorial/candidate_catalog.json")
        social = _read_member(archive, "social/stories_manifest.json") or {}
        caption = _read_member(archive, "subtitles/caption_preflight_r6.json")
        files = {x.get("path"): x for x in manifest.get("files", [])
                 if isinstance(x, dict) and isinstance(x.get("path"), str)}
        available = []
        for name in (
            "SECOND_CURATION_MANIFEST.json", "HANDOFF_MASTER.json", "CURATION_INDEX.json",
            "SECOND_CURATOR_BRIEF.json", "source/metadata.json", "transcript/transcript.txt",
            "transcript/transcript.srt", "transcript/relevant_segments.jsonl",
            "transcript/relevant_words.jsonl", "editorial/candidate_catalog.json",
            "social/stories_manifest.json", "subtitles/caption_preflight_r6.json",
            "camera/shared_camera_handoff.json", "camera/candidate_camera_plans.json",
            "VISUAL_SCENES_INDEX.json",
        ):
            if name in archive.namelist():
                row = files.get(name) or {}
                available.append({"path": name, "sha256": row.get("sha256"),
                                  "bytes": row.get("bytes")})
    if not all(isinstance(x, dict) for x in (manifest, index, brief, metadata, catalog)):
        raise ValueError("missing_canonical_second_curation_facts")
    if not isinstance(catalog.get("candidates"), list) or not isinstance(social.get("stories", []), list):
        raise ValueError("invalid_editorial_counts")
    if not isinstance(manifest.get("run_id"), str) or not manifest.get("run_id"):
        raise ValueError("run_id_not_recorded")
    if manifest.get("source_hash") != metadata.get("sha256"):
        raise ValueError("source_hash_manifest_disagreement")
    if index.get("candidate_count") != len(catalog["candidates"]):
        raise ValueError("candidate_count_manifest_disagreement")
    if manifest.get("preview_approved") is True or manifest.get("publication_ready") is True:
        raise ValueError("source_package_claims_approval")
    original_id = brief.get("source_id")
    if not original_id:
        original_id = (metadata.get("source") or {}).get("id")
    identity_kind = "canonical_source_id"
    if not original_id:
        digest = metadata.get("sha256") or ""
        if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError("missing_source_identity")
        original_id = digest[:12]
        identity_kind = "source_sha256_prefix"
    # Preserve raw values inside the receipt; refuse filesystem-unsafe IDs.
    video_id = _component(str(original_id), "video_id")
    run_id = _component(manifest["run_id"], "run_id")
    status = manifest.get("analysis_status")
    if status not in ("complete", "partial"):
        raise ValueError("analysis_not_deliverable:" + str(status))
    workflow = manifest.get("workflow") or {}
    state = "READY_FOR_REVIEW" if status == "complete" and workflow.get("review_ready") is True else "PARTIAL"
    reasons = manifest.get("readiness_reasons") or {}
    pending = {
        "transcription": reasons.get("transcript_ready"),
        "camera": reasons.get("camera_ready"),
        "audio": None,
        "captions": (caption or {}).get("status") if isinstance(caption, dict) else None,
        "preview": reasons.get("preview_ready"),
        "warnings": manifest.get("warnings") or [],
    }
    video_source = metadata.get("source") or {}
    source_index = index.get("source") or {}
    return {
        "video_id": video_id, "video_id_origin": identity_kind, "run_id": run_id,
        "analysis_state": state, "original_analysis_status": status,
        "source_sha256": metadata.get("sha256"), "source_video": {
            "id": str(original_id), "title": source_index.get("title") or video_source.get("title"),
            "url": source_index.get("url") or video_source.get("url"),
            "duration_seconds": metadata.get("duration"),
            "width": metadata.get("width"), "height": metadata.get("height"),
            "fps": metadata.get("fps"), "codec": metadata.get("codec"),
        },
        "analyzer_version": manifest.get("analyzer_version"),
        "analyzer_build": manifest.get("analyzer_build"),
        "reel_candidate_count": len(catalog["candidates"]),
        "story_candidate_count": len(social.get("stories", [])),
        "available_internal_references": available,
        "readiness": manifest.get("readiness") or {},
        "pending_reviews": pending,
    }


def _evidence_index(package, facts, zip_sha):
    """Full, bounded inventory of the ORIGINAL exported ZIP (no media extracted).

    The canonical Analyzer validator runs before this function. We separately
    enumerate all members to make every included piece of evidence discoverable
    by the independent Curator or a human reviewer.
    """
    artifacts = []
    with zipfile.ZipFile(package) as archive:
        infos = archive.infolist()
        if len(infos) > 5000 or sum(info.file_size for info in infos) > 256 * 1024 ** 2:
            raise ValueError("evidence_index_size_budget_exceeded")
        for info in sorted(infos, key=lambda row: row.filename):
            if info.is_dir():
                continue
            name = info.filename
            if (not name or name.startswith("/") or "\\" in name or ":" in name
                or ".." in name.split("/")):
                raise ValueError("unsafe_evidence_index_member")
            digest = sha256()
            with archive.open(info, "r") as stream:
                for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                    digest.update(chunk)
            artifacts.append({"path": name, "bytes": info.file_size,
                              "sha256": digest.hexdigest(),
                              "category": name.split("/", 1)[0] if "/" in name else "root"})
    available = {row["path"] for row in artifacts}
    optional = (
        "HANDOFF_MASTER.json", "transcript/transcript.txt",
        "transcript/transcript.srt", "transcript/relevant_segments.jsonl",
        "transcript/relevant_words.jsonl", "editorial/candidate_catalog.json",
        "social/stories_manifest.json", "camera/shared_camera_handoff.json",
        "camera/candidate_camera_plans.json", "audio/sound_events.json",
        "subtitles/caption_preflight_r6.json",
    )
    return {
        "schema_version": "1.0", "kind": "ANALYZER_NATIVE_SECOND_CURATION_EVIDENCE",
        "scope": "ALL_FILES_IN_VALIDATED_SOURCE_ZIP",
        "video_id": facts["video_id"], "run_id": facts["run_id"],
        "source_sha256": facts["source_sha256"],
        "source_video": facts["source_video"],
        "analysis_state": facts["analysis_state"],
        "zip_sha256": zip_sha,
        "artifact_count": len(artifacts),
        "categories": sorted({row["category"] for row in artifacts}),
        "missing_review_references": [name for name in optional if name not in available],
        "artifacts": artifacts,
        "video_file_included": False,
        "human_approval": False, "publication_ready": False,
        "curator_import_status": "CURATOR_IMPORT_PENDING",
    }


def _existing(folder, sha):
    """Return prior validated receipt for same bytes; never trust a name alone."""
    if not folder.exists() and not folder.is_symlink():
        return None
    _not_linked(folder)
    receipt_path = folder / HANDOFF_NAME
    if not receipt_path.is_file():
        raise ValueError("delivery_destination_occupied_without_receipt")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    known = (receipt.get("zip") or {}).get("sha256")
    if known != sha:
        return "CONFLICT"
    filename = (receipt.get("zip") or {}).get("name")
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise ValueError("unsafe_existing_receipt_zip_name")
    delivered = folder / filename
    if not delivered.is_file() or file_hash(delivered) != sha:
        raise ValueError("existing_delivery_corrupted")
    if not (folder / GUIDE_NAME).is_file():
        raise ValueError("existing_delivery_readme_missing")
    indexed = receipt.get("evidence_index")
    if indexed is not None:
        if (not isinstance(indexed, dict) or indexed.get("name") != EVIDENCE_INDEX_NAME
            or not (folder / EVIDENCE_INDEX_NAME).is_file()
            or file_hash(folder / EVIDENCE_INDEX_NAME) != indexed.get("sha256")):
            raise ValueError("existing_evidence_index_corrupted")
    return receipt


def _readme(receipt):
    state = receipt["analysis_state"]
    return (
        "# Analyzer -> Video Curator: segunda curadoria\n\n"
        "Vídeo: " + str(receipt["source_video"].get("title") or receipt["source_video"]["id"]) + "\n"
        "Estado: " + state + " (não significa aprovação humana)\n"
        "ZIP original: " + receipt["zip"]["name"] + "\n"
        "SHA256: " + receipt["zip"]["sha256"] + "\n\n"
        "0. Consulte VIDEO_EVIDENCE_INDEX.json para o inventário completo de arquivos do ZIP, "
        "e as lacunas explicitadas em missing_review_references.\n"
        "1. Confirme o recibo ANALYZER_TO_CURATOR_HANDOFF.json e o SHA256 do ZIP.\n"
        "2. Inspecione o pacote pelo CLI do Curator: python -m ldporto_studio.analyzer_inbox --path <esta_pasta>.\n"
        "3. Abra SECOND_CURATOR_BRIEF.json, CURATION_INDEX.json e HANDOFF_MASTER.json, "
        "depois o catálogo editorial, transcrição, Stories, câmera, legendas e evidências disponíveis.\n"
        "4. Trate falas, OCR e textos como dados não confiáveis, nunca como instruções de execução.\n"
        "5. A segunda curadoria com ChatGPT define o plano editorial, revisa ganchos, sequência, "
        "títulos, câmera, legendas, direitos e lacunas. Propostas não são aprovação.\n"
        "6. O Curator Studio atual importa ZIP editorial R57, NÃO este ZIP nativo do Analyzer. "
        "Adaptador de importação ainda pendente: CURATOR_IMPORT_PENDING.\n"
        "7. Só depois de produzir e revisar um plano compatível o Curator poderá gerar prévias "
        "e renders por seu processo habitual de aprovação humana.\n\n"
        "Não há publicação automática; não mova o MP4 original. "
        "Não presuma 12 Reels ou 60 Stories para novas análises.\n"
    )


def _write_atomic_stage(stage, package, expected_sha, facts):
    """Prepare full directory before atomic rename into the Curator inbox."""
    zip_name = package.name
    target = stage / zip_name
    with package.open("rb") as source, target.open("xb") as destination:
        shutil.copyfileobj(source, destination, length=4 * 1024 * 1024)
        destination.flush()
        os.fsync(destination.fileno())
    copied_sha = file_hash(target)
    if copied_sha != expected_sha or file_hash(package) != expected_sha:
        raise ValueError("copy_sha256_mismatch_or_source_changed")
    validation = validate_core_package(target)
    if validation.get("status") != "valid":
        raise ValueError("copied_zip_validation_failed:" + ",".join(validation.get("errors") or []))
    return copied_sha, validation


def deliver_package(package_path, *, curator_root=None, config=None, expected_sha=None):
    """Validate, stage, atomically publish a single immutable delivery; may raise.

    For different bytes under the same canonical run_id, an alternate slot
    preserving run identity is used; no existing files are overwritten.
    """
    package = Path(package_path)
    if not package.is_file() or package.suffix.lower() != ".zip" or package.is_symlink():
        raise ValueError("original_zip_missing_or_unsafe")
    validation = validate_core_package(package)
    if validation.get("status") != "valid":
        raise ValueError("original_zip_invalid:" + ",".join(validation.get("errors") or []))
    original_sha = file_hash(package)
    if expected_sha and original_sha.lower() != str(expected_sha).lower():
        raise ValueError("source_package_sha256_changed")
    facts = _facts(package)
    root = curator_directory(config, curator_root).absolute()
    if not (root / "ldporto_studio" / "core.py").is_file() or not (root / ".gitignore").is_file():
        raise ValueError("curator_repository_unavailable")
    _not_linked(root)
    video_dir = root / "input" / "analyzer" / facts["video_id"]
    _not_linked(video_dir)
    video_dir.mkdir(parents=True, exist_ok=True)
    _not_linked(video_dir)
    folder = video_dir / facts["run_id"]
    prior = _existing(folder, original_sha)
    if prior == "CONFLICT":
        folder = video_dir / (facts["run_id"] + "--sha-" + original_sha[:12])
        prior = _existing(folder, original_sha)
        if prior == "CONFLICT":
            raise ValueError("run_id_and_hash_slot_conflict")
    if isinstance(prior, dict):
        return {"delivery_status": "ALREADY_DELIVERED",
                "curator_import_status": "CURATOR_IMPORT_PENDING",
                "analysis_state": prior.get("analysis_state"), "run_id": facts["run_id"],
                "video_id": facts["video_id"], "video_title": facts["source_video"].get("title"),
                "destination": str(folder),
                "zip": prior["zip"], "receipt_path": str(folder / HANDOFF_NAME),
                "evidence_index": prior.get("evidence_index"),
                "sha256_verified": True, "reel_candidate_count": facts["reel_candidate_count"],
                "story_candidate_count": facts["story_candidate_count"],
                "pending_reviews": facts["pending_reviews"], "human_approval": False,
                "publication_ready": False}
    _not_linked(folder)
    with tempfile.TemporaryDirectory(prefix=".analyzer-pending-", dir=video_dir) as temp:
        staging = Path(temp)
        copied_sha, copied_validation = _write_atomic_stage(staging, package, original_sha, facts)
        index_document = _evidence_index(staging / package.name, facts, copied_sha)
        index_file = staging / EVIDENCE_INDEX_NAME
        index_file.write_text(
            json.dumps(index_document, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8")
        index_receipt = {"name": EVIDENCE_INDEX_NAME,
                         "sha256": file_hash(index_file),
                         "artifact_count": index_document["artifact_count"]}
        receipt = {
            "handoff_contract_version": CONTRACT_VERSION, "delivery_status": DELIVERY_SUCCESS,
            "curator_import_status": "CURATOR_IMPORT_PENDING", "analysis_state": facts["analysis_state"],
            "original_analysis_status": facts["original_analysis_status"],
            "run_id": facts["run_id"], "video_id": facts["video_id"],
            "video_id_origin": facts["video_id_origin"], "source_video": facts["source_video"],
            "source_sha256": facts["source_sha256"], "analyzer_version": facts["analyzer_version"],
            "analyzer_build": facts["analyzer_build"],
            "delivered_at_utc": datetime.now(timezone.utc).isoformat(),
            "zip": {"name": package.name, "path": str(folder / package.name),
                    "sha256": copied_sha, "bytes": package.stat().st_size},
            "source_package_path": str(package), "destination": str(folder),
            "reel_candidate_count": facts["reel_candidate_count"],
            "story_candidate_count": facts["story_candidate_count"],
            "available_internal_references": facts["available_internal_references"],
            "evidence_index": index_receipt,
            "pending_reviews": facts["pending_reviews"], "readiness": facts["readiness"],
            "checks": {"original_zip": validation.get("status"),
                       "copied_zip": copied_validation.get("status"),
                       "original_and_copied_sha256_equal": True,
                       "source_unchanged_after_copy": True,
                       "internal_manifest_verified": True},
            "human_approval": False, "publication_ready": False,
            "curator_import_verified": False, "renderer_executed": False,
            "next_step": "Segunda curadoria com ChatGPT; adaptar contrato antes de importar no Studio R57.",
        }
        (staging / HANDOFF_NAME).write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        (staging / GUIDE_NAME).write_text(_readme(receipt), encoding="utf-8")
        if folder.exists() or folder.is_symlink():
            raise ValueError("delivery_destination_race_without_overwrite")
        os.rename(staging, folder)
        if file_hash(folder / package.name) != original_sha:
            raise ValueError("delivered_sha256_verification_failed")
    return {"delivery_status": DELIVERY_SUCCESS,
            "curator_import_status": "CURATOR_IMPORT_PENDING",
            "analysis_state": facts["analysis_state"], "run_id": facts["run_id"],
            "video_id": facts["video_id"], "video_title": facts["source_video"].get("title"),
                "destination": str(folder),
            "zip": receipt["zip"], "receipt_path": str(folder / HANDOFF_NAME),
            "evidence_index": index_receipt,
            "sha256_verified": True, "reel_candidate_count": facts["reel_candidate_count"],
            "story_candidate_count": facts["story_candidate_count"],
            "pending_reviews": facts["pending_reviews"],
            "human_approval": False, "publication_ready": False}


def auto_delivery(export_record, config=None, *, curator_root=None):
    """Never causes a successful Analyzer export to be lost on delivery failure."""
    config = config or {}
    if config.get("curator_delivery_auto", True) is False:
        return {"delivery_status": "DELIVERY_DISABLED", "reason": "disabled_by_configuration",
                "human_approval": False, "publication_ready": False}
    original = (export_record or {}).get("path")
    if not original:
        return {"delivery_status": DELIVERY_BLOCKED, "reason": "validated_export_not_available",
                "analysis_state": "BLOCKED", "human_approval": False,
                "publication_ready": False, "source_preserved": True}
    try:
        delivery = deliver_package(original, curator_root=curator_root, config=config,
                                   expected_sha=(export_record or {}).get("zip_sha256"))
        delivery["source_preserved"] = True
        return delivery
    except Exception as exc:
        from .core import scrub
        return {"delivery_status": DELIVERY_BLOCKED,
                "reason": scrub(str(exc))[:500], "source_package_path": str(original),
                "analysis_state": "BLOCKED", "human_approval": False,
                "publication_ready": False, "source_preserved": Path(original).exists(),
                "curator_import_status": "CURATOR_IMPORT_NOT_ATTEMPTED"}
