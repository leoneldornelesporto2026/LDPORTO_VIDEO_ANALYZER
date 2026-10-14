"""Additive semantic package contracts; historical R5 archives remain read-only."""
import json
from pathlib import Path
import zipfile
import hashlib
import math
import re
import unicodedata
from copy import deepcopy

import jsonschema


SCHEMA_DIALECT = 'https://json-schema.org/draft/2020-12/schema'


def _claim_origin_issues(text, source_text):
    """Conservative provenance blockers, not general semantic entailment.

    Do not expand acronyms or attach names from outside the selected evidence.
    Lowercase paraphrases still require editorial review after these checks pass.
    """
    def folded(word):
        return ''.join(c for c in unicodedata.normalize('NFKD', word.casefold()) if not unicodedata.combining(c))
    source_words = {folded(word) for word in re.findall(r'[^\W\d_]+', source_text)}
    ignored = {'a', 'o', 'as', 'os', 'um', 'uma', 'uns', 'umas', 'ao', 'aos', 'na', 'no',
               'nas', 'nos', 'de', 'do', 'da', 'dos', 'das', 'e', 'em', 'mas', 'por', 'para',
               'se', 'que', 'com', 'como', 'isso', 'isto', 'ele', 'ela', 'eles', 'elas'}
    issues = []
    parenthetical = [(m.start(), m.end()) for m in re.finditer(r'\([^()]*\)', text)]
    for expansion in re.finditer(r'\b[A-Z][A-Z0-9]{1,}\s*\(([^()]*)\)', text):
        for word in re.findall(r'[^\W\d_]+', expansion.group(1)):
            if folded(word) not in source_words and folded(word) not in ignored:
                issues.append('unsupported_acronym_expansion:'+word)
    for match in re.finditer(r'[^\W\d_]+', text):
        word = match.group()
        token = folded(word)
        if token in source_words or token in ignored or len(word) < 2:
            continue
        if word.isupper():
            issues.append('unsupported_acronym_in_claim:'+word)
            continue
        if not word[0].isupper():
            continue
        if any(start < match.start() < end for start, end in parenthetical):
            issues.append('unsupported_parenthetical_expansion_or_name:'+word)
            continue
        preceding = text[:match.start()].rstrip()
        if preceding and preceding[-1] not in '.!?':
            issues.append('unsupported_named_term_in_claim:'+word)
    return issues


def validate_embedded_schemas(documents):
    """Validate the *whole* embedded schema, including its declared dialect."""
    errors = []
    for name, schema in documents.items():
        if not name.startswith('schemas/') or not name.endswith('.schema.json'):
            continue
        try:
            if schema.get('$schema') != SCHEMA_DIALECT:
                raise ValueError('unsupported_or_invalid_schema_dialect')
            jsonschema.Draft202012Validator.check_schema(schema)
        except (ValueError, AttributeError, jsonschema.SchemaError) as exc:
            errors.append({'artifact': name, 'reason': str(exc).splitlines()[0]})
    return {'status': 'valid' if not errors else 'invalid', 'errors': errors,
            'metadata_removed': False}


def read_package(path):
    """Bounded, traversal-free reads; never extract reference archives over sources."""
    from .second_curation_export import validate_core_package
    result = validate_core_package(path)
    if result['status'] != 'valid':
        raise ValueError({'invalid_reference_package': result['errors'][:10]})
    with zipfile.ZipFile(Path(path)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def decoded_documents(members):
    documents = {}
    for name, data in members.items():
        if name.endswith('.json'):
            documents[name] = json.loads(data)
        elif name.endswith('.jsonl'):
            documents[name] = [json.loads(line) for line in data.decode('utf-8-sig').splitlines() if line]
    return documents


def validate_semantic_artifacts(documents, legacy):
    """Offline consumer checks, independent of inference or its cached validators."""
    errors = []
    segments = {s['segment_id']: s for s in legacy['transcript/relevant_segments.jsonl']}
    arcs = {a['story_arc_id'] for a in legacy['editorial/story_arcs.json']}
    units = {u['unit_id']: u for u in legacy['editorial/story_units.json']['units']}
    def walk(value, location):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {'publication_ready', 'human_review_completed', 'preview_approved', 'confirmed'} and item is True:
                    errors.append('unapproved_gate_promotion:' + location + '/' + key)
                if key in {'source_segment_ids', 'supporting_segment_ids', 'question_segment_ids', 'answer_segment_ids'} and isinstance(item, list):
                    if any(sid not in segments for sid in item):
                        errors.append('unknown_segment:' + location)
                if key == 'source_arc_ids' and isinstance(item, list) and any(a not in arcs for a in item):
                    errors.append('unknown_arc:' + location)
                if key == 'source_unit_ids' and isinstance(item, list) and any(u not in units for u in item):
                    errors.append('unknown_unit:' + location)
                walk(item, location+'/'+key)
            if 'segment_id' in value:
                sid = value['segment_id']
                source = segments.get(sid)
                if source is None:
                    errors.append('unknown_evidence_segment:' + location)
                else:
                    if 'quote' in value and (not isinstance(value['quote'], str) or not value['quote'] or value['quote'] not in source['text']):
                        errors.append('nonliteral_quote:' + location)
                    if 'text' in value and value['text'] != source['text']:
                        # Word/highlight structures have their own temporal validator.
                        if '/validated_payload/keywords/' in location:
                            if not isinstance(value['text'], str) or not value['text'] or value['text'] not in source['text']:
                                errors.append('keyword_not_literal:' + location)
                        elif not any(k in location for k in ('source_words', 'highlight_candidates')):
                            errors.append('altered_evidence_text:' + location)
                    if all(k in value for k in ('start', 'end')):
                        a, b = value['start'], value['end']
                        if not all(isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) for t in (a, b)) or not source['start'] <= a < b <= source['end']:
                            errors.append('evidence_interval_invalid:' + location)
            # Source intervals describe complete canonical segments. Word/highlight
            # timestamps are checked separately and may legitimately be subspans.
            if 'source_intervals' in value and not any(k in location for k in ('source_words', 'highlight_candidates')):
                ids = value.get('source_segment_ids', value.get('supporting_segment_ids', value.get('answer_segment_ids')))
                if isinstance(ids, list) and all(sid in segments for sid in ids):
                    expected = [{'segment_id': sid, 'start': segments[sid]['start'], 'end': segments[sid]['end']} for sid in ids]
                    if value['source_intervals'] != expected:
                        errors.append('source_interval_segment_correspondence_mismatch:' + location)
            claim_ids = value.get('source_segment_ids', value.get('supporting_segment_ids', value.get('answer_segment_ids')))
            if isinstance(claim_ids, list) and claim_ids and all(sid in segments for sid in claim_ids):
                for field in ('summary', 'reasoning_summary'):
                    if not isinstance(value.get(field), str):
                        continue
                    ids = list(claim_ids)
                    if field == 'reasoning_summary':
                        ids.extend(sid for sid in value.get('question_segment_ids') or [] if sid in segments)
                    source_text = ' '.join(segments[sid]['text'] for sid in ids)
                    errors.extend(issue+':'+location+'/'+field for issue in _claim_origin_issues(value[field], source_text))
        elif isinstance(value, list):
            for i, child in enumerate(value):
                walk(child, location+'/'+str(i))
    for name, document in documents.items():
        # Rejected model responses are preserved as diagnostics, not accepted evidence.
        if name in {'editorial/semantic_resolver_diagnostics.json'}:
            continue
        if name.startswith(('editorial/', 'social/')):
            public = deepcopy(document)
            if isinstance(public, dict):
                public.pop('rejected_proposals', None)
            walk(public, name)
    graph = documents.get('editorial/semantic_narrative_graph.json') or {}
    nodes = [n.get('node_id') for n in graph.get('nodes', [])]
    if len(nodes) != len(set(nodes)):
        errors.append('duplicate_semantic_node')
    for edge in graph.get('edges', []):
        if edge.get('source_node_id') not in nodes or edge.get('target_node_id') not in nodes:
            errors.append('dangling_semantic_graph_edge')
    series = (documents.get('editorial/story_series_proposals.json') or {}).get('series', [])
    story_ids = set()
    for sequence in series:
        previous_ids = set()
        for index, story in enumerate(sequence['stories'], 1):
            sid = story.get('story_id')
            if sid in story_ids:
                errors.append('duplicate_story_id')
            story_ids.add(sid)
            if story.get('series_id') != sequence['series_id'] or story.get('sequence_position') != index or story.get('sequence_total') != len(sequence['stories']):
                errors.append('story_numbering_mismatch')
            if story.get('previous_story_dependency') is not None and story['previous_story_dependency'] not in previous_ids:
                errors.append('circular_or_unknown_story_dependency')
            previous_ids.add(sid)
            selected = set(story.get('source_segment_ids') or [])
            membership = {s for u in story.get('source_unit_ids') or [] if u in units for s in units[u]['source_segment_ids']}
            if not selected or not selected <= membership:
                errors.append('story_unit_segment_mismatch')
            if any((units[u].get('sequence_unit_eligibility') or units[u].get('eligibility')) == 'BLOCKED_RECORDED_COMMERCIAL'
                   for u in story.get('source_unit_ids') or [] if u in units):
                errors.append('recorded_commercial_gate_preserved')
    schema = documents.get('schemas/story_visual_handoff.schema.json')
    visual = documents.get('social/story_visual_handoff.json')
    if visual is not None:
        from .story_visual_handoff import validate_story_visual_handoff
        result = validate_story_visual_handoff(documents, legacy, documents)
        errors.extend('visual:'+str(e) for e in result['errors'])
        if schema is None:
            errors.append('missing_visual_schema')
        else:
            try:
                jsonschema.Draft202012Validator(schema).validate(visual)
            except jsonschema.ValidationError as exc:
                errors.append('visual_schema:'+exc.message)
    handoff = documents.get('SECOND_CURATION_SEMANTIC_HANDOFF.json')
    if handoff is not None:
        semantic_schema = documents.get('schemas/semantic_handoff.schema.json')
        if semantic_schema is None:
            errors.append('missing_semantic_handoff_schema')
        else:
            try:
                if semantic_schema.get('$schema') != SCHEMA_DIALECT:
                    raise ValueError('invalid_semantic_handoff_schema_dialect')
                jsonschema.Draft202012Validator.check_schema(semantic_schema)
                jsonschema.Draft202012Validator(semantic_schema).validate(handoff)
            except (ValueError, AttributeError, jsonschema.SchemaError, jsonschema.ValidationError) as exc:
                errors.append('semantic_handoff_schema:'+str(exc).splitlines()[0])
        references = list((handoff.get('artifact_refs') or {}).values())
        references.extend(value for key, value in handoff.items() if key.endswith('_ref') and value)
        available = {**legacy, **documents}
        for ref in references:
            if not isinstance(ref, str) or ref.split('#', 1)[0] not in available:
                errors.append('semantic_handoff_dangling_reference:'+str(ref))
                continue
            if '#' in ref:
                target, pointer = ref.split('#', 1)
                value = available[target]
                try:
                    if pointer and not pointer.startswith('/'):
                        raise KeyError('invalid_json_pointer')
                    for token in pointer.lstrip('/').split('/') if pointer else []:
                        token = token.replace('~1', '/').replace('~0', '~')
                        value = value[int(token)] if isinstance(value, list) else value[token]
                except (KeyError, IndexError, TypeError, ValueError):
                    errors.append('semantic_handoff_dangling_json_pointer:'+ref)
        expected_source = (legacy.get('source/metadata.json') or {}).get('sha256')
        if handoff.get('source_sha256') != expected_source:
            errors.append('semantic_handoff_source_identity_disagreement')
    return {'status': 'valid' if not errors else 'invalid', 'errors': sorted(set(errors)),
            'broken_reference_count': len(errors), 'publication_ready': False}


def export_semantic_package(reference, output, additions):
    """Copy legacy *data*, add validated derived contracts, repair only embedded schemas."""
    from .core import file_hash
    from .second_curation_export import validate_core_package
    from .semantic_runtime import atomic_json
    from datetime import datetime, timezone
    import uuid
    members = read_package(reference)
    legacy = decoded_documents(members)
    protected = {n: hashlib.sha256(v).hexdigest() for n, v in members.items()
                 if n != 'SECOND_CURATION_MANIFEST.json' and not n.startswith('schemas/')}
    for name, value in additions.items():
        if name in members:
            raise ValueError('semantic_addition_cannot_replace_legacy:' + name)
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name:
            raise ValueError('unsafe_semantic_artifact_path')
        members[name] = (value if isinstance(value, bytes) else value.encode('utf-8') if isinstance(value, str)
                         else json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'))
    if 'SECOND_CURATION_SEMANTIC_HANDOFF.json' in members and 'schemas/semantic_handoff.schema.json' not in members:
        members['schemas/semantic_handoff.schema.json'] = (Path(__file__).parents[2]/'schemas/semantic_handoff.schema.json').read_bytes()
    for name in list(members):
        if name.startswith('schemas/') and name.endswith('.schema.json'):
            source = Path(__file__).parents[2]/name
            if source.is_file():
                members[name] = source.read_bytes()
    documents = decoded_documents(members)
    validation = validate_semantic_artifacts({n: doc for n, doc in documents.items() if n not in legacy or n in additions}, legacy)
    schema_validation = validate_embedded_schemas(documents)
    if validation['status'] != 'valid' or schema_validation['status'] != 'valid':
        raise ValueError({'semantic_validation': validation, 'schema_validation': schema_validation})
    manifest = legacy['SECOND_CURATION_MANIFEST.json']
    text_calls = (documents.get('provenance/semantic_text_inference.json') or {}).get('new_textual_model_calls') or 0
    manifest.update(semantic_handoff_ref='SECOND_CURATION_SEMANTIC_HANDOFF.json',
        semantic_schema_version='1.0', source_reference_package_sha256=file_hash(reference),
        semantic_provenance_ref='provenance/semantic_text_inference.json',
        legacy_core_expensive_inference_executed=manifest.get('expensive_inference_executed'),
        expensive_inference_executed=bool(text_calls), new_textual_inference_calls=text_calls,
        new_audiovisual_inference=False)
    manifest['files'] = [{'path': n, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                         for n, data in sorted(members.items()) if n != 'SECOND_CURATION_MANIFEST.json']
    manifest['file_count'] = len(members)
    manifest['uncompressed_bytes'] = sum(r['bytes'] for r in manifest['files'])
    members['SECOND_CURATION_MANIFEST.json'] = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
    if any(hashlib.sha256(members[n]).hexdigest() != h for n, h in protected.items()):
        raise ValueError('legacy_artifact_changed_in_semantic_export')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    project = documents['source/metadata.json'].get('source', {}).get('id') or 'source'
    target = output/f'SECOND_CURATION_R5_1_{project}_{stamp}_{uuid.uuid4().hex[:6]}.zip'
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for n, data in sorted(members.items()):
            archive.writestr(n, data)
    result = validate_semantic_package(target, reference=reference)
    atomic_json(target.with_suffix('.validation.json'), result)
    if result['status'] != 'valid':
        # Retain failed packages as evidence, never advertise one as validated.
        raise ValueError({'exported_semantic_package_invalid': result})
    return {'path': str(target), 'sha256': file_hash(target), 'bytes': target.stat().st_size,
            'validation': result, 'publication_ready': False}


def validate_semantic_package(path, *, reference=None):
    """Consumer validates shipped schemas, cross-references and source preservation."""
    from .second_curation_export import validate_core_package
    from .build_provenance import validate_semantic_text_provenance
    core = validate_core_package(path)
    if core['status'] != 'valid':
        return {'status': 'invalid', 'errors': core['errors']}
    members = read_package(path)
    documents = decoded_documents(members)
    errors = validate_embedded_schemas(documents)['errors']
    semantic_names = {'editorial/global_topic_map.json', 'editorial/semantic_narrative_graph.json',
        'editorial/cross_arc_relations.json', 'editorial/semantic_qa_proposals.json',
        'editorial/narrative_completion_proposals.json', 'editorial/story_series_proposals.json',
        'social/narrative_editorial_title_proposals.json', 'social/story_visual_handoff.json',
        'schemas/story_visual_handoff.schema.json', 'SECOND_CURATION_SEMANTIC_HANDOFF.json',
        'schemas/semantic_handoff.schema.json', 'editorial/story_visual_completeness_report.json',
        'provenance/semantic_compatibility.json', 'provenance/semantic_text_inference.json', 'SEMANTIC_REVIEW.html'}
    errors.extend('missing_semantic_artifact:'+n for n in sorted(semantic_names-set(members)))
    reference_members = read_package(reference) if reference else None
    legacy = decoded_documents(reference_members) if reference_members else documents
    additions = {n: v for n, v in documents.items() if n in semantic_names or
                 n.startswith(('editorial/semantic_', 'provenance/')) and n != 'provenance/editorial_replay.json'}
    cross = validate_semantic_artifacts(additions, legacy)
    errors.extend(cross['errors'])
    if 'provenance/semantic_text_inference.json' in documents:
        errors.extend(validate_semantic_text_provenance(documents['provenance/semantic_text_inference.json'],
                                                       documents['source/metadata.json']['sha256']))
    protected_verified = 0
    if reference_members:
        for n, original in reference_members.items():
            if n == 'SECOND_CURATION_MANIFEST.json' or n.startswith('schemas/'):
                continue
            if members.get(n) != original:
                errors.append('legacy_artifact_changed:'+n)
            else:
                protected_verified += 1
    handoff = documents.get('SECOND_CURATION_SEMANTIC_HANDOFF.json') or {}
    if handoff.get('publication_ready') is not False or handoff.get('human_editorial_approval') is not False:
        errors.append('semantic_handoff_approval_gate_invalid')
    return {'status': 'valid' if not errors else 'invalid', 'errors': errors,
            'core_validation_status': core['status'], 'embedded_schemas_validated': True,
            'manifest_hashes_verified': len(members)-1, 'legacy_documents_preserved': protected_verified,
            'publication_ready': False}
