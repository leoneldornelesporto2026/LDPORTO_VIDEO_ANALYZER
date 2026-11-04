"""Read-only inventory and recoverable cleanup of explicitly regenerable files.

Original media and editorial artifacts are protected. Confirmed cleanup moves
allowlisted files to quarantine inside that analysis; it frees no disk space.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import time
import uuid


QUARANTINE_DIR = '.ldporto_quarantine'
PROTECTED = ('Original media, JSON, transcript, words, SRT, candidates, camera, '
             'contact sheets, reports, packages, revisions, approvals and final renders')


def _safe_path(value, root=None):
    """Reject traversal and every symlink/junction/reparse ancestor before resolve."""
    raw = Path(value).expanduser()
    windows = PureWindowsPath(str(value))
    if '..' in raw.parts or '..' in windows.parts:
        raise ValueError('Caminho com travessia não autorizado')
    if root is not None and (raw.is_absolute() or windows.is_absolute() or windows.drive):
        raise ValueError('Referência deve ser relativa ao projeto')
    path = Path(root) / raw if root is not None else raw.absolute()
    for component in (path, *path.parents):
        try:
            stat = component.lstat()
        except FileNotFoundError:
            continue
        if component.is_symlink() or getattr(stat, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Links simbólicos, junctions e reparse points não são permitidos')
    actual = path.resolve()
    if root is not None and not actual.is_relative_to(Path(root).resolve()):
        raise ValueError('Caminho fora do projeto')
    return actual


def _project_root(value):
    root = _safe_path(value)
    if not root.is_dir():
        raise ValueError('Pasta do projeto inexistente')
    from .paths import PROJECT_ROOT
    forbidden = {Path(root.anchor), Path.home().resolve(), PROJECT_ROOT.resolve()}
    protected_ancestors = {QUARANTINE_DIR, 'revisions', 'approved', 'approvals',
                           'final_renders', 'renders', '.git', 'models'}
    if (root in forbidden or PROJECT_ROOT.resolve().is_relative_to(root)
            or any(part.lower() in protected_ancestors for part in root.parts)):
        raise ValueError('Selecione uma análise específica, não a raiz do aplicativo')
    return root


def _hash(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def _pid_alive(pid):
    if pid <= 0:
        return True
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() != 87  # Only an unknown PID is proven dead.
        code = wintypes.DWORD()
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        try:
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _project_in_use(root):
    lock = Path(root) / 'RUNNING.lock'
    try:
        if lock.is_symlink():
            return True
        if lock.exists():
            _safe_path(lock)
            return _pid_alive(int(lock.read_text(encoding='utf-8').strip()))
    except (OSError, ValueError):
        return True
    return False


def media_in_use(path):
    try:
        path = _safe_path(path)
        for marker in path.parent.glob('.ldporto_media_use_*.json'):
            try:
                row = json.loads(_safe_path(marker).read_text(encoding='utf-8'))
                owner = _safe_path(row['path'])
                if owner == path and _pid_alive(int(row['pid'])):
                    return True
            except (OSError, ValueError, TypeError, KeyError):
                return True  # Unknown ownership is not proof of safety.
        return False
    except (OSError, ValueError):
        return True


@contextmanager
def media_lease(path):
    path = _safe_path(path)
    marker = path.parent / ('.ldporto_media_use_' + uuid.uuid4().hex + '.json')
    with marker.open('x', encoding='utf-8') as handle:
        json.dump({'path': str(path), 'pid': os.getpid(), 'started_at': time.time()}, handle)
    try:
        yield
    finally:
        marker.unlink(missing_ok=True)


def _regenerable(relative):
    parts = relative.parts
    if len(parts) < 2 or any(part.lower() in {
            'renders', 'final_renders', 'revisions', 'approved', 'approvals', QUARANTINE_DIR
    } for part in parts):
        return False
    if 'final' in relative.stem.lower().split('_'):
        return False
    return (parts[0] == 'audio' and relative.suffix.lower() == '.wav'
            or parts[0] in {'temporary_frames', 'render_staging'} and relative.suffix.lower() in {'.png', '.wav', '.tmp'}
            or parts[0] == '.cache' and relative.suffix.lower() in {'.npz', '.npy', '.pkl'})


def _removable(path, root, source=None):
    try:
        actual = _safe_path(path)
        if _project_in_use(root) or not actual.is_file() or media_in_use(actual):
            return False
        if not actual.is_relative_to(root) or not _regenerable(actual.relative_to(root)):
            return False
        # Compatibility argument: a source can only add protection.
        if source and (actual == source or (source.exists() and os.path.samefile(actual, source))):
            return False
        return True
    except (OSError, ValueError):
        return False


def _files(root):
    """Walk without descending into links, junctions or other reparse points."""
    pending = [root]
    while pending:
        folder = pending.pop()
        try:
            with os.scandir(_safe_path(folder)) as entries:
                for entry in entries:
                    try:
                        path = _safe_path(entry.path)
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(path)
                        elif entry.is_file(follow_symlinks=False):
                            yield path
                    except (OSError, ValueError):
                        continue
        except (OSError, ValueError):
            continue


def cleanup_preview(root, source=None, include_source=False):
    """Read only. include_source is ignored: original media stays protected."""
    root = _project_root(root)
    source = _safe_path(source) if source else None
    removable, total, quarantined = [], 0, 0
    for path in _files(root):
        try:
            stat = path.stat()
            total += stat.st_size
            if QUARANTINE_DIR in path.relative_to(root).parts:
                quarantined += stat.st_size
            if _removable(path, root, source):
                checksum = _hash(path)
                after = path.stat()
                if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    continue
                removable.append({'path': str(path), 'relative_path': path.relative_to(root).as_posix(),
                                  'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns, 'sha256': checksum})
        except OSError:
            continue
    eligible = sum(row['bytes'] for row in removable)
    return {'schema_version': '6.0', 'root': str(root), 'optional_source': None,
            'protected_source': str(source) if source else None, 'include_source_allowed': False,
            'current_bytes': total, 'reclaimable_bytes': eligible, 'regenerable_bytes': eligible,
            'preserved_bytes': total - eligible, 'quarantine_bytes': quarantined,
            'reclaimed_bytes_after_action': 0, 'action': 'quarantine',
            'project_in_use': _project_in_use(root), 'requires_confirmation': True,
            'removable': sorted(removable, key=lambda row: row['path']), 'protected': PROTECTED}


def _write_receipt(path, document):
    path = _safe_path(path)
    temporary = path.with_name('.receipt_' + uuid.uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _matching(path, row):
    stat = path.stat()
    return (stat.st_size == row['bytes'] and stat.st_mtime_ns == row['mtime_ns']
            and _hash(path) == row['sha256'])


def _move_no_replace(source, destination):
    """Never replace an existing destination, including on non-Windows hosts."""
    if os.name == 'nt':
        os.rename(source, destination)  # Windows rename fails if the target exists.
    else:
        # Both paths are on the same filesystem. An exclusive hard link avoids
        # POSIX rename's replacement semantics; unlink only follows a valid link.
        os.link(source, destination, follow_symlinks=False)
        source.unlink()


def execute_cleanup(preview, confirmed=False, cancel=None):
    """Quarantine unchanged regenerable files. No final deletion is performed."""
    if confirmed is not True:
        raise ValueError('Confirme o preview da quarentena antes de mover arquivos')
    root = _project_root(preview['root'])
    source = preview.get('protected_source')
    source = _safe_path(source) if source else None
    identifier = uuid.uuid4().hex
    quarantine = _safe_path(Path(QUARANTINE_DIR) / identifier, root)
    removed, skipped, errors = [], [], []
    cancelled = False
    reserved = False
    receipt = {'schema_version': '6.0', 'root': str(root), 'quarantine_id': identifier,
               'created_at': datetime.now(timezone.utc).isoformat(), 'files': []}
    for row in preview.get('removable', []):
        if cancel and cancel():
            cancelled = True
            skipped.append(str(row.get('path', 'invalid_reference')))
            continue
        try:
            path = _safe_path(row['path'])
            if not _removable(path, root, source) or not _matching(path, row):
                skipped.append(row['path'])
                continue
            relative = path.relative_to(root)
            if not reserved:
                _safe_path(QUARANTINE_DIR, root).mkdir(exist_ok=True)
                quarantine.mkdir(exist_ok=False)
                reserved = True
            destination = _safe_path(Path('files') / relative, quarantine)
            if destination.exists():
                raise FileExistsError('Colisão na quarentena')
            destination.parent.mkdir(parents=True, exist_ok=True)
            item = {**row, 'relative_path': relative.as_posix(), 'status': 'pending'}
            receipt['files'].append(item)
            _write_receipt(quarantine / 'manifest.json', receipt)
            # A same-volume rename avoids partial copies and leaves the original
            # untouched if the filesystem refuses the move.
            _safe_path(destination)
            if (not _removable(path, root, source) or not _matching(path, row)
                    or (cancel and cancel())):
                item['status'] = 'skipped'
                skipped.append(row['path'])
            else:
                _safe_path(path)
                _safe_path(destination)
                if destination.exists():
                    raise FileExistsError('Colisão na quarentena')
                _move_no_replace(path, destination)
                item['status'] = 'quarantined'
                removed.append(row)
            _write_receipt(quarantine / 'manifest.json', receipt)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if row not in removed:
                skipped.append(str(row.get('path', 'invalid_reference')))
            errors.append({'path': str(row.get('path', 'invalid_reference')), 'reason': str(exc)})
    moved = sum(row['bytes'] for row in removed)
    return {'action': 'quarantine', 'removed_bytes': moved, 'quarantined_bytes': moved,
            'reclaimed_bytes': 0, 'removed': removed, 'skipped': skipped, 'errors': errors,
            'cancelled': cancelled or bool(cancel and cancel()),
            'quarantine_id': identifier if receipt['files'] else None,
            'quarantine_path': str(quarantine) if receipt['files'] else None}


def restore_preview(root, quarantine_id):
    """Read-only restore plan; collisions, changed hashes and live owners block it."""
    root = _project_root(root)
    if not isinstance(quarantine_id, str) or len(quarantine_id) != 32 or any(
            character not in '0123456789abcdef' for character in quarantine_id):
        raise ValueError('ID de quarentena inválido')
    quarantine = _safe_path(Path(QUARANTINE_DIR) / quarantine_id, root)
    receipt = json.loads(_safe_path('manifest.json', quarantine).read_text(encoding='utf-8'))
    if (not isinstance(receipt, dict) or not isinstance(receipt.get('files'), list)
            or any(not isinstance(item, dict) for item in receipt['files'])):
        raise ValueError('Recibo de quarentena inválido')
    if receipt.get('root') != str(root) or receipt.get('quarantine_id') != quarantine_id:
        raise ValueError('Recibo não pertence a este projeto')
    rows = []
    for item in receipt.get('files', []):
        if item.get('status') not in {'pending', 'quarantined'}:
            continue
        row = {**item, 'restorable': False, 'reason': None}
        try:
            relative = Path(item['relative_path'])
            target = _safe_path(relative, root)
            stored = _safe_path(Path('files') / relative, quarantine)
            if not _regenerable(relative):
                row['reason'] = 'protected_file'
            elif _project_in_use(root) or media_in_use(target) or media_in_use(stored):
                row['reason'] = 'project_or_media_in_use'
            elif target.exists():
                row['reason'] = 'destination_exists'
            elif not stored.is_file() or not _matching(stored, item):
                row['reason'] = 'missing_or_changed_quarantine_file'
            else:
                row['restorable'] = True
        except (OSError, ValueError, KeyError, TypeError) as exc:
            row['reason'] = str(exc)
        rows.append(row)
    return {'schema_version': '6.0', 'root': str(root), 'quarantine_id': quarantine_id,
            'requires_confirmation': True, 'files': rows,
            'restorable_bytes': sum(row['bytes'] for row in rows if row['restorable'])}


def restore_quarantine(root, quarantine_id, confirmed=False, cancel=None):
    if confirmed is not True:
        raise ValueError('Confirme o preview da restauração antes de mover arquivos')
    plan = restore_preview(root, quarantine_id)
    root = _project_root(plan['root'])
    quarantine = _safe_path(Path(QUARANTINE_DIR) / quarantine_id, root)
    receipt_path = _safe_path('manifest.json', quarantine)
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    restored, skipped, errors = [], [], []
    for row in plan['files']:
        if cancel and cancel():
            skipped.append({**row, 'reason': 'cancelled'})
            continue
        if not row['restorable']:
            skipped.append(row)
            continue
        try:
            relative = Path(row['relative_path'])
            source = _safe_path(Path('files') / relative, quarantine)
            target = _safe_path(relative, root)
            target.parent.mkdir(parents=True, exist_ok=True)
            if (target.exists() or _project_in_use(root) or media_in_use(target)
                    or media_in_use(source) or not _matching(source, row) or (cancel and cancel())):
                raise ValueError('Destino ou arquivo mudou após o preview')
            _safe_path(source)
            _safe_path(target)
            if target.exists():
                raise FileExistsError('Colisão na restauração')
            _move_no_replace(source, target)
            restored.append(row)
            for item in receipt['files']:
                if item.get('relative_path') == row['relative_path']:
                    item['status'] = 'restored'
            _write_receipt(receipt_path, receipt)
        except (OSError, ValueError) as exc:
            if row not in restored:
                skipped.append({**row, 'reason': str(exc)})
            errors.append({'relative_path': row['relative_path'], 'reason': str(exc)})
    return {'restored': restored, 'restored_bytes': sum(row['bytes'] for row in restored),
            'skipped': skipped, 'errors': errors, 'quarantine_id': quarantine_id,
            'cancelled': bool(cancel and cancel())}


def _document(root, name):
    try:
        path = _safe_path(name, root)
        if path.stat().st_size > 4 * 1024 * 1024:
            return {}
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def list_quarantines(root):
    root = _project_root(root)
    directory = _safe_path(QUARANTINE_DIR, root)
    if not directory.is_dir():
        return []
    result = []
    for child in sorted(directory.iterdir()):
        try:
            plan = restore_preview(root, child.name)
            result.append({'quarantine_id': child.name, 'restorable_bytes': plan['restorable_bytes'],
                           'file_count': len(plan['files'])})
        except (OSError, ValueError):
            continue
    return result


def list_projects(base=None, export_verifier=None):
    """Inventory only: no index writes, extraction, model calls or media changes.

    export_verifier may supply the organized export's read-only validator.
    Without it, an existing export is explicitly recorded as not verified.
    """
    from .paths import ANALYSIS_DIR
    base = _safe_path(base or ANALYSIS_DIR)
    if not base.is_dir():
        return []
    markers = ('metadata.json', 'run_manifest.json', 'analysis.json', 'analysis.compact.json')
    folders = [base] if any((base / name).is_file() for name in markers) else []
    if not folders:
        for child in base.iterdir():
            try:
                child = _safe_path(child)
                if child.is_dir() and child.name != QUARANTINE_DIR and any((child / name).is_file() for name in markers):
                    folders.append(child)
            except (OSError, ValueError):
                continue
    projects = []
    for folder in sorted(folders):
        preview = cleanup_preview(folder)
        metadata = _document(folder, 'metadata.json')
        if not metadata:
            metadata = _document(folder, 'analysis.json').get('metadata') or {}
        if not metadata:
            metadata = _document(folder, 'analysis.compact.json').get('metadata') or {}
        if not isinstance(metadata, dict):
            metadata = {}
        manifest = _document(folder, 'run_manifest.json')
        source = metadata.get('source') if isinstance(metadata.get('source'), dict) else {}
        exported = _document(folder, 'project_export.json')
        export_path = exported.get('path') or exported.get('export_path')
        exists, integrity = False, 'unavailable'
        if export_path:
            try:
                exists = _safe_path(export_path).is_dir()
                integrity = 'not_verified' if exists else 'missing'
                if exists and export_verifier:
                    result = export_verifier(export_path)
                    integrity = result.get('status', 'not_verified') if isinstance(result, dict) else 'not_verified'
                    external_manifest = _safe_path('PROJECT_MANIFEST.json', export_path)
                    if exported.get('manifest_sha256') and _hash(external_manifest) != exported['manifest_sha256']:
                        integrity = 'failed'
                    if metadata.get('sha256'):
                        external_source = _document(export_path, 'PROJECT_MANIFEST.json').get('source_sha256')
                        if external_source != metadata['sha256']:
                            integrity = 'failed'
            except (OSError, ValueError):
                integrity = 'invalid_path'
        latest = folder.stat().st_mtime
        for path in _files(folder):
            try:
                latest = max(latest, path.stat().st_mtime)
            except OSError:
                continue
        projects.append({'root': str(folder), 'name': source.get('title') or metadata.get('filename') or folder.name,
                         'video_id': source.get('id'), 'date': manifest.get('created_at') or manifest.get('started_at'),
                         'status': manifest.get('analysis_status') or 'unavailable',
                         'disk_bytes': preview['current_bytes'], 'last_used': datetime.fromtimestamp(latest, timezone.utc).isoformat(),
                         'last_used_basis': 'latest_artifact_modification_not_access_time',
                         'regenerable_bytes': preview['regenerable_bytes'], 'protected_bytes': preview['preserved_bytes'],
                         'quarantine_bytes': preview['quarantine_bytes'], 'project_in_use': preview['project_in_use'],
                         'export_path': export_path, 'export_exists': exists, 'export_integrity': integrity,
                         'export_state': exported.get('state') or 'unavailable',
                         'reclaimable_bytes': preview['reclaimable_bytes'], 'read_only': True})
    return projects
