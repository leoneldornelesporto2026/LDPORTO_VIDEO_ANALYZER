"""Delivery requires executable motion, a render receipt and decoded preview bytes."""
from collections import Counter
from .core import digest


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
                      and max(k.get('zoom', 1) for k in r['camera']['keyframes'])
                      - min(k.get('zoom', 1) for k in r['camera']['keyframes']) > .001]
        reasons, receipts = set(), []
        if not executable:
            reasons.add('no_render_timeline_support')
            for row in timeline:
                if row['start'] < end and row['end'] > start:
                    reasons.update((row.get('decision') or {}).get('reasons', []))
        for item in canaries:
            render = item.get('repaired_render') if item.get('repaired_validation') is not None else item.get('render')
            validation = item.get('repaired_validation') if item.get('repaired_validation') is not None else item.get('validation')
            render, validation = render or {}, validation or {}
            if (render.get('timeline_sha256') != signature or not render.get('preview_sha256')
                    or validation.get('preview_sha256') != render.get('preview_sha256')
                    or not validation.get('verifier_uses_rendered_frames') or validation.get('sampled_frames', 0) <= 0):
                continue
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
                    receipts.append({'canary_id': item.get('canary_id'), 'preview_sha256': render['preview_sha256'],
                                     'director_id': receipt.get('director_id'), 'sampled_frames': validation['sampled_frames']})
        delivered = bool(executable and receipts)
        if not delivered and executable and not reasons:
            reasons.add('no_verified_preview_motion')
        outcomes.append({'proposal_id': index, 'start': start, 'end': end, 'target_person_id': target,
                         'render_timeline_supported': bool(executable), 'delivered': delivered,
                         'reason_codes': [] if delivered else sorted(reasons), 'receipts': receipts})
    count = sum(r['delivered'] for r in outcomes)
    return {'zoom_delivered_event_count': count, 'zoom_delivery_verified': True if count else None,
            'zoom_delivery_fraction': count / len(outcomes) if outcomes else None,
            'proposal_outcomes': outcomes, 'undelivered_reason_counts': dict(Counter(
                reason for row in outcomes for reason in row['reason_codes'])),
            'timeline_sha256': signature, 'proof_scope': 'sampled_technical_render_motion_not_full_event_or_identity_accuracy',
            'preview_approved': None, 'publish_ready': False}
