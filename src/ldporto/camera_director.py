"""Stateful offline camera routing; outputs recommendations, never renders video."""
from bisect import bisect_left, bisect_right
from collections import Counter, deque
import json
import math
import time
from .core import ok
from .director_config import resolve_config
from .temporal import IntervalCursor, VisualIndex, SampleIndex, number
from .camera_geometry import geometry, crop_rect, contains, base_size
from .camera_motion import CameraMotion, SmartZoomState
from .camera_evidence import (VisualTargetEvidence, camera_state, local_speaker_supported,
                              target_contradiction, focus_window_evidence)
from .interview_layout import choose_layout
from .camera_preflight import preflight_target, preflight_split, evidence_funnel

PRESERVE = {'broll', 'b_roll', 'screen', 'screen_capture', 'screen_content',
            'logo', 'title_card', 'empty', 'black'}


def _confidence(row):
    return number(row.get('confidence'))


def _candidate(name, layout, focus, components, **extra):
    return {'candidate': name, 'layout': layout, 'focus': focus,
            'score': sum(components.values()), 'components': components, **extra}


def _editorial_zoom_beat(time, moments, arcs, questions=None):
    for moment in moments:
        refs = moment.get('evidence_segment_ids') or []
        if not refs:
            continue
        categories = set(moment.get('categories') or [])
        core = moment.get('core_moment') or moment
        start = number(core.get('start'))
        score = number(moment.get('hook_score', moment.get('hook_strength', (moment.get('editorial') or {}).get('hook_strength'))))
        # Understanding often identifies a concrete hook_type without a category
        # literally named 'hook'. Accept only strongly grounded reveal/emotion
        # classifications; do not turn generic attention scores into zoom beats.
        typed_hook = moment.get('hook_type') in {'reveal', 'emotional_statement'}
        if (categories & {'hook', 'reveal', 'surprise', 'strong_opinion'} or typed_hook) and start <= time < start + 5 and score >= .7:
            return {'id': moment['moment_id'] + '_HOOK', 'reason': 'HOOK_EMPHASIS', 'evidence_refs': refs}
        if categories & {'payoff', 'punchline', 'emotion'} and core.get('start') is not None and core.get('end') is not None and number(core['start']) <= time < number(core['end']):
            return {'id': moment['moment_id'] + '_PAYOFF', 'reason': 'PAYOFF_EMPHASIS', 'evidence_refs': refs}
    # Q&A contains precisely timestamped answer payoff; do not infer from a
    # question mark alone or an unanswered question.
    for question in questions or []:
        answer_start = question.get('answer_start')
        answer_end = question.get('answer_end')
        refs = question.get('answer_segment_ids') or []
        if (question.get('question_answer_complete') is True and refs
                and isinstance(answer_start, (int, float)) and isinstance(answer_end, (int, float))
                and answer_start <= time < answer_end):
            return {'id': str(question.get('question_id') or 'QA_'+str(answer_start))+'_ANSWER',
                    'reason': 'QA_ANSWER_PAYOFF', 'evidence_refs': refs}
    for arc in arcs:
        payoff = arc.get('payoff') or {}
        if payoff.get('segment_ids') and payoff.get('start') is not None and payoff['start'] <= time < payoff.get('end', payoff['start']):
            return {'id': arc['story_arc_id'] + '_PAYOFF', 'reason': 'STORY_CLIMAX', 'evidence_refs': payoff['segment_ids']}
    return None


def _prepare(metadata, vision, shots, active, cfg):
    duration = number(metadata.get('duration'))
    boundaries = {0., duration}
    boundaries.update(round(i*cfg['tick_seconds'], 8) for i in range(math.ceil(duration/cfg['tick_seconds'])))
    for collection in (shots, active):
        for row in collection:
            boundaries.update(max(0., min(duration, number(row.get(k)))) for k in ('start', 'end'))
    times = sorted(boundaries)
    shot_cursor, active_cursor = IntervalCursor(shots), IntervalCursor(active)
    visual = VisualIndex(vision)
    records = []
    for start, end in zip(times, times[1:]):
        if end-start < 1e-8:
            continue
        mid = (start+end)/2
        shot = next(iter(shot_cursor.at(mid)), None)
        lo, hi = (shot['start'], shot['end']) if shot else (start, end)
        frame, obs = visual.near(mid, lo, hi, cfg['max_observation_gap_seconds']) if shot else (None, {})
        voices = list(active_cursor.at(mid))
        speakers = sorted({r.get('speaker_id') for r in voices if r.get('speaker_id')})
        # Only recent, visibly supported associations can direct an individual crop.
        # Distinct contradictory identities are never resolved by screen position.
        confident_rows = [r for r in voices
            if r.get('person_id') in obs and obs[r['person_id']].get('face_visible')
            and local_speaker_supported(r)
            and _confidence(r) >= cfg['enter_confidence']
            and r.get('contemporary_visual_presence') is not False
            and r.get('offscreen_state') is not True]
        confident_by_person = {}
        for candidate in confident_rows:
            person_id = candidate['person_id']
            previous = confident_by_person.get(person_id)
            if previous is None or _confidence(candidate) > _confidence(previous):
                confident_by_person[person_id] = candidate
        confident = list(confident_by_person.values())
        safe = {p: geometry([o], metadata, cfg) for p, o in obs.items()}
        safe = {p: g for p, g in safe.items() if g['safe']}
        pair = tuple(sorted(safe)) if len(safe) == 2 and len(obs) == 2 else ()
        records.append({'start': start, 'end': end, 'mid': mid, 'shot': shot or {},
                        'frame': frame, 'obs': obs, 'voices': voices, 'speakers': speakers,
                        'confident': confident, 'safe': safe, 'pair': pair,
                        'overlap': len(speakers) > 1 or any(r.get('overlap') for r in voices)})
    # Future availability is checked across every sampled interval, never across a shot.
    run_end, previous = 0., None
    for row in reversed(records):
        key = (row['shot'].get('shot_id'), row['pair'])
        if key != previous or not row['pair']:
            run_end = row['end']
        row['pair_available_until'] = run_end
        previous = key
    return records


def build_camera_director(metadata, vision, shots, active_speaker, person_motion, cfg=None,
                          questions_answers=None, story_arcs=None, main_moments=None, camera_plan=None):
    started = time.perf_counter()
    cfg = resolve_config(cfg)
    if not cfg['enabled']:
        return ok({'timeline': [], 'metrics': {}, 'debug': None, 'config': cfg}, 'skipped')
    duration = number(metadata.get('duration'))
    if duration <= 0:
        return ok({'timeline': [], 'metrics': {}, 'debug': None, 'config': cfg}, 'unavailable')
    records = _prepare(metadata, vision, shots or [], active_speaker or [], cfg)
    predecision_evidence = evidence_funnel(records, duration)
    qa = IntervalCursor([{**q, 'start': q.get('question_start'),
                          'end': q.get('answer_end') or q.get('question_end')} for q in questions_answers or []])
    arcs = IntervalCursor(story_arcs or [])
    moments = IntervalCursor([{**m, 'start': (m.get('core_moment') or m).get('start'),
                               'end': (m.get('core_moment') or m).get('end')} for m in main_moments or []])
    planner = IntervalCursor((camera_plan or {}).get('selected_global_path', []))
    graphics_cursor = IntervalCursor((vision.get('broadcast_graphics') or {}).get('intervals', []))
    motion_index = SampleIndex(person_motion or [])
    rows, debug, focus_windows = [], [], []
    counts = Counter()
    switches, recent_people = deque(), deque()
    current_focus, current_layout, current_pair = None, 'full_frame', ()
    current_role = 'SOURCE_PRESERVE'
    source_id, shot_since, layout_since = None, 0., 0.
    last_switch, last_focus_change = -math.inf, -math.inf
    last_reaction, reaction_until, reaction_return = -math.inf, -math.inf, None
    speaker_since, last_voice, last_person = 0., None, None
    hold_until = 0.
    previous_mode, last_stable_person, last_valid_crop = None, None, None
    controller = CameraMotion()
    smart_state = SmartZoomState()
    visual_targets = VisualTargetEvidence()
    previous_motion = {}
    side_assignments = {}
    split_anchor = None
    virtual_durations, virtual_start = [], 0.
    last_signature = None
    evidence_seconds = unresolved_seconds = 0.
    recent_turn_durations = deque(maxlen=20)
    debug_signature = None
    for index, item in enumerate(records):
        t, end, mid = item['start'], item['end'], item['mid']
        dt, shot, obs = end-t, item['shot'], item['obs']
        sid = shot.get('shot_id')
        reset = sid != source_id or index == 0
        reasons, suppressed = [], None
        transition = 'hold'
        if reset:
            smart_state.reset_shot(t)
            source_id, shot_since, layout_since = sid, t, t
            current_focus, current_layout, current_pair = None, 'full_frame', ()
            current_role = 'SOURCE_PRESERVE'
            controller = CameraMotion()
            last_switch = last_focus_change = -math.inf
            hold_until = t
            reaction_until, reaction_return = -math.inf, None
            previous_motion.clear()
            split_anchor = None
            counts['source_shot_resets'] += 1
            reasons.append('source_shot_reset')
            transition = 'source_cut' if index else 'initial'
        speakers = item['speakers']
        voice = speakers[0] if len(speakers) == 1 and not item['overlap'] else None
        if voice != last_voice:
            if voice and last_voice:
                switches.append(t)
                recent_turn_durations.append(t-speaker_since)
            speaker_since = t
            last_voice = voice
        while switches and switches[0] < t-10:
            switches.popleft()
        rate5 = sum(x >= t-5 for x in switches)
        rate10 = len(switches)
        quick = sum(x >= t-cfg['quick_exchange_window_seconds'] for x in switches) >= cfg['quick_exchange_switches']
        speech_run = t-speaker_since if voice else 0.
        confident = item['confident']
        if not confident and item['voices'] and not item['overlap']:
            counts['unconfirmed_audio_visual_windows'] += 1
        person = confident[0]['person_id'] if len(confident) == 1 and not item['overlap'] else None
        confidence = _confidence(confident[0]) if person else 0.
        role = ('CONFIRMED_SPEAKER' if person and confident[0].get('active_speaker_state', 'CONFIRMED' if confidence >= .8 else 'PROBABLE') == 'CONFIRMED'
                else 'PROBABLE_SPEAKER' if person else 'SOURCE_PRESERVE')
        dominant = visual_targets.update(obs, item['frame']['time'] if item['frame'] else mid, sid, cfg)
        item['visual_target_evidence'] = dominant
        contradiction = target_contradiction(item['voices']) or len(confident) > 1
        if cfg['dominant_face_fallback'] and person is None and dominant and not item['overlap'] and not contradiction:
            fallback_person = dominant['person_id']
            if fallback_person in item['safe'] and shot.get('shot_type') not in PRESERVE | {'close_up', 'medium_close_up'}:
                person, confidence = fallback_person, dominant['confidence']
                role = 'DOMINANT_FACE'
                speech_run = dominant['persistence_seconds']
                reasons.append('DOMINANT_FACE')
                counts['visual_only_fallback_windows'] += 1
        for r in confident:
            recent_people.append((t, r['person_id']))
        while recent_people and recent_people[0][0] < t-10:
            recent_people.popleft()
        relevant = {p for _, p in recent_people}
        pair = item['pair']
        safe = item['safe']
        preserve = shot.get('shot_type') in PRESERVE or not shot or item['frame'] is None
        qrows, arows, mrows = qa.at(mid), arcs.at(mid), moments.at(mid)
        planned = next(iter(planner.at(mid)), None)
        strong_moment = any(number(m.get('editorial_score')) >= .75 or
                           set(m.get('categories', [])) & {'payoff', 'punchline', 'conclusion', 'reveal'} for m in mrows)
        mode = ('B_ROLL' if preserve else 'OVERLAP' if item['overlap'] else
                'GROUP_DISCUSSION' if quick and len(obs) > 2 else
                'QUICK_EXCHANGE' if quick else 'QUESTION_ANSWER' if qrows and voice else
                'MONOLOGUE' if voice and (speech_run >= 5 or len(relevant) <= 1) else
                'DIALOGUE' if voice else 'NO_CLEAR_SPEAKER')
        if person is None and not preserve:
            unresolved_seconds += dt
        if item['frame']:
            evidence_seconds += dt
        if person and person not in safe:
            counts['unsafe_crop_avoided'] += 1
        quality = number(shot.get('camera_score'), .4)
        candidates = [_candidate('FULL_FRAME', 'full_frame', None, {'source': .40})]
        incumbent_disputed = contradiction or (current_role in {'CONFIRMED_SPEAKER', 'PROBABLE_SPEAKER'}
            and any(r.get('person_id') == current_focus and not local_speaker_supported(r) for r in item['voices']))
        if current_focus in safe and not preserve and not incumbent_disputed:
            current_voice_score = max((_confidence(r) for r in item['voices'] if r.get('person_id') == current_focus), default=0.)
            candidates.append(_candidate('KEEP_CURRENT', current_layout, current_focus,
                {'speaker': .50*current_voice_score, 'crop': .15, 'quality': .10*quality,
                 'persistence': cfg['persistence_bonus'], 'continuity': .20}, pair=current_pair))
        if person in safe and not preserve:
            candidates.append(_candidate('FOCUS_'+person, 'single_person', person,
                {'speaker': .60*confidence, 'crop': .15, 'quality': .10*quality,
                 'stability': .10*min(1., speech_run/cfg['speaker_confirm_seconds']),
                 'switch_penalty': -cfg['switch_cost'] if current_focus and current_focus != person else 0.}))
        pair_reason = mode in {'OVERLAP', 'QUICK_EXCHANGE', 'QUESTION_ANSWER'}
        pair_eligible = (pair and set(pair) <= relevant and pair_reason and not preserve and
                         item['pair_available_until']-t >= cfg['min_hold_seconds'])
        pair_geo = geometry([obs[p] for p in pair], metadata, cfg) if pair else {'safe': False}
        split_plan = preflight_split(pair, index, records, metadata, cfg, horizon=cfg['split_preflight_seconds']) if pair_eligible and cfg['enable_split'] else {'safe': False}
        if pair_eligible:
            if pair_geo['safe']:
                candidates.append(_candidate('TWO_SHOT', 'two_shot', None,
                    {'conversation': .65, 'crop': .20, 'stability': .15}, pair=pair))
            elif cfg['enable_split'] and split_plan.get('safe'):
                candidates.append(_candidate('SPLIT', 'split_candidate', None,
                    {'conversation': .60, 'independent_crops': .20, 'stability': .15}, pair=pair))
        if pair_eligible and not pair_geo.get('safe') and not split_plan.get('safe'):
            counts['split_preflight_rejected'] += 1
        if current_layout in {'two_shot', 'split_candidate'} and current_pair and all(p in safe for p in current_pair):
            if pair_reason or speech_run < cfg['preferred_hold_seconds']:
                candidates.append(_candidate('KEEP_LAYOUT', current_layout, None,
                    {'persistence': .55, 'crop': .2, 'conversation': .25}, pair=current_pair))
        # Objective listener motion change, never an emotion label. Original audio stays intact.
        reaction = None
        if (cfg['enable_reaction_shots'] and not preserve and person and role != 'DOMINANT_FACE'
                and speech_run >= cfg['preferred_hold_seconds'] and not contradiction
                and t-last_reaction >= cfg['reaction_cooldown_seconds'] and not quick and not item['overlap']):
            for p in safe:
                sample = motion_index.near(p, item['frame']['time'], shot['start'], shot['end'])
                if (not sample or sample.get('movement_intensity') is None
                        or ('track_id' in sample and sample['track_id'] != obs[p].get('track_id'))
                        or ('scene_id' in sample and sample['scene_id'] != shot.get('scene_id'))):
                    continue
                intensity = number(sample['movement_intensity'])
                motion_key = (p, obs[p].get('track_id'))
                old = previous_motion.get(motion_key)
                previous_motion[motion_key] = intensity
                if p != person and old is not None and intensity >= cfg['reaction_threshold'] and intensity-old >= cfg['reaction_delta']:
                    reaction = p
            if reaction:
                candidates.append(_candidate('REACTION_'+reaction, 'single_person', reaction,
                    {'listener_motion_spike': .80, 'crop': .2, 'editorial': .2}, reaction=True))
        # Global Planner is an editorial preference, not a hard override. The Director
        # may reject it for current-frame safety, minimum hold, stale evidence or source cuts.
        if planned:
            for candidate in candidates:
                layout_match = candidate['layout'] == planned.get('layout')
                focus_match = candidate.get('focus') == planned.get('focus_person')
                people_match = not planned.get('people') or set(candidate.get('pair', ())) == set(planned.get('people', []))
                if layout_match and focus_match and people_match:
                    candidate['components']['global_plan_alignment'] = .28
                    candidate['score'] += .28

        if reaction_until > t and current_focus in safe and not contradiction:
            chosen = _candidate('HOLD_REACTION', 'single_person', current_focus, {'reaction_hold': 1.})
            mode = 'REACTION'
        else:
            chosen = max(candidates, key=lambda c: c['score'])
        if preserve:
            chosen = candidates[0]
            reasons.append('preserve_source_content' if shot else 'missing_source_shot')
        requested_focus = chosen['focus']
        new_pair = chosen.get('pair', ())
        changed = (requested_focus, chosen['layout'], new_pair) != (current_focus, current_layout, current_pair)
        lost_confidence = any(r.get('person_id') == current_focus and _confidence(r) < cfg['exit_confidence']
                              for r in item['voices']) if current_focus else False
        safety_exit = (lost_confidence or incumbent_disputed or preserve or (current_focus is not None and current_focus not in safe) or
                       (current_pair and any(p not in safe for p in current_pair)) or
                       (item['overlap'] and current_layout == 'single_person'))
        returning = reaction_until <= t and reaction_return is not None
        if returning:
            if person == reaction_return and person in safe:
                chosen = _candidate('RETURN_TO_SPEAKER', 'single_person', person, {'reaction_return': 1.})
                requested_focus, new_pair, changed = person, (), current_focus != person
            reaction_return = None
        incumbent = next((c for c in candidates if c['candidate'] in {'KEEP_CURRENT', 'KEEP_LAYOUT'}), None)
        if changed and not safety_exit and not reset and not returning:
            if t < hold_until or t-layout_since < cfg['min_hold_seconds']:
                suppressed = 'minimum_hold'
            elif t-last_switch < cfg['switch_cooldown_seconds']:
                suppressed = 'switch_cooldown'
            elif chosen['layout'] == 'single_person' and not chosen.get('reaction') and (
                    speech_run < max(cfg['speaker_confirm_seconds'], cfg['short_interruption_seconds'])):
                suppressed = 'brief_interruption_or_unconfirmed_speaker'
            elif incumbent and chosen['score'] < incumbent['score']+cfg['switch_margin']:
                suppressed = 'challenger_margin_and_persistence'
        # Initial focus must also be confirmed, even if there is no previous crop.
        if chosen['layout'] == 'single_person' and current_focus is None and not chosen.get('reaction') and speech_run < cfg['speaker_confirm_seconds']:
            suppressed = 'speaker_confirmation'
        # When incumbent wins, still expose the requested speaker switch that was rejected.
        if person and person != current_focus and requested_focus == current_focus and current_focus and not preserve:
            suppressed = suppressed or 'challenger_margin_and_persistence'
        if suppressed and not safety_exit:
            if changed or (person and person != current_focus):
                counts['switches_suppressed'] += 1
            chosen = _candidate('HOLD', current_layout, current_focus, {'hold': 1.}, pair=current_pair)
            requested_focus, new_pair, changed = current_focus, current_pair, False
            reasons.append(suppressed)
        if safety_exit and chosen['layout'] == 'single_person' and (lost_confidence or contradiction or preserve or item['overlap'] or chosen['focus'] not in safe):
            chosen = candidates[0]
            requested_focus, new_pair = None, ()
            changed = current_layout != 'full_frame' or current_focus is not None
        if changed:
            if t > virtual_start:
                virtual_durations.append(t-virtual_start)
            virtual_start = t
            if not reset:
                counts['director_switches'] += 1
            if current_focus != requested_focus:
                last_focus_change = t
            current_focus, current_layout, current_pair = requested_focus, chosen['layout'], new_pair
            current_role = role if current_focus == person else 'REACTION' if chosen.get('reaction') else 'SOURCE_PRESERVE'
            last_switch, layout_since = t, t
            hold_until = t+cfg['min_hold_seconds']
            transition = 'cut' if not reset else transition
            reasons.append(chosen['candidate'].lower())
            if chosen.get('reaction'):
                last_reaction, reaction_until, reaction_return = t, t+cfg['reaction_seconds'], person
                mode = 'REACTION'
            if current_focus == person:
                last_stable_person = person
        if current_layout == 'full_frame':
            current_focus, current_pair = None, ()
        # Lookahead is bounded by this source shot, and never changes the active speaker early.
        next_cut = number(shot.get('end'), end)
        near_cut = cfg['enable_lookahead'] and 0 < next_cut-t <= cfg['lookahead_seconds']
        future_voice = None
        if cfg['enable_lookahead'] and not near_cut:
            j = index+1
            horizon = min(next_cut, t+cfg['lookahead_seconds'])
            while j < len(records) and records[j]['start'] < horizon:
                future = records[j]
                if future['shot'].get('shot_id') != sid:
                    break
                if len(future['speakers']) == 1 and future['speakers'][0] != voice:
                    future_voice = future['speakers'][0]
                    break
                j += 1
        beat = _editorial_zoom_beat(mid, mrows, arows, qrows)
        raw_beat = beat
        if beat:
            counts['editorial_beat_raw_windows'] += 1
            counts['editorial_beat_'+beat['reason']] += 1
        if quick or item['overlap'] or near_cut:
            if beat:
                counts['editorial_beat_suppressed_due_to_cut_or_overlap'] += 1
            beat = None
        if beat:
            counts['editorial_beat_eligible_windows'] += 1
            if current_focus is None:
                counts['editorial_beat_without_focus_windows'] += 1
            elif current_focus == person and current_layout == 'single_person':
                counts['editorial_beat_with_speaker_focus_windows'] += 1
        elif current_focus and current_layout == 'single_person':
            counts['focused_windows_without_editorial_beat'] += 1
        baseline_geo = (preflight_target(current_focus, index, records, metadata, cfg,
            horizon=cfg['crop_preflight_seconds']) if current_focus in obs else {'safe': False})
        if current_focus and baseline_geo.get('safe') is False:
            counts['crop_preflight_blocked_windows'] += 1
        # A single sampled frame is not proof a digital zoom will remain safe.
        zoom_path_supported = baseline_geo.get('safe', False) and baseline_geo.get('preflight_sample_count', 0) >= 2
        if beat and current_focus and not zoom_path_supported:
            counts['zoom_temporal_preflight_rejected_windows'] += 1
            reasons.append('INSUFFICIENT_TEMPORAL_CROP_EVIDENCE')
        face_size = number((obs.get(current_focus, {}).get('face_bbox') or {}).get('height'))
        source_motion_data = (item['frame'] or {}).get('source_camera_motion')
        source_motion_value = number((source_motion_data or {}).get('magnitude'), number((item['frame'] or {}).get('camera_motion_proxy')))
        smart_decision = smart_state.decide(t, target=current_focus if current_layout == 'single_person' else None,
            confidence=confidence if current_focus == person else 0., safe=(zoom_path_supported if beat else baseline_geo.get('safe', False)),
            zoom_cap=baseline_geo.get('max_zoom', 1.), face_size=face_size,
            source_close=shot.get('shot_type') in {'close_up', 'medium_close_up'}, source_motion=source_motion_value,
            speech_seconds=speech_run, remaining_seconds=next_cut - t, beat=beat,
            micro_interruption=bool(person and person != current_focus and suppressed),
            cfg=cfg['smart_zoom'], max_speed=cfg['max_zoom_speed'])
        desired_zoom = smart_decision['zoom']
        if smart_decision.get('zoom_attempted'):
            counts['smart_zoom_requested_windows'] += 1
        if smart_decision.get('new_zoom_request'):
            counts['smart_zoom_accepted_windows'] += 1
        if beat:
            for reason in smart_decision['reason_codes']:
                if reason not in {'STABLE_EDITORIAL_FRAMING','HOOK_EMPHASIS','PAYOFF_EMPHASIS','STORY_CLIMAX','QA_ANSWER_PAYOFF'}:
                    counts['zoom_block_'+reason] += 1
            if not smart_decision.get('new_zoom_request'):
                cause = smart_decision['reason_codes'][0]
                if 'INSUFFICIENT_TEMPORAL_CROP_EVIDENCE' in reasons:
                    cause = baseline_geo.get('preflight_reason') or 'INSUFFICIENT_TEMPORAL_CROP_EVIDENCE'
                counts['zoom_opportunity_outcome_'+cause] += 1
            else:
                counts['zoom_opportunity_outcome_ACCEPTED'] += 1
        elif raw_beat:
            counts['zoom_opportunity_outcome_CUT_OR_OVERLAP'] += 1
        reasons.extend(smart_decision['reason_codes'])
        motion = motion_index.near(current_focus, mid, shot.get('start', t), next_cut) if current_focus else None
        geo = preflight_target(current_focus, index, records, metadata, cfg,
            horizon=cfg['crop_preflight_seconds'], zoom=desired_zoom) if current_focus in obs else (
            geometry([obs[p] for p in current_pair], metadata, cfg) if current_layout == 'two_shot' else {'safe': False})
        if current_layout == 'split_candidate':
            verified = preflight_split(current_pair, index, records, metadata, cfg,
                                       horizon=cfg['split_preflight_seconds'])
            if changed or split_anchor is None:
                split_anchor = ({verified['left_person']: verified['left_crop'],
                                 verified['right_person']: verified['right_crop']}
                                if verified.get('safe') else {})
            split_valid = bool(verified.get('safe') and split_anchor and all(
                contains(split_anchor[p], verified['subject_bounds'][p]) for p in current_pair))
            assignment = (verified['left_person'], verified['right_person']) if verified.get('safe') else current_pair
            split = {'left_person': assignment[0], 'right_person': assignment[1],
                     'left_crop': split_anchor.get(assignment[0]), 'right_crop': split_anchor.get(assignment[1]),
                     'left_crop_safe': split_valid, 'right_crop_safe': split_valid,
                     'simultaneous_visibility_coverage': None, 'coverage_is_sampled': True,
                     'panel_aspect_correct': True, 'panel_motion': 'static_safe_crop'} if split_valid else None
            if not split_valid:
                split = None
                current_layout, current_focus, current_pair = 'full_frame', None, ()
                transition = 'safety_cut'
                last_switch = layout_since = t
                hold_until = t+cfg['min_hold_seconds']
                reasons.append('split_subject_left_safe_panel')
                counts['unsafe_crop_avoided'] += 1
        else:
            split = None
            split_anchor = None
        if changed or reset:
            # Deliberate edits are cuts; no continuous pan between unrelated subjects/cameras.
            anchor = geo.get('center', [.5, .5])
            controller = CameraMotion(*anchor, 1.)
        start_state = controller.snapshot(t)
        if geo.get('safe') and current_layout in {'single_person', 'two_shot'}:
            target = [*geo['center'], geo['zoom']]
            if near_cut:
                target = [*controller.target[:2], min(controller.target[2], geo['max_zoom'])]
                reasons.append('hold_before_source_cut')
            before, after, deadzone = controller.move(target, t, dt, cfg)
            counts['deadzone_suppressed_moves'] += int(deadzone)
            rect = crop_rect(after[:2], max(1., after[2]), base_size(metadata, cfg))
            # Safety has priority over smoothing. Do not report an unsafe interpolated crop.
            if (after[2] > geo['max_zoom']+1e-6 or after[2] < 1.-1e-6 or
                    not contains(crop_rect(before[:2], max(1., before[2]), base_size(metadata, cfg)), geo['subject_bounds']) or
                    not contains(rect, geo['subject_bounds'])):
                counts['unsafe_crop_avoided'] += 1
                current_layout, current_focus, current_pair = 'full_frame', None, ()
                controller = CameraMotion()
                transition = 'safety_cut'
                last_switch = layout_since = t
                hold_until = t+cfg['min_hold_seconds']
                start_state = controller.snapshot(t)
                reasons.append('unsafe_motion_path_preserve_frame')
                geo, rect = {'safe': False}, None
            else:
                last_valid_crop = rect
        else:
            controller = CameraMotion()
            rect = None
            if current_layout in {'single_person', 'two_shot'}:
                # The renderer follows layout/keyframes; a false crop flag alone
                # must never leave an individual crop executable downstream.
                current_layout, current_focus, current_pair = 'full_frame', None, ()
                transition = 'safety_cut'
                last_switch = layout_since = t
                hold_until = t+cfg['min_hold_seconds']
                start_state = controller.snapshot(t)
                reasons.append('CROP_PREFLIGHT_UNSAFE')
                counts['unsafe_crop_avoided'] += 1
        end_state = controller.snapshot(end)
        if (smart_decision.get('requested_zoom', 1.) > 1.001 and end_state['zoom'] <= 1.001
                and (current_layout == 'full_frame' or not smart_decision['digital_motion_allowed'])):
            counts['zoom_aborted_evaluation_windows'] += 1
        smart_state.current_zoom = end_state['zoom']
        movement = ('slow_push_in' if end_state['zoom']-start_state['zoom'] > 1e-5 else
                    'slow_pull_out' if start_state['zoom']-end_state['zoom'] > 1e-5 else
                    'pan' if math.dist(start_state['center'], end_state['center']) > 1e-5 else 'hold')
        framing = ('original' if current_layout == 'full_frame' else 'two_shot' if current_layout == 'two_shot'
               else 'split' if split else 'close' if face_size * end_state['zoom'] >= cfg['smart_zoom']['close_face_min'] else 'medium')
        camera_mode = ('SOURCE_FULL' if current_layout == 'full_frame' and preserve else 'SOURCE_PRESERVE' if current_layout == 'full_frame' else
                   'STATIC_TWO_SHOT' if current_layout == 'two_shot' else 'SPLIT' if split else 'REACTION' if mode == 'REACTION' else
                   'SMART_RECENTER' if movement == 'pan' and smart_decision['mode'] in {'STATIC_MEDIUM', 'STATIC_CLOSE'} else smart_decision['mode'])
        if current_focus and not geo.get('safe'):
            reasons.append('CROP_PREFLIGHT_UNSAFE')
        reasons = list(dict.fromkeys(reasons or ['stable_decision']))
        if current_focus == person:
            current_role = role
        role = current_role if current_focus else 'SOURCE_PRESERVE'
        focus_conf = (number(obs.get(current_focus, {}).get('detection_confidence')) if role == 'DOMINANT_FACE' else
                      max((_confidence(r) for r in item['voices'] if r.get('person_id') == current_focus), default=0.)) if current_focus else None
        decision = {
            'confidence': focus_conf, 'confidence_is_calibrated': False,
            'reasons': reasons, 'switch_suppressed': suppressed is not None,
            'switch_suppressed_reason': suppressed, 'selected_candidate': chosen['candidate'],
        }
        focus_windows.append(focus_window_evidence(item, current_focus, current_layout, role, reasons, chosen['candidate']))
        sig = (sid, mode, current_layout, current_focus, current_pair, framing, camera_mode, role, planned.get('planner_id') if planned else None)
        row = {
            'broadcast_graphics': list(graphics_cursor.at(mid)),
            'graphics_policy': 'single_copy_source_strip' if current_layout == 'split_candidate' else 'avoid_face_text_overlap',
            'interview_layout': choose_layout(list(obs.values()), list(current_pair) or ([current_focus] if current_focus else []),
                                               union_safe=current_layout == 'two_shot'),
            'camera_evidence_role': role if current_focus else 'SOURCE_CLOSEUP_PRESERVE' if shot.get('shot_type') in {'close_up', 'medium_close_up'} else 'SOURCE_PRESERVE',
            'speaker_identity_confirmed': bool(current_focus and role == 'CONFIRMED_SPEAKER'),
            'camera_state': camera_state(transition, current_layout, movement, mode == 'REACTION', last_person, current_focus),
            'schema_version': '4.3', 'start': t, 'end': end,
            'camera_mode': camera_mode, 'zoom_mode': smart_decision['mode'],
            'smart_zoom': {
                **smart_decision, 'target_person_id': current_focus,
                'source_camera_motion': source_motion_data, 'beat': beat,
                'state_entered_at': smart_state.state_entered_at,
                'last_zoom_event_at': smart_state.last_zoom_event_at if math.isfinite(smart_state.last_zoom_event_at) else None,
            },
            'conversation_mode': mode, 'source_shot_id': sid,
            'audio_speaker': voice, 'audio_speakers': speakers,
            'audio_events': [{'start': t, 'end': end, 'speaker_ids': speakers}],
            'focus_person': current_focus, 'focus_confidence': focus_conf,
            'visible_people': sorted(obs), 'visibility_is_sampled': True,
            'visual_observed_at_start': item['frame']['time'] if item['frame'] else None,
            'visual_observed_at_end': item['frame']['time'] if item['frame'] else None,
            'layout': current_layout, 'framing': framing,
            'camera': {
                'center_start': start_state['center'], 'center_end': end_state['center'],
                'zoom_start': start_state['zoom'], 'zoom_end': end_state['zoom'],
                'zoom_target': controller.target[2], 'movement_style': movement,
                'tracking_mode': 'deadzone_follow' if current_focus else 'source_preserve',
                'transition_in': transition, 'transition_out': 'hold', 'keyframes': [start_state, end_state],
            },
            'crop': {
                'safe': bool(geo.get('safe')), 'rect_end': rect,
                'quality_limited_max_zoom': geo.get('quality_limited_max_zoom', 1.),
                'max_allowed': geo.get('max_zoom', 1.), 'baseline_requires_upscale': geo.get('baseline_requires_upscale'),
                'upscale_ratio': end_state['zoom'] / max(min((base_size(metadata, cfg) or (0, 0, 0, 0))[0] * metadata.get('width', 0) / cfg['output_width'], (base_size(metadata, cfg) or (0, 0, 0, 0))[1] * metadata.get('height', 0) / cfg['output_height']), 1e-9) if current_layout != 'full_frame' else None,
                'max_upscale_ratio': cfg['smart_zoom']['max_upscale_ratio'],
                'requested_zoom': smart_decision['requested_zoom'], 'actual_zoom': end_state['zoom'],
                'limited_by_quality': bool(smart_decision.get('limited_by_quality') or geo.get('limited_by_quality')),
                'quality_unknown': geo.get('quality_unknown'),
                'preflight_reason': geo.get('preflight_reason'),
                'preflight_sample_count': geo.get('preflight_sample_count'),
                'full_frame_policy': 'fit_with_padding' if current_layout == 'full_frame' else None,
            },
            'split': split,
            'reaction': {'emotion': None, 'audio_person': person, 'evidence': ['listener_motion_spike', 'face_visible', 'crop_safe']} if mode == 'REACTION' else None,
            'decision': decision,
            'speaker_switch_rate': {
                'changes_5s': rate5, 'changes_10s': rate10,
                'mean_recent_turn_seconds': sum(recent_turn_durations)/len(recent_turn_durations) if recent_turn_durations else None,
            },
            'continuous_speech_duration': speech_run,
            'global_plan': {'planner_id': planned.get('planner_id'), 'state': planned.get('state'), 'layout': planned.get('layout'), 'focus_person': planned.get('focus_person'), 'reason_code': planned.get('reason_code')} if planned else None,
            'context': {
                'question_ids': [question.get('question_id') for question in qrows],
                'story_arc_ids': [arc.get('story_arc_id') for arc in arows],
                'moment_ids': [moment.get('moment_id') for moment in mrows],
            },
        }
        # Compact decisions while retaining non-linear motion and changes in audio.
        if rows and sig == last_signature and transition == 'hold':
            prior = rows[-1]
            prior['end'] = end
            prior['visible_people'] = sorted(set(prior['visible_people']) & set(row['visible_people']))
            prior['visual_observed_at_end'] = row['visual_observed_at_end']
            prior['continuous_speech_duration'] = speech_run
            prior['focus_confidence'] = min(prior['focus_confidence'], focus_conf) if focus_conf is not None and prior['focus_confidence'] is not None else None
            prior['decision']['reasons'] = list(dict.fromkeys(prior['decision']['reasons']+reasons))
            prior['decision']['switch_suppressed'] |= decision['switch_suppressed']
            if suppressed:
                prior['decision']['switch_suppressed_reason'] = suppressed
            if prior['audio_events'][-1]['speaker_ids'] == speakers:
                prior['audio_events'][-1]['end'] = end
            else:
                prior['audio_events'].append(row['audio_events'][0])
            prior['audio_speakers'] = sorted(set(prior['audio_speakers']) | set(speakers))
            prior['audio_speaker'] = prior['audio_speakers'][0] if len(prior['audio_speakers']) == 1 else None
            cam = prior['camera']
            keys = cam['keyframes']
            moving = any(abs(v) > 1e-5 for v in end_state['velocity'])
            if not moving and len(keys) >= 2 and keys[-1]['center'] == end_state['center'] and keys[-1]['zoom'] == end_state['zoom']:
                keys[-1] = end_state
            else:
                keys.append(end_state)
            cam.update(center_end=end_state['center'], zoom_end=end_state['zoom'], zoom_target=controller.target[2])
            prior['crop']['max_allowed'] = min(prior['crop']['max_allowed'], row['crop']['max_allowed'])
            prior['crop']['rect_end'] = rect
            # Preserve the strongest later editorial beat even when camera mode
            # stays unchanged and adjacent evaluation windows are compacted.
            if row['smart_zoom'].get('beat'):
                prior['smart_zoom']['beat'] = row['smart_zoom']['beat']
            prior['smart_zoom']['requested_zoom'] = max(number(prior['smart_zoom'].get('requested_zoom'), 1.),
                                                          number(row['smart_zoom'].get('requested_zoom'), 1.))
            prior['smart_zoom']['reason_codes'] = list(dict.fromkeys(
                prior['smart_zoom'].get('reason_codes', []) + row['smart_zoom'].get('reason_codes', [])))
        else:
            if rows:
                rows[-1]['camera']['transition_out'] = transition
            row['director_id'] = f'DIRECTOR_{len(rows):06}'
            rows.append(row)
        last_signature = sig
        # Event-based debug with counts; no repeated score dump at every sample.
        dbg_sig = (sig, suppressed, chosen['candidate'], bool(pair_eligible), near_cut, bool(future_voice),
                   tuple(round(v, 3) for v in controller.target))
        if cfg['debug_output'] and dbg_sig != debug_signature:
            debug.append({'time': t, 'conversation_mode': mode, 'candidates': [{**c, **({'pair': list(c['pair'])} if 'pair' in c else {})} for c in candidates],
                          'requested_focus': person, 'kept_focus': current_focus,
                          'switch_suppressed_reason': suppressed,
                          'split_eligibility': {'eligible': bool(pair_eligible),
                            'reason': 'both_contemporary_safe_and_relevant' if pair_eligible else 'insufficient_simultaneous_safe_relevant_evidence',
                            'available_until': item['pair_available_until'] if pair else None},
                          'deadzone_suppressed_moves_total': counts['deadzone_suppressed_moves'],
                          'source_reset': reset, 'lookahead_horizon': min(next_cut, t+cfg['lookahead_seconds']),
                          'future_speaker': future_voice,
                          'state': {'current_focus_person': current_focus, 'current_layout': current_layout,
                            'current_framing': framing, 'current_zoom': controller.zoom.position,
                            'target_zoom': controller.target[2], 'current_center_x': controller.x.position,
                            'current_center_y': controller.y.position, 'target_center': controller.target[:2],
                            'shot_age': t-shot_since, 'layout_age': t-layout_since, 'last_switch_time': last_switch if math.isfinite(last_switch) else None,
                            'last_focus_change_time': last_focus_change if math.isfinite(last_focus_change) else None,
                            'speaker_since': speaker_since, 'hold_until': hold_until,
                            'previous_conversation_mode': previous_mode, 'last_stable_person': last_stable_person,
                            'last_valid_crop': last_valid_crop}})
            debug_signature = dbg_sig
        previous_mode, last_person = mode, person
    # Metrics count actual delivered edits, including safety fallbacks; mode-only
    # interval boundaries do not artificially inflate camera switch rates.
    virtual_durations, virtual_start = [], 0.
    delivered_switches = 0
    previous = None
    for row in rows:
        key = (row['source_shot_id'], row['layout'], row['focus_person'],
               (row.get('split') or {}).get('left_person'), (row.get('split') or {}).get('right_person'))
        if previous is not None and key != previous:
            virtual_durations.append(row['start']-virtual_start)
            virtual_start = row['start']
            if key[0] == previous[0]:
                delivered_switches += 1
        previous = key
    if duration > virtual_start:
        virtual_durations.append(duration-virtual_start)
    counts['director_switches'] = delivered_switches
    fractions = {layout: sum(r['end']-r['start'] for r in rows if r['layout'] == layout)/duration
                 for layout in ('split_candidate', 'two_shot', 'full_frame')}
    metrics = {'camera_director_coverage': sum(row['end'] - row['start'] for row in rows if row.get('focus_person') or row.get('split')) / duration,
                'camera_director_visual_sample_coverage': evidence_seconds/duration,
                'dominant_face_coverage': sum(row['end'] - row['start'] for row in rows if row.get('camera_evidence_role') == 'DOMINANT_FACE') / duration,
                'smart_zoom_enabled': cfg['smart_zoom']['enabled'],
                'zoom_event_count': len(smart_state.events), 'zoom_events_per_minute': len(smart_state.events) * 60 / duration,
                'mean_zoom_factor': sum((row['camera']['zoom_start'] + row['camera']['zoom_end']) / 2 * (row['end'] - row['start']) for row in rows) / duration,
                'max_zoom_factor': max((key['zoom'] for row in rows for key in row['camera']['keyframes']), default=1.),
                'zoom_target_loss_count': sum('TARGET_LOST_DURING_ZOOM' in row['decision']['reasons'] for row in rows),
                'smart_camera_decision_count': sum(row['camera_mode'] not in {'SOURCE_FULL', 'SOURCE_PRESERVE'} for row in rows),
                'safe_zoom_fraction': sum(row['end'] - row['start'] for row in rows if row['crop']['safe'] and row['camera']['zoom_end'] > 1.001) /
                    max(1e-9, sum(row['end'] - row['start'] for row in rows if row['camera']['zoom_end'] > 1.001)),
               'camera_director_timeline_coverage': sum(r['end']-r['start'] for r in rows)/duration,
               'unresolved_focus_fraction': unresolved_seconds/duration,
               'director_switches_per_minute': counts['director_switches']*60/duration,
               'average_director_shot_seconds': sum(virtual_durations)/len(virtual_durations) if virtual_durations else None,
               'split_fraction': fractions['split_candidate'], 'two_shot_fraction': fractions['two_shot'],
               'full_frame_fraction': fractions['full_frame'],
               **{k: counts[k] for k in ('switches_suppressed', 'deadzone_suppressed_moves', 'unsafe_crop_avoided', 'source_shot_resets')},
               'director_intervals': len(rows), 'director_evaluation_windows': len(records),
               'evaluation_windows_with_face_evidence':sum(bool(item['obs'] and any(o.get('face_visible') for o in item['obs'].values())) for item in records),
               'evaluation_windows_with_grounded_speaker':sum(bool(item['confident']) and not item['overlap'] for item in records),
               'evaluation_windows_with_conflicting_person_targets':sum(len(item['confident'])>1 for item in records),
               'evaluation_windows_without_visual_sample':sum(item['frame'] is None for item in records),
               'editorial_beat_raw_windows':counts['editorial_beat_raw_windows'],
               'editorial_beat_eligible_windows':counts['editorial_beat_eligible_windows'],
               'editorial_beat_suppressed_due_to_cut_or_overlap':counts['editorial_beat_suppressed_due_to_cut_or_overlap'],
               'editorial_beat_without_focus_windows':counts['editorial_beat_without_focus_windows'],
               'editorial_beat_with_speaker_focus_windows':counts['editorial_beat_with_speaker_focus_windows'],
               'focused_windows_without_editorial_beat':counts['focused_windows_without_editorial_beat'],
               'observations_per_second': len(vision.get('observations', []))/duration,
               'conversation_modes': dict(Counter(r['conversation_mode'] for r in rows)),
               'elapsed_seconds': time.perf_counter()-started,
               'timeline_json_bytes': len(json.dumps(rows, allow_nan=False).encode()),
               'motion_limits': {k: cfg[k] for k in cfg if k.startswith('max_pan_') or k.startswith('max_zoom_')},
               'planner_agreement_fraction': (sum(r['end']-r['start'] for r in rows
                   if r.get('global_plan') and r['layout'] == r['global_plan'].get('layout')
                   and r.get('focus_person') == r['global_plan'].get('focus_person'))/duration if camera_plan else None),
               'coverage_note': 'Visual coverage is sampled; timeline coverage includes explicit full-frame fallback.'}
    from .preview_verifier import zoom_diagnostics
    delivered_zoom, _ = zoom_diagnostics(rows, duration, cfg['smart_zoom']['min_zoom_duration'])
    zoom_block_reasons = Counter({k.removeprefix('zoom_block_'): v for k,v in counts.items() if k.startswith('zoom_block_')})
    metrics.update(delivered_zoom,
                   proposed_zoom_event_count=len(smart_state.events),
                   zoom_opportunity_window_count=counts['editorial_beat_eligible_windows'],
                   zoom_request_window_count=counts['smart_zoom_requested_windows'],
                   zoom_accepted_event_count=len(smart_state.events),
                   zoom_accepted_window_count=counts['smart_zoom_accepted_windows'],
                   zoom_delivered_event_count=delivered_zoom.get('zoom_event_count', 0),
                   zoom_aborted_window_count=counts['zoom_aborted_evaluation_windows'],
                   zoom_raw_opportunity_window_count=counts['editorial_beat_raw_windows'],
                   zoom_opportunity_outcome_counts={k.removeprefix('zoom_opportunity_outcome_'): v
                       for k, v in counts.items() if k.startswith('zoom_opportunity_outcome_')},
                   zoom_accepted_push_in_event_count=sum(e['mode'] == 'SMART_ZOOM_IN' for e in smart_state.events),
                   zoom_accepted_pull_out_event_count=sum(e['mode'] == 'SMART_ZOOM_OUT' for e in smart_state.events),
                   zoom_block_reason_counts=dict(zoom_block_reasons),
                   zoom_delivery_fraction=(delivered_zoom.get('zoom_event_count', 0) / len(smart_state.events)
                                           if smart_state.events else None),
                   zoom_diagnostics_contract='opportunity_request_accepted_delivered_aborted_v1',
                   focus_evidence_funnel=predecision_evidence,
                   crop_preflight_blocked_windows=counts['crop_preflight_blocked_windows'],
                   zoom_temporal_preflight_rejected_windows=counts['zoom_temporal_preflight_rejected_windows'],
                   visual_only_fallback_windows=counts['visual_only_fallback_windows'],
                   split_preflight_rejected_windows=counts['split_preflight_rejected'],
                   zoom_zero_root_cause=('NO_GROUNDED_EDITORIAL_BEAT' if not counts['editorial_beat_raw_windows']
                      else 'CUT_OR_OVERLAP_BLOCKED_BEATS' if not counts['editorial_beat_eligible_windows']
                      else 'NO_SAFE_FOCUSED_TARGET' if not counts['editorial_beat_with_speaker_focus_windows']
                      else 'SAFETY_OR_DURATION_GATES' if not smart_state.events else None))
    reason_seconds = Counter()
    resolved_seconds = Counter()
    for window in focus_windows:
        reason_seconds[window['reason_code']] += window['end']-window['start']
        resolved_seconds[window['reason_code']] += window['coverage_effect']['resolved_focus_seconds']
    metrics['focus_decision_audit'] = {
        'method': 'per_evaluation_window_sampled_evidence_not_identity_accuracy',
        'duration_seconds': dict(reason_seconds), 'resolved_focus_seconds': dict(resolved_seconds),
        'fractions_of_video': {key: value/duration for key, value in reason_seconds.items()}}
    status = 'unavailable' if not evidence_seconds else 'partial' if unresolved_seconds or evidence_seconds < .8*duration else 'ok'
    return ok({'timeline': rows, 'focus_window_audit': focus_windows, 'metrics': metrics, 'debug': {'schema_version': '3.0', 'events': debug, 'counts': dict(counts)} if cfg['debug_output'] else None,
               'zoom_events': smart_state.events,
               'config': cfg}, status, ['Camera Director: recomendações editoriais conservadoras; confidence não é probabilidade calibrada.'])
