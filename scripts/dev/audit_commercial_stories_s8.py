"""S8 offline diagnostic from the actual existing analysis folder or ZIP.

No media/LLM/OCR rerun. Sources: stage checkpoints, analysis.json,
main_moments and saved visual/stories files. No invented validation outcomes.
"""
import argparse
import csv
import json
import sys
import zipfile
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.commercial_gate import apply_commercial_refinement


def _load(source, *names):
    source = Path(source)
    if source.is_dir():
        for name in names:
            paths = sorted(source.rglob(name), key=lambda x: (len(x.parts), str(x)))
            for p in paths:
                if p.is_file() and not p.is_symlink():
                    try: return json.loads(p.read_text(encoding='utf-8-sig'))
                    except (json.JSONDecodeError, UnicodeDecodeError): pass
    elif source.suffix.lower() == '.zip':
        with zipfile.ZipFile(source) as archive:
            available = archive.namelist()
            for name in names:
                hits = sorted((p for p in available if p == name or p.endswith('/'+name)),
                              key=lambda x: (x.count('/'), x))
                for hit in hits:
                    info = archive.getinfo(hit)
                    if info.file_size > 64*1024*1024: continue
                    try: return json.loads(archive.read(hit).decode('utf-8-sig'))
                    except (json.JSONDecodeError, UnicodeDecodeError): pass
    return None


def _data(value):
    return value.get('data', value) if isinstance(value, dict) else value


def audit(source, output):
    source = Path(source)
    if not source.exists(): raise FileNotFoundError(source)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    raw = _data(_load(source, 'analysis.json') or {})
    segments = _data(_load(source, 'transcript_segments.json', '04_transcription.json') or
                     raw.get('transcript_segments') or [])
    if isinstance(segments, dict): segments = segments.get('segments') or []
    understanding = _data(_load(source, '17c_commercial_visual.json') or {})
    moments = _data(_load(source, 'main_moments.json', '16_understanding.json') or raw.get('main_moments') or [])
    if isinstance(moments, dict): moments = moments.get('main_moments') or []
    raw_ocr = _data(_load(source, 'commercial_visual_s8.json', '17c_commercial_visual.json') or
                    raw.get('commercial_visual_s8') or {})
    texts = raw_ocr.get('texts', []) if isinstance(raw_ocr, dict) else []
    visual = _data(_load(source, 'broadcast_graphics.json', '17b_broadcast_graphics.json') or
                   raw.get('broadcast_graphics') or {})
    social = _data(_load(source, 'social_output.json', 'stories_manifest.json') or raw.get('social_output') or {})
    if not isinstance(segments, list) or not isinstance(moments, list):
        raise ValueError('Invalid transcript/candidates saved format. No fabricated measures.')
    # S8 recomputation only if there is canonical text evidence; keep original
    # recorded decisions independently for comparisons.
    reevaluation = apply_commercial_refinement({'main_moments': moments}, segments, texts, {'max_moments': 12}) if segments and moments else {}
    by_id = {str(row.get('moment_id')): row for row in reevaluation.get('main_moments', [])}
    original = Counter((row.get('commercial_classification') or {}).get('eligibility', 'unknown') for row in moments)
    status = Counter((row.get('commercial_classification') or {}).get('eligibility', 'unknown') for row in by_id.values())
    rows = []
    for row in moments:
        cid = str(row.get('moment_id') or row.get('candidate_id') or '')
        changed = by_id.get(cid) or {}
        rows.append({'moment_id':cid, 'start':row.get('ideal_start',row.get('start')),
                     'end':row.get('ideal_end',row.get('end')),
                     'previous_eligibility':(row.get('commercial_classification') or {}).get('eligibility','unknown'),
                     'rechecked_eligibility':(changed.get('commercial_classification') or {}).get('eligibility', 'not_rechecked'),
                     'linked_blocks': ';'.join(changed.get('commercial_block_refs') or []),
                     'commercial_gate_reason':changed.get('commercial_gate_reason') or '',
                     'manual_label':'', 'reviewer':'', 'reviewed_media':'', 'notes':''})
    with (output/'commercial_human_review_s8.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ['moment_id','manual_label','reviewer','reviewed_media','notes'])
        writer.writeheader();writer.writerows(rows)
    graphics_intervals = visual.get('intervals', []) if isinstance(visual, dict) else []
    stories = social.get('stories', []) if isinstance(social, dict) else []
    diagnostics = {'schema':'S8', 'scope':'saved_evidence_only_no_media_rerun',
        'source_has_canonical_segments':bool(segments), 'source_has_candidates':bool(moments),
        'candidates_count':len(moments),'recorded_eligibility':dict(original),'rechecked_eligibility':dict(status),
        'confirmed_commercial_blocks_from_asr':reevaluation.get('commercial_blocks', []),
        'ocr':{'status':raw_ocr.get('status','not_present') if isinstance(raw_ocr,dict) else 'not_present',
               'observation_count':len(texts),'continuity_unverified':True},
        'broadcast_graphics':{'status':visual.get('status','not_present') if isinstance(visual,dict) else 'not_present',
                              'sampled_interval_count':len(graphics_intervals),
                              'regions_found':sum(len(r.get('regions') or []) for r in graphics_intervals)},
        'stories':{'count':len(stories),'titles_pending_human_review':sum(row.get('requires_curator_review', True) for row in stories),
                   'full_video_diversity_available':bool(stories)},
        'limitations':['Cannot prove commercial-gate recall without manually labelled video.',
                       'OCR observations do not establish duration of on-screen overlay.',
                       'Cannot validate GC placements without rendered previews.',
                       'Audio-event model not rerun; disabled/absent does not imply no laughter.']}
    (output/'commercial_stories_s8_audit.json').write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2),encoding='utf-8')
    return diagnostics


def main():
    ap=argparse.ArgumentParser(description='Audit commercial / graphics / stories from saved analysis (no media rerun).')
    ap.add_argument('source',help='Analysis directory or saved review ZIP')
    ap.add_argument('--output',required=True)
    args=ap.parse_args()
    report=audit(args.source,args.output)
    print(json.dumps({'status':'audit_created','candidates':report['candidates_count'],
                      'has_saved_segments':report['source_has_canonical_segments'],
                      'output':str(Path(args.output).resolve())},ensure_ascii=False))

if __name__=='__main__': main()
