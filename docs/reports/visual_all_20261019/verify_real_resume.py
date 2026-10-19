"""Read-only guards on source evidence; creates a separate resumed delivery."""
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto import visual_scenes_export as exporter


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(paths):
    result = {}
    for path in paths:
        files = sorted(path.rglob('*')) if path.is_dir() else [path]
        for file in files:
            if file.is_file():
                result[str(file.relative_to(ROOT))] = {
                    'sha256': sha(file), 'bytes': file.stat().st_size,
                    'mtime_ns': file.stat().st_mtime_ns,
                }
    return result


def main():
    output = ROOT / 'pacotes_para_enviar/VISUAL_ALL_pc6SR_Fvdt0_20261019'
    analysis = ROOT / 'analysis/video_d96cd4328fd5'
    source = ROOT / 'input/youtube/pc6SR_Fvdt0/pc6SR_Fvdt0.mp4'
    parent = ROOT / 'pacotes_para_enviar/SECOND_CURATION_PARTIAL_pc6SR_Fvdt0_20261019_032257_115420_b77577.zip'
    protected = [source, parent, *(analysis / name for name in (
        'analysis_summary.json', 'scenes.json', 'shots.json',
        'transcript_segments.json', 'words.json')),
        *(output / name for name in ('visual_assets', 'capture_cache', 'moment_sheet_cache'))]
    before = snapshot(protected)
    with patch.object(exporter, '_Capture', side_effect=AssertionError('source decoder forbidden on resume')) as decoder, \
            patch('ldporto.preview_renderer.build_contact_sheet', side_effect=AssertionError('moment renderer forbidden on resume')) as renderer:
        result = exporter.reexport_all_scenes(analysis, parent, source, output)
    after = snapshot(protected)
    assert before == after, 'protected evidence/cache bytes or modification time changed'
    assert result['last_visual_execution'] == {'new_captures': 0, 'reused_complete_export': True}
    assert result['validation']['status'] == 'valid'
    assert result['export_status'] == 'COMPLETE'
    report = {
        'status': 'PASS', 'scope': 'actual persisted 66.194-second source and parent ZIP',
        'source_decoder_calls': decoder.call_count, 'moment_renderer_calls': renderer.call_count,
        'protected_file_count': len(before), 'protected_bytes_and_mtime_unchanged': before == after,
        'last_visual_execution': result['last_visual_execution'],
        'resumed_zip_path': result['path'], 'resumed_zip_sha256': result['sha256'],
        'resumed_zip_bytes': result['bytes'], 'zip_validation_status': result['validation']['status'],
        'statistics': result['statistics'], 'source_sha256': result['source_sha256'],
        'parent_zip_sha256': result['parent_package_sha256'], 'pdfs': result['pdfs'],
        'protected_files': after,
    }
    target = Path(__file__).with_name('REAL_RESUME_PROOF.json')
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'protected_files'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
