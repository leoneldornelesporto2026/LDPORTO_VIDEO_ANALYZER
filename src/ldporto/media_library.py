"""Hash-bound local originals. Resolution never downloads or deletes media."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import uuid

from .core import file_hash
from .paths import videos_directory


MEDIA_EXTENSIONS={'.mp4','.mkv','.webm','.mov','.avi'}


def _identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',value):
        raise ValueError('unsafe_media_library_id')
    return value


def _safe(path):
    path=Path(path).expanduser().absolute()
    for part in [path,*path.parents]:
        if part.is_symlink() or (part.exists() and getattr(part.lstat(),'st_file_attributes',0)&0x400):
            raise ValueError('unsafe_media_link_or_junction')
    return path.resolve()


def library_directory():
    return videos_directory()/'LDPORTO_MEDIA_LIBRARY'


def resolve_existing_media(video_id, *, expected_sha256=None, explicit_path=None,
                           project_reference=None, library_root=None, legacy_root=None,
                           registered_paths=()):
    """Return a verified original by priority, or a report requiring operator choice.

    Registered paths are explicit inputs, never a recursive disk scan. Hashes
    bind content; video ID and requested download height do not replace them.
    """
    vid=_identifier(video_id)
    if expected_sha256 is not None and not re.fullmatch(r'[a-f0-9]{64}',str(expected_sha256)):
        raise ValueError('invalid_expected_media_sha256')
    reference=project_reference or {}
    if reference.get('source_sha256') and expected_sha256 and reference['source_sha256']!=expected_sha256:
        raise ValueError('media_project_reference_identity_conflict')
    expected_sha256=expected_sha256 or reference.get('source_sha256')
    # Resolve higher-priority explicit locations before reading lower-priority
    # manifests; a malformed library cannot veto a valid operator selection.
    for origin,selected in (('explicit_selection',explicit_path),('project_reference',reference.get('local_path'))):
        if selected:
            selected=_safe(selected)
            if selected.is_file() and selected.suffix.lower() in MEDIA_EXTENSIONS:
                actual=file_hash(selected)
                if expected_sha256 and actual!=expected_sha256:
                    if origin=='explicit_selection':
                        raise ValueError('selected_media_hash_mismatch')
                    continue
                return {'status':'FOUND_VERIFIED','path':str(selected),'origin':origin,'video_id':vid,
                    'source_sha256':actual,'bytes':selected.stat().st_size,'download_needed':False,
                    'container_validation':'extension_only_use_media_inspect_before_render',
                    'attempts':[],'publication_ready':False}
    choices=[]
    if explicit_path:
        choices.append(('explicit_selection',Path(explicit_path),expected_sha256))
    if reference.get('local_path'):
        choices.append(('project_reference',Path(reference['local_path']),expected_sha256))
    library=_safe(library_root or library_directory())/vid
    manifest=library/'media_manifest.json'
    if manifest.is_file():
        doc=json.loads(_safe(manifest).read_text(encoding='utf-8'))
        filename=doc.get('relative_path')
        if not isinstance(filename,str) or Path(filename).name!=filename or any(c in filename for c in '/\\:'):
            raise ValueError('unsafe_media_library_manifest')
        if doc.get('video_id')!=vid:
            raise ValueError('media_library_manifest_id_mismatch')
        choices.append(('media_library',library/filename,expected_sha256 or doc.get('source_sha256')))
    if legacy_root:
        legacy=_safe(legacy_root)/vid
        record=legacy/'download.json'
        doc=json.loads(_safe(record).read_text(encoding='utf-8')) if record.is_file() else {}
        filename=doc.get('filename')
        if filename is not None and (not isinstance(filename,str) or Path(filename).name!=filename or
                                      any(c in filename for c in '/\\:') or '..' in filename):
            raise ValueError('Cache de download referencia caminho inseguro.')
        if filename:
            choices.append(('legacy_input',legacy/filename,expected_sha256 or doc.get('sha256')))
        elif legacy.is_dir():
            choices.extend(('legacy_input',p,expected_sha256) for p in sorted(legacy.glob(vid+'.*')) if p.suffix.lower() in MEDIA_EXTENSIONS)
    choices.extend(('registered_search',Path(p),expected_sha256) for p in registered_paths)
    attempts=[]; seen=set()
    for origin,path,expected in choices:
        checked=_safe(path)
        if checked in seen:
            continue
        seen.add(checked)
        if not checked.is_file() or checked.suffix.lower() not in MEDIA_EXTENSIONS:
            attempts.append({'origin':origin,'filename':checked.name,'status':'MISSING_OR_UNSUPPORTED'})
            continue
        actual=file_hash(checked)
        if expected and actual!=expected:
            attempts.append({'origin':origin,'filename':checked.name,'status':'HASH_MISMATCH','actual_sha256':actual})
            if origin=='explicit_selection':
                raise ValueError('selected_media_hash_mismatch')
            continue
        return {'status':'FOUND_VERIFIED','path':str(checked),'origin':origin,'video_id':vid,
                'source_sha256':actual,'bytes':checked.stat().st_size,'download_needed':False,
                'container_validation':'extension_only_use_media_inspect_before_render',
                'attempts':attempts,'publication_ready':False}
    return {'status':'OPERATOR_SELECTION_REQUIRED','video_id':vid,'source_sha256':expected_sha256,
            'download_needed':True,'download_authorized':False,'attempts':attempts,'publication_ready':False}


def register_media_copy(source, video_id, expected_sha256, *, library_root=None, metadata=None):
    """Copy into a new library identity; preserve source and partials on failure."""
    source=_safe(source); vid=_identifier(video_id)
    if source.suffix.lower() not in MEDIA_EXTENSIONS or file_hash(source)!=expected_sha256:
        raise ValueError('media_copy_source_identity_mismatch')
    root=_safe(_safe(library_root or library_directory())/vid)
    root.mkdir(parents=True,exist_ok=True)
    root=_safe(root)
    target=root/('original'+source.suffix.lower())
    already_present=target.exists()
    if already_present:
        if file_hash(_safe(target))!=expected_sha256:
            raise ValueError('media_library_existing_original_conflict')
    else:
        temporary=root/('.copy_'+uuid.uuid4().hex+'.partial')
        with source.open('rb') as incoming,temporary.open('xb') as outgoing:
            shutil.copyfileobj(incoming,outgoing,8*1024**2)
        if file_hash(temporary)!=expected_sha256 or file_hash(source)!=expected_sha256:
            raise ValueError('media_copy_checksum_mismatch_source_and_partial_preserved')
        # Exclusive creation on both Windows and POSIX; rename can replace on POSIX.
        os.link(temporary,target)
        temporary.unlink()  # Only the task-owned temporary link, after verified copy.
    manifest={'schema_version':'1.0','video_id':vid,'source_sha256':expected_sha256,
        'relative_path':target.name,'bytes':target.stat().st_size,'created_at':datetime.now(timezone.utc).isoformat(),
        'metadata':metadata or {},'source_preserved':True,'publication_ready':False}
    for name,document in (('media_manifest.json',manifest),('integrity.json',{'schema_version':'1.0',
        'state':'HASH_VERIFIED','source_sha256':expected_sha256,'copy_sha256':file_hash(target),
        'source_removed':False,'publication_ready':False})):
        path=root/name
        if path.exists():
            existing=json.loads(_safe(path).read_text(encoding='utf-8'))
            if existing.get('source_sha256')!=expected_sha256 or existing.get('publication_ready') is not False:
                raise ValueError('media_library_existing_manifest_conflict')
            if name=='media_manifest.json' and (existing.get('video_id')!=vid or existing.get('relative_path')!=target.name):
                raise ValueError('media_library_existing_manifest_conflict')
            if name=='integrity.json' and (existing.get('copy_sha256')!=expected_sha256 or existing.get('source_removed') is not False):
                raise ValueError('media_library_existing_integrity_conflict')
            continue
        with path.open('x',encoding='utf-8') as handle:
            json.dump(document,handle,ensure_ascii=False,indent=2)
    return {'status':'ALREADY_VERIFIED' if already_present else 'COPIED_VERIFIED','path':str(target),
            'source_sha256':expected_sha256,'source_preserved':True}
