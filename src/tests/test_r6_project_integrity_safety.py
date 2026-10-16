"""Independent integrity and package-snapshot regressions; synthetic data only."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ldporto import second_curation_export
from ldporto.project_export import export_project, verify_project_export
from test_v43_handoff import analysis_fixture


def package(tmp_path, identifier='SNAPSHOT_A'):
    analysis = analysis_fixture()
    source_hash = hashlib.sha256(identifier.encode()).hexdigest()
    analysis['metadata']['sha256'] = source_hash
    analysis['metadata']['source'] = {
        'type': 'local', 'id': identifier, 'title': 'Synthetic snapshot ' + identifier
    }
    result = second_curation_export.build_core_package(
        analysis, output_dir=tmp_path / identifier)
    return Path(result['path']), source_hash


def manifest(root):
    path = root / 'PROJECT_MANIFEST.json'
    return path, json.loads(path.read_text(encoding='utf-8'))


def save_manifest(path, document):
    path.write_text(json.dumps(document), encoding='utf-8')


def refresh_file_inventory(root, document):
    """Model a repaired byte inventory while preserving semantic manifest fields."""
    rows = []
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.name not in {'PROJECT_MANIFEST.json', 'checksums.sha256'}:
            data = path.read_bytes()
            rows.append({'path': path.relative_to(root).as_posix(), 'bytes': len(data),
                         'sha256': hashlib.sha256(data).hexdigest()})
    checksums = root / '07_RELATORIOS_TECNICOS' / 'checksums.sha256'
    checksums.write_text(''.join(row['sha256'] + '  ' + row['path'] + '\n' for row in rows), encoding='utf-8')
    data = checksums.read_bytes()
    rows.append({'path': checksums.relative_to(root).as_posix(), 'bytes': len(data),
                 'sha256': hashlib.sha256(data).hexdigest()})
    document['files'] = rows
    save_manifest(root / 'PROJECT_MANIFEST.json', document)


def test_export_uses_the_bytes_that_were_validated_even_if_input_path_changes(tmp_path, monkeypatch):
    original, original_source = package(tmp_path, 'SNAPSHOT_A')
    replacement, _ = package(tmp_path, 'SNAPSHOT_B')
    original_bytes = original.read_bytes()
    replacement_bytes = replacement.read_bytes()
    real_validate = second_curation_export.validate_core_package
    swapped = False
    def replace_input_after_validation(path):
        nonlocal swapped
        result = real_validate(path)
        if not swapped:
            assert result['status'] == 'valid'
            original.write_bytes(replacement_bytes)
            swapped = True
        return result
    monkeypatch.setattr(second_curation_export, 'validate_core_package', replace_input_after_validation)
    result = export_project(original, tmp_path / 'Videos')
    root = Path(result['path'])
    _, data = manifest(root)
    assert original.read_bytes() == replacement_bytes  # The fixture performed the concurrent edit.
    assert data['source_sha256'] == original_source
    assert data['package_sha256'] == hashlib.sha256(original_bytes).hexdigest()
    assert (root / '06_SEGUNDA_CURADORIA' / 'SECOND_CURATION_READY.zip').read_bytes() == original_bytes


@pytest.mark.parametrize(('field', 'value'), [
    ('contract', 'unrelated.document'),
    ('schema_version', '999'),
    ('state', 'PUBLISH_READY'),
    ('source_video_included', True),
    ('final_social_videos_rendered', True),
])
def test_verifier_rejects_unknown_contract_state_and_unsupported_media_claims(tmp_path, field, value):
    source, _ = package(tmp_path)
    result = export_project(source, tmp_path / 'Videos')
    root = Path(result['path'])
    path, data = manifest(root)
    data[field] = value
    save_manifest(path, data)
    assert verify_project_export(root)['status'] == 'failed'


@pytest.mark.parametrize(('field', 'value'), [
    ('package_sha256', '0' * 64),
    ('source_sha256', '0' * 64),
    ('package_run_id', 'unrelated-run'),
])
def test_verifier_binds_manifest_to_the_included_package(tmp_path, field, value):
    source, _ = package(tmp_path)
    result = export_project(source, tmp_path / 'Videos')
    root = Path(result['path'])
    path, data = manifest(root)
    data[field] = value
    save_manifest(path, data)
    assert verify_project_export(root)['status'] == 'failed'


def test_reindexed_replacement_zip_is_not_the_original_project_package(tmp_path):
    source, _ = package(tmp_path, 'SNAPSHOT_A')
    other, _ = package(tmp_path, 'SNAPSHOT_B')
    result = export_project(source, tmp_path / 'Videos')
    root = Path(result['path'])
    _, data = manifest(root)
    copied = root / '06_SEGUNDA_CURADORIA' / 'SECOND_CURATION_READY.zip'
    copied.write_bytes(other.read_bytes())
    refresh_file_inventory(root, data)
    assert verify_project_export(root)['status'] == 'failed'


def test_manifest_leaf_reparse_is_rejected_before_read(tmp_path, monkeypatch):
    source, _ = package(tmp_path)
    result = export_project(source, tmp_path / 'Videos')
    root = Path(result['path'])
    manifest_path = root / 'PROJECT_MANIFEST.json'
    original_lstat = Path.lstat
    def reparse_stat(path, *args, **kwargs):
        stat = original_lstat(path, *args, **kwargs)
        if path == manifest_path:
            return SimpleNamespace(st_file_attributes=0x400, st_mode=stat.st_mode)
        return stat
    monkeypatch.setattr(Path, 'lstat', reparse_stat)
    assert verify_project_export(root)['status'] == 'failed'


def test_ready_manifest_with_only_arbitrary_file_is_not_a_complete_dossier(tmp_path):
    root = tmp_path / 'invented-dossier'
    root.mkdir()
    arbitrary = root / 'arbitrary.txt'
    arbitrary.write_bytes(b'synthetic unrelated content')
    save_manifest(root / 'PROJECT_MANIFEST.json', {
        'schema_version': '1.0', 'contract': 'ldporto.project_dossier',
        'state': 'READY_FOR_REVIEW', 'preview_approved': False, 'publication_ready': False,
        'source_video_included': False, 'final_social_videos_rendered': False,
        'files': [{'path': arbitrary.name, 'bytes': arbitrary.stat().st_size,
                   'sha256': hashlib.sha256(arbitrary.read_bytes()).hexdigest()}]
    })
    assert verify_project_export(root)['status'] == 'failed'


@pytest.mark.parametrize('required_path', [
    '00_RESUMO/GUIA_EDITORIAL_COMPLETO.pdf',
    '00_RESUMO/RESUMO_EXECUTIVO.pdf',
    '01_TRANSCRICAO/TRANSCRICAO_COMPLETA.pdf',
])
def test_generated_dossier_cannot_validate_with_required_pdf_missing(tmp_path, required_path):
    source, _ = package(tmp_path)
    result = export_project(source, tmp_path / 'Videos')
    root = Path(result['path'])
    _, data = manifest(root)
    assert data['pdf_status'] == 'GENERATED'
    (root / required_path).unlink()  # This test owns the isolated synthetic export.
    refresh_file_inventory(root, data)
    assert verify_project_export(root)['status'] == 'failed'


@pytest.mark.parametrize('incompatibility', ['extra_segment', 'duplicate_segment', 'orphan_word', 'other_run'])
def test_optional_analysis_must_be_a_compatible_canonical_snapshot(tmp_path, incompatibility):
    source, source_hash = package(tmp_path)
    analysis = analysis_fixture()
    analysis['metadata']['sha256'] = source_hash
    analysis['metadata']['source'] = {'type': 'local', 'id': 'SNAPSHOT_A', 'title': 'Synthetic snapshot SNAPSHOT_A'}
    if incompatibility == 'extra_segment':
        analysis['transcript_segments'].append({
            'segment_id': 'UNRELATED', 'start': 1, 'end': 2,
            'speaker': 'SP1', 'text': 'Synthetic extra segment absent from the package.'
        })
    elif incompatibility == 'duplicate_segment':
        analysis['transcript_segments'].append(dict(analysis['transcript_segments'][0]))
    elif incompatibility == 'orphan_word':
        analysis['words'] = [{
            'word_id': 'UNRELATED_WORD', 'segment_id': 'ABSENT_SEGMENT',
            'start': 1, 'end': 2, 'word': 'synthetic', 'speaker': 'SP1'
        }]
    else:
        analysis['run_manifest'] = {'run_id': 'UNRELATED_RUN'}
    before = source.read_bytes()
    with pytest.raises(ValueError):
        export_project(source, tmp_path / 'Videos', analysis=analysis)
    assert source.read_bytes() == before
