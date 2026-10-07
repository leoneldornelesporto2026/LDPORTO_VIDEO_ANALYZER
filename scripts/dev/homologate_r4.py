"""R4 release acceptance: validate second-curation ZIP and optional actual preview/analysis.

Does NOT approve uploads, assess editorial accuracy or change pipeline caches.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ldporto.curator_bridge import audit_second_curation_package


def inspect_preview(path):
    """Measure actual MP4 video/audio streams; not subjective crop/ASR correctness."""
    media = Path(path)
    result = {'path': str(media), 'file_present': media.is_file(), 'render_quality_approved': False}
    if not media.is_file() or not shutil.which('ffprobe'):
        result['error'] = 'video_missing' if not media.is_file() else 'ffprobe_unavailable'
        return result
    p = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                        'format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate',
                        '-of', 'json', str(media)], capture_output=True, text=True, timeout=45)
    if p.returncode:
        result['error'] = 'ffprobe_failed'
        result['details'] = p.stderr[-500:]
        return result
    data = json.loads(p.stdout)
    streams = data.get('streams') or []
    videos = [x for x in streams if x.get('codec_type') == 'video']
    audios = [x for x in streams if x.get('codec_type') == 'audio']
    duration = float(data.get('format', {}).get('duration') or 0)
    result.update(video_streams=len(videos), audio_streams=len(audios), duration_seconds=duration,
                  width=videos[0].get('width') if videos else None,
                  height=videos[0].get('height') if videos else None,
                  container_bytes=int(data.get('format', {}).get('size') or 0),
                  portrait_9_16=bool(videos and abs(videos[0].get('width', 0) / max(1, videos[0].get('height', 1)) - 9/16) < .01),
                  technical_streams_ok=bool(videos and audios and duration > 0))
    # ffprobe cannot certify face selection, legibility, safe area or synchronized lyrics.
    result['manual_inspection_required'] = ['face_target', 'safe_caption_area', 'subtitle_accuracy',
                                             'commercial_context', 'scene_changes', 'audio_sync']
    return result


def inspect_analysis(path):
    source = Path(path)
    if source.is_dir():
        source = source / 'analysis.json'
    if not source.is_file():
        return {'available': False, 'reason': 'analysis_json_missing'}
    data = json.loads(source.read_text(encoding='utf-8'))
    states = data.get('stage_status') or {}
    status_summary = {k: v.get('status', 'unknown') for k, v in states.items() if isinstance(v, dict)}
    failed = {k: value for k, value in status_summary.items() if value in ('failed', 'blocked', 'cancelled')}
    quality = data.get('analysis_quality') or {}
    interesting = ('micro_track_ratio', 'speaker_person_mapping_coverage', 'active_speaker_coverage',
                   'resolved_focus_coverage', 'zoom_event_count', 'zoom_delivered_event_count')
    return {'available': True, 'analysis_status': data.get('analysis_status'),
            'stage_count': len(status_summary), 'failed_or_blocked_stages': failed,
            'understanding_status': status_summary.get('16_understanding', 'unknown'),
            'tracked_quality_signals': {key: quality[key] for key in interesting if key in quality},
            'editorial_upstream_healthy': status_summary.get('16_understanding') in ('ok','partial')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', help='Full second-curation ZIP')
    parser.add_argument('--preview', help='Actual rendered MP4 to inspect streams')
    parser.add_argument('--analysis', help='Original full Analyzer analysis.json or its directory')
    parser.add_argument('--report', required=True, help='Destination JSON report')
    args = parser.parse_args()
    if not any((args.package, args.preview, args.analysis)):
        parser.error('Provide --package, --preview and/or --analysis')
    report = {'schema_version': '1.0', 'release_phase': 'R4_homologation',
              'ready_to_publish': False, 'final_human_approval_required': True,
              'environment': {'python': sys.version.split()[0], 'windows_target': 'Windows 10/11 Python 3.11',
                              'target_runtime_confirmed': sys.platform == 'win32' and sys.version_info[:2] == (3,11)}}
    if args.package:
        report['second_curation_package'] = audit_second_curation_package(args.package)
    if args.preview:
        report['preview'] = inspect_preview(args.preview)
    if args.analysis:
        report['analysis'] = inspect_analysis(args.analysis)
    missing = []
    if not report['environment']['target_runtime_confirmed']:
        missing.append('Windows/Python3.11_homologation')
    if 'second_curation_package' in report and not report['second_curation_package']['bridge_possible']:
        missing.append('second_curation_ready_package')
    if 'preview' in report and not report['preview'].get('technical_streams_ok'):
        missing.append('valid_preview_video_audio')
    if 'analysis' in report and not report['analysis'].get('editorial_upstream_healthy'):
        missing.append('complete_understanding_stage')
    missing.extend(('manual_editorial_review', 'manual_subtitle_review', 'manual_camera_review', 'Curator_first_preview_approval'))
    report['pending_acceptance_criteria'] = missing
    destination = Path(args.report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
