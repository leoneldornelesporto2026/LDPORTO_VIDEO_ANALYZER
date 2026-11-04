"""Offline Understanding-only replay from a CHATGPT_REVIEW_video_*.zip snapshot.

No YouTube/download, Whisper, video decode, diarization, tracking or Ollama.
This does NOT certify the full pipeline or overwrite any existing checkpoint.

Example (from project root):
    python scripts/dev/replay_understanding_snapshot.py REVIEW.zip --output-dir replay_understanding
"""
import argparse
import json
import logging
import sys
from pathlib import Path
from zipfile import ZipFile

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from ldporto.config import load_config
from ldporto.core import Context, write_json
from ldporto.understanding import run_understanding


def replay(review_zip, output_dir, fixture_output=None):
    review_zip, output_dir = Path(review_zip), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(review_zip) as source:
        names = set(source.namelist())
        roots = [name.removesuffix('analysis.json') for name in names
                 if name.startswith('analysis/') and name.endswith('/analysis.json')]
        if len(roots) != 1:
            raise ValueError('Exactly one analysis/*/analysis.json is required')
        root = roots[0]
        def read(name, default=None):
            path = root + name
            return json.loads(source.read(path)) if path in names else default
        doc = read('analysis.json')
        metadata = doc['metadata']
        if not isinstance(metadata, dict) or not metadata.get('duration'):
            raise ValueError('Missing snapshot source metadata')
        transcript = {'segments': read('transcript_segments.json', []), 'words': read('words.json', [])}
        semantic = {'topics': read('topics.json', []), 'moments': read('editorial_moments.json', []),
                    'questions_answers': read('questions_answers.json', []),
                    'program_sections': read('program_sections.json', []),
                    'editorial_review': doc.get('ollama_editorial_review')}
        diarization = {'speakers': read('speakers.json', [])}
        vision = {'people': read('people.json', []), 'observations': [], 'thumbnails': []}
        shots = read('shots.json', [])
        active = {'mapping_summary': []}
    cfg = load_config()
    cfg['understanding']['extract_frames'] = False
    logger = logging.getLogger('understanding-snapshot-replay')
    ctx = Context(output_dir / '_source_not_needed.mp4', output_dir, cfg, 'offline-understanding-replay', logger)
    result = run_understanding(ctx, metadata, transcript, diarization, vision, active,
                               semantic, shots, cfg['understanding'])
    data = result['data']
    summary = {
        'execution_scope': 'offline_review_snapshot_understanding_only',
        'source_id': root.split('/')[1],
        'status': result['status'],
        'source_segments': len(transcript['segments']),
        'semantic_moments': len(semantic['moments']),
        'story_arcs': len(data['story_arcs']),
        'entities': len(data['entities']),
        'main_moments': len(data['main_moments']),
        'shortlist': len(data['editorial_shortlist']),
        'duration_exceptions': sum(row.get('duration_exception', False) for row in data['main_moments']),
        'missing_proof_exceptions': sum(not row.get('duration_exception_evidence') for row in data['main_moments']
                                        if row.get('duration_exception')),
        'contract_diagnostics_path': 'understanding_contract_diagnostics.json',
        'video_pipeline_reexecuted': False,
        'requires_full_cache_replay_on_windows': True,
    }
    write_json(output_dir / 'replay_summary.json', summary)
    if fixture_output:
        # Keep the fixture tiny and free of video transcripts: authentic IDs,
        # source boundaries and proof values are enough for duration regression.
        exceptions = [row for row in data['main_moments'] if row.get('duration_exception')]
        chosen = exceptions[:1] or data['main_moments'][:1]
        write_json(fixture_output, {
            'source_id': summary['source_id'],
            'source_segments': len(transcript['segments']),
            'source_semantic_moments': len(semantic['moments']),
            'cases': [{key: candidate.get(key) for key in (
                'moment_id', 'ideal_start', 'ideal_end', 'boundary_segment_ids',
                'duration_exception', 'duration_exception_evidence', 'clean_opening',
                'clean_ending', 'context_requirement', 'hook_score', 'standalone_score')}
                for candidate in chosen],
        })
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('review_zip')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--fixture-output', help='Optional minimal ID-only regression fixture')
    arguments = parser.parse_args()
    print(json.dumps(replay(arguments.review_zip, arguments.output_dir, arguments.fixture_output), ensure_ascii=False, indent=2))
