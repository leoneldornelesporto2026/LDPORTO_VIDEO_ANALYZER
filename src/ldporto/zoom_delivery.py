"""Separate executable/rendered transforms from final-frame proof of zoom delivery."""
from collections import Counter
from .core import digest


def timeline_zoom_span(row, start, end):
    """Measure the executable keyframe curve inside this proposal only."""
    keys = sorted((k for k in (row.get('camera') or {}).get('keyframes', [])
                   if isinstance(k.get('time'), (int, float))), key=lambda k: k['time'])
    if len(keys) < 2:
        return 0.
    a, b = max(start, row['start']), min(end, row['end'])
    if a >= b:
        return 0.
    def at(t):
        if t <= keys[0]['time']:
            return keys[0].get('zoom', 1.)
        for left, right in zip(keys, keys[1:]):
            if t <= right['time']:
                fraction = (t-left['time']) / max(right['time']-left['time'], 1e-12)
                return left.get('zoom', 1.) + fraction*(right.get('zoom', 1.)-left.get('zoom', 1.))
        return keys[-1].get('zoom', 1.)
    values = [at(a), at(b)] + [k.get('zoom', 1.) for k in keys if a < k['time'] < b]
    return max(values)-min(values)


def delivery_report(proposals, timeline, canaries=()):
    signature = digest(timeline)
    outcomes = []
    for index, proposal in enumerate(proposals or []):
        start, end = proposal['start'], proposal['end']
        target = proposal.get('target_person_id')
        rows = [r for r in timeline if r['start'] < end and r['end'] > start
                and r.get('focus_person') == target and target
                and r.get('camera_mode') == proposal.get('mode')
                and r.get('layout') in ('single_person', 'two_shot')]
        executable = [r for r in rows if r.get('director_id') and (r.get('crop') or {}).get('safe') is True
                      and len((r.get('camera') or {}).get('keyframes', [])) >= 2
                      and timeline_zoom_span(r, start, end) > .001]
        reasons, receipts = set(), []
        rendered_support, decoded_support = False, False
        if not executable:
            reasons.add('no_render_timeline_support')
            for row in timeline:
                if row['start'] < end and row['end'] > start:
                    reasons.update((row.get('decision') or {}).get('reasons', []))
        for item in canaries:
            render = item.get('repaired_render') if item.get('repaired_validation') is not None else item.get('render')
            validation = item.get('repaired_validation') if item.get('repaired_validation') is not None else item.get('validation')
            render, validation = render or {}, validation or {}
            interval = item.get('interval') or {}
            canary_start = render.get('start', interval.get('start'))
            canary_end = render.get('end', interval.get('end'))
            if (canary_start is not None and canary_end is not None and
                    (canary_start >= end or canary_end <= start)):
                continue
            if (render.get('timeline_sha256') != signature or not render.get('preview_sha256')
                    or validation.get('preview_sha256') != render.get('preview_sha256')
                    or not validation.get('verifier_uses_rendered_frames') or validation.get('sampled_frames', 0) <= 0):
                continue
            decoded_support = True
            blocking = {'FACE_OR_HEAD_CLIPPED': 'head_clipping', 'UNEXPECTED_BORDER': 'border',
                        'UPSCALE_LIMIT_VIOLATION': 'low_res', 'ZOOM_TARGET_LOST': 'no_support'}
            failures = {blocking[i['issue_type']] for i in validation.get('issues', []) if i.get('issue_type') in blocking}
            if failures:
                reasons.update(failures)
                continue
            for receipt in render.get('rendered_motion', []):
                if (receipt.get('director_id') not in {r.get('director_id') for r in executable}
                        or receipt.get('target_person_id') != target or receipt.get('mode') != proposal.get('mode')
                        or receipt.get('first_time', end) >= end or receipt.get('last_time', start) <= start
                        or receipt.get('frames', 0) < 2):
                    continue
                # Require effective crop scale motion inside this proposal's interval,
                # not just zoom-valued keyframes or a static enlarged crop.
                relevant = [p for p in receipt.get('scale_samples', []) if start <= p[0] < end]
                direction = 1 if proposal.get('mode') == 'SMART_ZOOM_IN' else -1
                if len(relevant) >= 2 and direction * (relevant[-1][1] - relevant[0][1]) > .001:
                    rendered_support = True
                    receipts.append({'canary_id': item.get('canary_id'), 'preview_sha256': render['preview_sha256'],
                                     'director_id': receipt.get('director_id'), 'sampled_frames': validation['sampled_frames']})
        rendered = bool(executable and receipts)
        # The current Preview Verifier checks decoded-frame safety, but does not
        # measure source-aligned scale motion in the final frames. A renderer
        # receipt alone cannot prove perceptible motion (a flat frame is a
        # concrete counterexample). Keep the final delivery gate unresolved.
        delivered = False
        if rendered:
            reasons.add('final_frame_motion_unverified')
        elif executable and not reasons:
            reasons.add('no_verified_preview_motion')
        outcomes.append({'proposal_id': index, 'start': start, 'end': end, 'target_person_id': target,
                         'render_timeline_supported': bool(executable), 'rendered': rendered, 'delivered': delivered,
                         'evidence_stages': {'focus_proposed': bool(target),
                             'crop_geometrically_valid': any((r.get('crop') or {}).get('safe') is True for r in rows),
                             'motion_preflight_supported': any((r.get('crop') or {}).get('safe') is True and
                                 ((r.get('crop') or {}).get('preflight_sample_count') or 0) >= 2 for r in rows),
                             'movement_present_in_timeline': bool(executable),
                             'render_transform_motion_received': rendered_support,
                             'preview_frames_decoded': decoded_support,
                             'movement_confirmed_in_final_frames': None},
                         'reason_codes': [] if delivered else sorted(reasons), 'receipts': receipts})
    count = sum(r['delivered'] for r in outcomes)
    rendered_count = sum(r['rendered'] for r in outcomes)
    return {'zoom_delivered_event_count': count, 'zoom_delivery_verified': None,
            'rendered_zoom_event_count': rendered_count,
            'render_transform_receipts_verified': True if rendered_count else None,
            'zoom_delivery_fraction': count / len(outcomes) if outcomes else None,
            'proposal_outcomes': outcomes, 'undelivered_reason_counts': dict(Counter(
                reason for row in outcomes for reason in row['reason_codes'])),
            'timeline_sha256': signature, 'proof_scope': 'render_transform_and_decoded_safety_not_final_frame_motion_proof',
            'delivery_contract': 'r6_final_frame_motion_evidence_required',
            'motion_measurement_source': 'renderer_effective_transform_receipt_with_decoded_preview_safety_checks',
            'final_frame_motion_analysis_executed': False,
            'preview_approved': None, 'publish_ready': False}
