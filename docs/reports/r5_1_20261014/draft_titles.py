"""Auditable assisted editorial draft, not an Ollama inference or human approval."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
from ldporto.core import digest, file_hash
from ldporto.semantic_runtime import atomic_json
from ldporto.semantic_package import read_package, decoded_documents, validate_semantic_artifacts
from ldporto.semantic_replay import _load_artifacts, _checkpoint
from ldporto.story_visual_handoff import build_story_visual_handoff

REPORT = Path(__file__).resolve().parent
output = REPORT/'semantic_replay'
state = json.loads((output/'semantic_state.json').read_text(encoding='utf-8'))
artifacts = _load_artifacts(output, state)
reference = ROOT/'docs/reports/r5_20261014/release_replay/package/SECOND_CURATION_PARTIAL_zd_wjssZ7mc_20261014_140253_762578_0b9a68.zip'
legacy = decoded_documents(read_package(reference))
rows = {s['segment_id']: s for s in legacy['transcript/relevant_segments.jsonl']}

# The model's location/route and geographic-GPS paraphrases exceed 126–132.
# Retain the originals in provenance; use only the actual explanation/closing.
series = artifacts['editorial/story_series_proposals.json']['series'][0]
story = series['stories'][0]
repair = {'schema_version': '1.0', 'origin': 'codex_assisted_source_verification',
    'source_segment_ids': list(story['source_segment_ids']),
    'original_series_summary': series['summary'],
    'original_suggested_ending': story['suggested_ending'],
    'reason': 'source describes direction toward a station and pre-GPS time; not position/route determination or geographic GPS availability',
    'replacement_series_summary': rows['SEG_00131']['text'],
    'replacement_suggested_ending': rows['SEG_00132']['text'],
    'canonical_source_modified': False, 'human_review_completed': False, 'publication_ready': False}
if series['summary'] != rows['SEG_00131']['text'] or story['suggested_ending'] != rows['SEG_00132']['text']:
    artifacts['provenance/editorial_metadata_repair.json'] = repair
    series['summary'] = rows['SEG_00131']['text']
    story['suggested_ending'] = rows['SEG_00132']['text']
    series['editorial_metadata_origin'] = {'origin': repair['origin'],
        'repair_artifact': 'provenance/editorial_metadata_repair.json'}

def quote(sid):
    return {'segment_id': sid, 'quote': rows[sid]['text']}

def title(text, angle, ids):
    return {'text': text, 'angle': angle, 'factual_claims': [rows[s]['text'] for s in ids],
            'supporting_quotes': [quote(s) for s in ids], 'condensed_text': None}

payload = {
    'primary_title': title('COMO O ADF VAI APONTAR A DIREÇÃO?', 'CURIOSITY', ['SEG_00131']),
    'alternative_titles': [
        title('FREQUÊNCIAS DE RÁDIO: PARA ONDE VOAR?', 'EXPLANATORY', ['SEG_00128','SEG_00131']),
        title('O PILOTO E OS AUXÍLIOS DE RADIONAVEGAÇÃO', 'CONTEXT', ['SEG_00126','SEG_00127'])],
    'opening_hook_text': rows['SEG_00126']['text'], 'hook_supporting_quotes': [quote('SEG_00126')],
    'social_caption': rows['SEG_00129']['text'], 'caption_supporting_quotes': [quote('SEG_00129')],
    'engagement_question': 'Comente sua opinião.', 'cta': 'Comente sua opinião.',
    'keywords': [{'text': text, 'segment_id': sid, 'reason': 'KEY_FACT'} for text, sid in [
        ('radionavegação','SEG_00127'), ('frequências','SEG_00128'), ('ADF','SEG_00131')]],
    'abstention_reason': None}
record = {'origin': 'codex_assisted_editorial_draft_from_canonical_source', 'author': 'Codex',
    'source_sha256': state['source_sha256'], 'payload': payload, 'payload_sha256': digest(payload),
    'draft_script_sha256': file_hash(Path(__file__)), 'new_ollama_calls': 0,
    'human_review_completed': False, 'publication_ready': False,
    'reason': 'Qwen attempts retained; no generated title set passed all source validators'}

def draft(task_id, context, schema):
    ids = {s['segment_id'] for s in context['data']['segments']}
    if ids != {'SEG_%05d'%i for i in range(126,133)}:
        raise ValueError('assisted_draft_source_scope_changed')
    return payload, {'origin': record['origin'], 'author': 'Codex',
        'execution_mode': 'assisted_editorial_draft', 'payload_sha256': digest(payload),
        'draft_script_sha256': record['draft_script_sha256'],
        'new_ollama_call': False, 'human_review_completed': False}

artifacts.update(build_story_visual_handoff(legacy, artifacts, draft))
artifacts['provenance/assisted_editorial_draft.json'] = record
validation = validate_semantic_artifacts(artifacts, legacy)
atomic_json(output/'assisted_draft_validation.json', validation)
stories = [s for series in artifacts['social/story_visual_handoff.json']['series'] for s in series['stories']]
if validation['status'] != 'valid' or not stories or any(s['metadata_status'] != 'COMPLETE_FOR_REVIEW' for s in stories):
    print(json.dumps({'validation': validation, 'blockers': [s['blocking_issues'] for s in stories]}, ensure_ascii=True))
    raise SystemExit(2)
atomic_json(output/'assisted_editorial_draft_utf8.json', record)
_checkpoint(output, state, artifacts, 'C_VALIDATED')
atomic_json(output/'CHECKPOINT_C.json', {'status': 'C_VALIDATED', 'validation': validation,
    'new_model_calls': 0, 'scope': 'assisted editorial metadata; Qwen attempts retained',
    'draft_payload_sha256': digest(payload), 'human_review_completed': False, 'publication_ready': False})
print(json.dumps({'status': 'valid', 'complete_stories': len(stories), 'titles_per_story': 3,
                  'human_review_completed': False}))
