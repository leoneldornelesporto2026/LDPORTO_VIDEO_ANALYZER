"""Bounded canary preview + rendered-frame verification integration."""
from pathlib import Path
from .core import ok, digest
from .preview_renderer import render_preview, select_canary_intervals
from .preview_verifier import verify_preview, conservative_repair

PREVIEW_CODE = ['preview_renderer.py','preview_verifier.py','preview_integration.py','core.py']


def build_preview_package(ctx, metadata, director, cfg):
    if not cfg.get('enabled'):
        return ok({'canaries': [], 'validation': {'schema_version':'1.0','issues':[], 'status':'skipped', 'verifier_uses_rendered_frames':False},
                   'closed_loop': {'attempted': False}}, 'skipped')
    timeline = director.get('timeline', [])
    if not timeline:
        return ok({'canaries': [], 'validation': {'schema_version':'1.0','issues':[]},
                   'closed_loop': {'attempted': False}}, 'unavailable', ['Camera Director sem timeline para preview.'])
    if not Path(ctx.video).is_file():
        return ok({'canaries': [], 'validation': {'schema_version':'1.0', 'issues':[], 'status':'unavailable',
                   'verifier_uses_rendered_frames':False, 'unresolved_reason':'source_media_unavailable'},
                   'closed_loop': {'attempted': False, 'iterations':0, 'repair_accepted':False,
                                   'repaired_director_ids':[], 'second_validation':None},
                   'repaired_timeline':None}, 'unavailable', ['Source media unavailable; no rendered-frame verification was performed.'])
    intervals = select_canary_intervals(timeline, metadata.get('duration') or 0,
                                        int(cfg.get('max_canaries', 4)), float(cfg.get('canary_seconds', 4.0)))
    preview_dir = ctx.output/'previews'
    preview_dir.mkdir(parents=True, exist_ok=True)
    canaries, all_issues, artifacts = [], [], []
    for i, interval in enumerate(intervals):
        target = preview_dir/f'canary_{i:02d}.mp4'
        rendered = render_preview(ctx.video, timeline, metadata, target, interval,
                                  int(cfg.get('output_width', 540)), int(cfg.get('output_height', 960)))
        item = {'canary_id':f'CANARY_{i:02d}','interval':interval,'render':rendered.get('data',{}),
                'render_status':rendered.get('status')}
        if rendered.get('status') == 'ok':
            artifacts.extend(rendered.get('artifacts', []))
            validation = verify_preview(target, {'width':cfg.get('output_width',540),
                                                 'height':cfg.get('output_height',960),
                                                 'source_start':interval['start'],
                                                 'duration':interval['end']-interval['start']}, timeline)
            data = validation.get('data', {})
            for issue in data.get('issues', []):
                issue['interval'] = [interval['start'], interval['end']]
                issue['canary_id'] = item['canary_id']
            item['validation'] = data
            item['validation_status'] = validation.get('status')
            item['accepted_preview_path'] = str(target) if validation.get('status') == 'ok' else None
            all_issues.extend(data.get('issues', []))
        else:
            item['validation'] = {'issues': [{'severity':'error','issue_type':'PREVIEW_RENDER_FAILED',
                                             'evidence': {'canary_id': item['canary_id']}}]}
            all_issues.extend(item['validation']['issues'])
            item['validation_status'] = 'unavailable'
        canaries.append(item)
    validation = {'schema_version':'1.0','issues':all_issues,'issue_count':len(all_issues),
                  'canary_count':len(canaries),'verifier_uses_rendered_frames':any(item.get('validation',{}).get('verifier_uses_rendered_frames') for item in canaries),
                  'status':'partial' if all_issues or any(item['validation_status'] != 'ok' for item in canaries) else 'ok'}
    repaired_timeline, repaired_ids = timeline, []
    attempted = False
    second_validation = None
    max_repairs = max(0, int(cfg.get('max_repair_iterations', 1)))
    if all_issues and max_repairs:
        repaired_timeline, repaired_ids = conservative_repair(timeline, validation)
        attempted = bool(repaired_ids)
        if attempted:
            second_issues = []
            successful_rechecks = 0
            for i, interval in enumerate(intervals):
                target = preview_dir/f'canary_{i:02d}_repaired.mp4'
                rerender = render_preview(ctx.video, repaired_timeline, metadata, target, interval,
                                          int(cfg.get('output_width', 540)), int(cfg.get('output_height', 960)))
                if rerender.get('status') == 'ok':
                    artifacts.extend(rerender.get('artifacts', []))
                    recheck = verify_preview(target, {'width':cfg.get('output_width',540),
                                                      'height':cfg.get('output_height',960),
                                                      'source_start':interval['start'],
                                                      'duration':interval['end']-interval['start']}, repaired_timeline)
                    for issue in recheck.get('data',{}).get('issues',[]):
                        issue['interval'] = [interval['start'], interval['end']]
                        issue['canary_id'] = f'CANARY_{i:02d}_REPAIRED'
                    second_issues.extend(recheck.get('data',{}).get('issues',[]))
                    successful_rechecks += int(recheck.get('status') == 'ok' and recheck.get('data',{}).get('sampled_frames',0) > 0)
                    canaries[i]['repaired_validation'] = recheck.get('data', {})
                    canaries[i]['accepted_preview_path'] = str(target) if recheck.get('status') == 'ok' and recheck.get('data',{}).get('sampled_frames',0) > 0 else None
                else:
                    second_issues.append({'severity':'error','issue_type':'PREVIEW_REPAIR_RENDER_FAILED',
                                          'evidence': {'canary_id': f'CANARY_{i:02d}_REPAIRED'}})
            second_validation = {'schema_version':'1.0','issues':second_issues,
                                 'issue_count':len(second_issues),'verifier_uses_rendered_frames':successful_rechecks > 0,
                                 'successful_rechecks':successful_rechecks, 'expected_rechecks':len(intervals)}
    status = 'partial' if any(c.get('validation_status') in ('partial','unavailable') for c in canaries) else 'ok'
    repair_accepted = bool(attempted and second_validation and not second_validation['issues'] and
                           second_validation['successful_rechecks'] == len(intervals))
    if repair_accepted:
        status = 'ok'
    final_validation = {**second_validation, 'status':'ok', 'canary_count':len(canaries), 'source_preserving_repair_used':True} if repair_accepted else validation
    return ok({'canaries':canaries,'validation':final_validation, 'initial_validation':validation,
               'closed_loop':{'attempted':attempted,'iterations':1 if attempted else 0, 'repair_accepted':repair_accepted,
                              'repaired_director_ids':repaired_ids,
                              'second_validation':second_validation},
               'repaired_timeline':repaired_timeline if repair_accepted else None}, status,
              ['Canary previews validam casos de risco; vídeo completo não é renderizado nesta etapa.'], artifacts)


def run_preview_stage(ctx, metadata, director, cfg):
    params = {'config':cfg,'schema':'1.0','director':digest(director.get('timeline', []))}
    result = ctx.step('19b_preview_verifier', params, lambda: build_preview_package(ctx, metadata, director, cfg),
                      code_files=PREVIEW_CODE, output_version='1.0', requires=['19_camera_director'] if cfg.get('enabled') else [])
    return result
