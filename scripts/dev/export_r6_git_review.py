"""Prepare a reviewable, text-only Git snapshot of a validated R6 delivery.

No Git operations or network calls. The original Analyzer ZIP and Curator input
remain untouched. This represents the CANONICAL EXPORTED R6 evidence, not the
whole ignored analysis/ runtime directory or any raw media.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import shutil
from zipfile import ZipFile

TEXT_SUFFIXES = frozenset({
    ".json", ".jsonl", ".srt", ".vtt", ".txt", ".md",
    ".csv", ".tsv", ".yaml", ".yml", ".xml"
})
MAX_ZIP_BYTES = 256 * 1024 * 1024
MAX_TEXT_BYTES = 160 * 1024 * 1024
MAX_FILE_BYTES = 24 * 1024 * 1024  # Direct display threshold, NOT a rejection limit.
CHUNK_BYTES = 4 * 1024 * 1024       # Git-readable UTF-8 text parts.
MAX_FILES = 5000
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,96}$")
SAFE_RUN = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
SCHEMA = "ldporto-analyzer-git-evidence-1.0"


def digest(path):
    result = sha256()
    with Path(path).open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(part)
    return result.hexdigest()


def _safe_name(name):
    p = PurePosixPath(name)
    return bool(name) and not p.is_absolute() and ".." not in p.parts and (
        "\\" not in name and ":" not in name and name == p.as_posix()
    ) and not name.startswith(".")


def _is_link(path):
    return path.is_symlink() or bool(
        getattr(path.lstat(), "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)
    )


def _text_chunks(raw):
    """Lossless UTF-8 slices, each at most CHUNK_BYTES and individually readable."""
    chunks=[]
    offset=0
    while offset<len(raw):
        end=min(len(raw),offset+CHUNK_BYTES)
        if end<len(raw):
            # Do not split a multibyte Unicode code point.
            while end>offset and raw[end] & 0xC0 == 0x80:
                end-=1
        if end==offset:
            raise ValueError("Fronteira UTF-8 inválida no particionamento")
        part=raw[offset:end]
        try:
            part.decode("utf-8-sig" if offset==0 else "utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Chunk textual UTF-8 inválido") from exc
        chunks.append(part)
        offset=end
    return chunks


def _parts_for(path, raw):
    """Content-addressed path namespace avoids any collisions with R6 members."""
    parent="parts/"+sha256(path.encode("utf-8")).hexdigest()
    return [
        {"path":f"{parent}/{i:05d}.txt",
         "bytes":len(part),"sha256":sha256(part).hexdigest()}
        for i,part in enumerate(_text_chunks(raw),1)
    ]


def plan_snapshot(delivery):
    """Validate receipt, canonical ZIP, every manifest hash; return immutable plan."""
    root = Path(delivery).expanduser().resolve(strict=True)
    if not root.is_dir() or _is_link(root):
        raise ValueError("Diretório de entrega inválido ou link")
    receipt_path = root / "ANALYZER_TO_CURATOR_HANDOFF.json"
    if not receipt_path.is_file() or _is_link(receipt_path):
        raise ValueError("Recibo Analyzer→Curator ausente ou link")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (receipt.get("human_approval") is not False or
            receipt.get("publication_ready") is not False or
            receipt.get("curator_import_status") != "CURATOR_IMPORT_PENDING"):
        raise ValueError("A entrega não é rascunho R6 válido")
    run_id = receipt.get("run_id")
    video_id = root.parent.name
    if not isinstance(run_id, str) or not SAFE_RUN.fullmatch(run_id):
        raise ValueError("run_id inseguro; exportação Git recusada")
    if not SAFE_ID.fullmatch(video_id):
        raise ValueError("video_id inseguro; exportação Git recusada")
    z = receipt.get("zip") or {}
    zip_name = z.get("name")
    if (not isinstance(zip_name, str) or Path(zip_name).name != zip_name
            or not zip_name.endswith(".zip")):
        raise ValueError("Nome de ZIP inseguro")
    archive_path = root / zip_name
    if (not archive_path.is_file() or _is_link(archive_path)
            or not 0 < archive_path.stat().st_size <= MAX_ZIP_BYTES
            or archive_path.stat().st_size != z.get("bytes")
            or digest(archive_path) != z.get("sha256")):
        raise ValueError("ZIP original não corresponde ao recibo")
    text_files = []
    excluded = []
    with ZipFile(archive_path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if (not 0 < len(infos) <= MAX_FILES or len(set(names)) != len(names)
                or any(not _safe_name(n) for n in names)
                or sum(info.file_size for info in infos) > MAX_ZIP_BYTES):
            raise ValueError("Membros ZIP inseguros/duplicados ou limite excedido")
        # Files must not be represented as Unix symlinks in the ZIP.
        if any(((info.external_attr >> 16) & 0o170000) == 0o120000
               for info in infos):
            raise ValueError("ZIP contém links simbólicos")
        required = {"SECOND_CURATION_MANIFEST.json",
                    "source/metadata.json", "editorial/candidate_catalog.json"}
        if not required.issubset(names):
            raise ValueError("Contrato Analyzer R6 incompleto")
        manifest = json.loads(archive.read("SECOND_CURATION_MANIFEST.json"))
        if manifest.get("run_id") != run_id:
            raise ValueError("run_id ZIP diverge do recibo")
        metadata = json.loads(archive.read("source/metadata.json"))
        if metadata.get("sha256") != receipt.get("source_sha256"):
            raise ValueError("SHA da fonte diverge entre ZIP e recibo")
        declared = manifest.get("files")
        if not isinstance(declared, list):
            raise ValueError("Manifesto ZIP sem lista de arquivos")
        paths = [e.get("path") for e in declared if isinstance(e, dict)]
        if (len(paths) != len(declared) or len(paths) != len(set(paths))
                or set(paths) != set(names) - {"SECOND_CURATION_MANIFEST.json"}):
            raise ValueError("Manifesto não cobre todos os membros do ZIP")
        table = {e["path"]: e for e in declared}
        total_text = 0
        for info in infos:
            name = info.filename
            raw = archive.read(name)
            record = table.get(name)
            if record is not None and (record.get("bytes") != len(raw)
                    or record.get("sha256") != sha256(raw).hexdigest()):
                raise ValueError("Evidência alterada: " + name)
            if info.is_dir():
                raise ValueError("Membro diretório não esperado")
            if PurePosixPath(name).suffix.lower() not in TEXT_SUFFIXES:
                excluded.append({"path": name, "bytes": len(raw),
                                 "sha256": sha256(raw).hexdigest(),
                                 "reason": "NON_TEXT_MEDIA_OR_BINARY"})
                continue
            total_text += len(raw)
            if total_text > MAX_TEXT_BYTES:
                raise ValueError("Conjunto textual acima de 160 MiB")
            try:
                raw.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValueError("Arquivo textual não UTF-8: " + name) from exc
            row={"path":name,"bytes":len(raw),"sha256":sha256(raw).hexdigest()}
            if len(raw)>MAX_FILE_BYTES:
                row["storage"]="UTF8_LOSSLESS_PARTS"
                row["parts"]=_parts_for(name,raw)
            text_files.append(row)
    return {
        "schema": SCHEMA,
        "status": "GIT_TEXT_REVIEW_PENDING",
        "video_id": video_id,
        "run_id": run_id,
        "source_sha256": receipt["source_sha256"],
        "source_zip_sha256": z["sha256"],
        "zip_members_total": len(names),
        "git_text_files": text_files,
        "excluded_binary_files": excluded,
        "text_bytes": total_text,
        "chunked_text_file_count":sum(bool(x.get("parts")) for x in text_files),
        "chunk_count":sum(len(x.get("parts",[])) for x in text_files),
        "human_approved": False,
        "publication_ready": False,
        "git_commit_created": False,
        "git_push_executed": False,
        "zip_or_media_modified": False,
    }


def save_snapshot(delivery, destination_root):
    """Copy manifest-proven text into a content-addressed Git-visible docs tree."""
    plan = plan_snapshot(delivery)
    dest_root = Path(destination_root).expanduser().resolve()
    delivery_root = Path(delivery).expanduser().resolve(strict=True)
    if (dest_root == delivery_root or dest_root.is_relative_to(delivery_root)
            or delivery_root.is_relative_to(dest_root)):
        raise ValueError("Git export não pode sobrepor a entrega de origem")
    folder = (dest_root / plan["video_id"] /
              (plan["run_id"] + "_" + plan["source_zip_sha256"][:12]))
    if folder.exists():
        if not folder.is_dir() or _is_link(folder):
            raise ValueError("Snapshot pré-existente inválido")
        return _verify_existing(folder, plan)
    folder.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".analyzer-git-stage-", dir=folder.parent))
    committed = False
    try:
        zname = json.loads((delivery_root / "ANALYZER_TO_CURATOR_HANDOFF.json")
                           .read_text(encoding="utf-8"))["zip"]["name"]
        with ZipFile(delivery_root / zname) as archive:
            for row in plan["git_text_files"]:
                raw = archive.read(row["path"])
                if len(raw) != row["bytes"] or sha256(raw).hexdigest() != row["sha256"]:
                    raise ValueError("Evidência mudou durante exportação: " + row["path"])
                if row.get("parts"):
                    chunks=_text_chunks(raw)
                    if len(chunks)!=len(row["parts"]):
                        raise ValueError("Contagem de partes divergente: "+row["path"])
                    for info,part in zip(row["parts"],chunks):
                        if (len(part)!=info["bytes"] or
                                sha256(part).hexdigest()!=info["sha256"]):
                            raise ValueError("Parte divergente: "+info["path"])
                        target=stage.joinpath(*PurePosixPath(info["path"]).parts)
                        target.parent.mkdir(parents=True,exist_ok=True)
                        target.write_bytes(part)
                else:
                    destination = stage.joinpath("evidence", *PurePosixPath(row["path"]).parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(raw)
        (stage / "ANALYZER_GIT_EVIDENCE_MANIFEST.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (stage / "README.md").write_text(
            "# Analyzer R6 | Evidências textuais originais\n\n"
            "Snapshot verificável do ZIP canônico exportado. Textos pequenos em evidence/.\n"
            "Textos maiores que 24 MiB são particionados sem perda em parts/<SHA256-do-caminho>/"
            "00001.txt etc.; o manifesto lista a ordem, bytes e SHA256 de cada pedaço.\n"
            "A concatenação binária na ordem restaura exatamente o arquivo original,"
            " comprovável pelo sha256 do membro no manifesto.\n"
            "O manifesto lista também imagens e binários não versionados.\n\n"
            "A transcrição é o ASR ORIGINAL, não as legendas revisadas.\n"
            "A segunda checagem de palavras, tempos e contexto pertence ao Curator.\n"
            "Nenhuma aprovação, render, Git commit ou push automático ocorreu.\n"
            "Revise direitos, dados pessoais e caminhos/segredos antes de adicionar ao Git.\n",
            encoding="utf-8")
        _verify_existing(stage, plan)
        if folder.exists():
            raise ValueError("Snapshot concorrente existente; não sobrescrever")
        stage.rename(folder)
        committed = True
        return folder
    finally:
        if not committed and stage.exists():
            shutil.rmtree(stage)


def _verify_existing(folder, plan):
    manifest = folder / "ANALYZER_GIT_EVIDENCE_MANIFEST.json"
    if not manifest.is_file() or _is_link(manifest):
        raise ValueError("Snapshot anterior sem manifesto íntegro")
    saved_plan=json.loads(manifest.read_text(encoding="utf-8"))
    if saved_plan!=plan:
        # Legacy NASA snapshots were written before the optional part counters
        # existed. Accept them ONLY when all original entries are direct files
        # and the remaining complete, hash-bound manifest is identical.
        old_fields=("chunked_text_file_count","chunk_count")
        legacy_plan={k:v for k,v in plan.items() if k not in old_fields}
        if (any(x.get("parts") for x in plan["git_text_files"])
                or saved_plan!=legacy_plan):
            raise ValueError("Snapshot anterior pertence a outro ZIP")
    expected={"ANALYZER_GIT_EVIDENCE_MANIFEST.json","README.md"}
    for row in plan["git_text_files"]:
        if row.get("parts"):
            expected.update(x["path"] for x in row["parts"])
        else:
            expected.add("evidence/"+row["path"])
    files = list(folder.rglob("*"))
    if any(_is_link(p) for p in files):
        raise ValueError("Snapshot anterior contém link")
    actual = {p.relative_to(folder).as_posix() for p in files if p.is_file()}
    if actual != expected:
        raise ValueError("Arquivos do snapshot anterior foram adicionados/removidos")
    for row in plan["git_text_files"]:
        if row.get("parts"):
            calculated=sha256()
            size=0
            for part in row["parts"]:
                p=folder.joinpath(*PurePosixPath(part["path"]).parts)
                if (not p.is_file() or p.stat().st_size!=part["bytes"]
                        or digest(p)!=part["sha256"]):
                    raise ValueError("Parte textual já exportada foi modificada: "+part["path"])
                size+=part["bytes"]
                with p.open("rb") as source:
                    for block in iter(lambda:source.read(1024*1024),b""):
                        calculated.update(block)
            if size!=row["bytes"] or calculated.hexdigest()!=row["sha256"]:
                raise ValueError("Reconstrução SHA256 do texto divergente: "+row["path"])
        else:
            p = folder.joinpath("evidence", *PurePosixPath(row["path"]).parts)
            if not p.is_file() or p.stat().st_size != row["bytes"] or digest(p) != row["sha256"]:
                raise ValueError("Texto já exportado foi modificado: " + row["path"])
    return folder


def main(argv=None):
    p = argparse.ArgumentParser(description="R6 evidence snapshot for Git review only")
    p.add_argument("--delivery", required=True, type=Path,
                   help="Curator input/analyzer/<video_id>/<run_id>")
    p.add_argument("--destination-root", type=Path,
                   default=Path(__file__).resolve().parents[2] / "docs" / "analyzer_runs")
    p.add_argument("--summary", action="store_true",
                   help="Print compact counts instead of full manifest inventory")
    p.add_argument("--save", action="store_true",
                   help="Persist verified textual evidence in docs/analyzer_runs")
    p.add_argument("--confirm-git-text-review", action="store_true",
                   help="Acknowledge that Git text can contain transcript/metadata")
    args = p.parse_args(argv)
    if args.save and not args.confirm_git_text_review:
        raise ValueError("Exige --confirm-git-text-review para salvar material textual")
    plan = plan_snapshot(args.delivery)
    if args.save:
        plan["saved_folder"] = str(save_snapshot(args.delivery, args.destination_root))
    else:
        plan["saved_folder"] = None
    if args.summary:
        summary={k:plan[k] for k in (
            "schema","status","video_id","run_id","zip_members_total",
            "text_bytes","chunked_text_file_count","chunk_count",
            "human_approved","git_commit_created","git_push_executed",
            "saved_folder")}
        summary["git_text_file_count"]=len(plan["git_text_files"])
        summary["excluded_binary_file_count"]=len(plan["excluded_binary_files"])
        summary["large_text_names"]=[
            x["path"] for x in plan["git_text_files"] if x.get("parts")]
        print(json.dumps(summary,ensure_ascii=False,indent=2))
    else:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
