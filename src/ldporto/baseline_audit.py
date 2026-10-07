"""Reconcile stored measurements without changing historical evidence."""
import hashlib
import json
import re
from pathlib import Path


def reconcile_tracking_counters(people, tracks, log_time=None, logged_count=None):
    raw_ids = {row['person_id'] for row in people}
    track_source_ids = {pid for row in tracks for pid in row.get('source_person_ids', [])}
    at_log = sum(row.get('first_seen', float('inf')) <= log_time for row in people) if log_time is not None else None
    return {'logged_video_time_seconds': log_time, 'logged_raw_person_hypotheses': logged_count,
            'reconstructed_raw_person_hypotheses_at_log': at_log,
            'log_counter_verified': at_log == logged_count if at_log is not None else None,
            'final_raw_person_hypotheses': len(raw_ids), 'final_raw_tracklets': len(tracks),
            'valid_tracklets': sum(bool(row.get('qualified')) for row in tracks),
            'micro_tracklets': sum(not row.get('qualified') for row in tracks),
            'additional_tracklets_for_existing_hypotheses': len(tracks) - len(track_source_ids),
            'new_hypotheses_after_last_log': len(raw_ids) - at_log if at_log is not None else None,
            'counter_definitions': {
                'log': 'VisionEngine len(people): cumulative anonymous online person_id hypotheses at this timestamp; NOT track_id count.',
                'raw_tracklets': 'Re-ID input grouped by distinct track_id, including micro tracklets.',
                'valid_tracklets': 'Observed visual seconds and sample count pass configured Re-ID qualification.',
                'final_people': 'Post-Re-ID anonymous persistent identities; NOT annotated unique humans.',
                'reappearances': 'Online gallery can reuse person_id after a shot/occlusion while allocating a NEW track_id.'}}


def audit_baseline(folder):
    folder = Path(folder)
    def read(name):
        return json.loads((folder / name).read_text(encoding='utf-8-sig'))
    summary, quality = read('analysis_summary.json'), read('analysis_quality.json')
    logs = folder / 'logs' / 'analyzer.log'
    matches = re.findall(r'Visão:\s*([\d.]+)\s*/\s*[\d.]+s;\s*(\d+) tracks',
                         logs.read_text(encoding='utf-8-sig') if logs.exists() else '')
    stamp, count = (float(matches[-1][0]), int(matches[-1][1])) if matches else (None, None)
    counters = reconcile_tracking_counters(read('raw_people.json'), read('raw_tracks.json'), stamp, count)
    counters['final_persistent_identities'] = quality.get('persistent_person_count')
    keys = ('raw_track_count', 'valid_track_count', 'micro_track_count', 'micro_track_ratio',
            'speaker_person_mapping_coverage', 'active_speaker_coverage', 'resolved_focus_coverage',
            'zoom_event_count', 'semantic_fallback_ratio', 'story_payoff_coverage',
            'candidates_before_dedup', 'final_shortlist_count')
    return {'schema_version': '1.0', 'execution_scope': summary.get('execution_scope'),
            'producer_version': summary.get('producer_version'), 'metadata': summary['metadata'],
            'analysis_status': summary.get('analysis_status'), 'tracking_counters': counters,
            'baseline_metrics': {key: quality.get(key) for key in keys},
            'stage_runtime': summary.get('stage_runtime', {}),
            'evidence_checksums': {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                                   for name in ('analysis_summary.json', 'analysis_quality.json', 'raw_tracks.json', 'raw_people.json')}}
