import json
import zipfile
from pathlib import Path

import pytest

from ldporto.subtitle_review import review_selected_clips, write_review_kit
from ldporto.targeted_asr import select_repair_windows
from ldporto.timeline import captions
from ldporto.config import load_config


def word(text, start, end, **kwargs):
    return {'word': text, 'raw': ' ' + text, 'start': start, 'end': end,
            'confidence': .9, 'needs_review': False, **kwargs}


def candidate(ident='C1', start=0., end=7.):
    return {'moment_id': ident, 'start': start, 'end': end,
            'default_shortlist_eligible': True, 'ideal_start': start, 'ideal_end': end}


def test_original_24_percent_style_metric_is_separate_from_derived_flags():
    words = [word('a', 0, 1, speech_overlap=True), word('b', 1, 2, needs_review=True)]
    # A pre-flagged word and a new overlap signal are different measured buckets.
    report = review_selected_clips(words, [candidate()], selected_ids=['C1'])
    assert report['originally_flagged_for_review'] == 1
    assert report['original_review_fraction'] == .5
    assert report['words_flagged_for_review'] == 2
    assert report['global_word_reasons']['overlapping_speech'] == 1


def test_empty_selected_ids_means_no_clips_no_targeted_windows():
    words = [word('duvidosa', 1, 2, needs_review=True)]
    report = review_selected_clips(words, [candidate()], selected_ids=[])
    assert report['selected_candidate_count'] == 0
    assert select_repair_windows(words, [candidate()], [], [], 8, shortlist_ids=[]) == []


def test_targeted_covers_shortlist_hook_and_payoff_even_without_low_probability():
    rows = select_repair_windows([word('ok', 2, 3)], [candidate()], [], [], 7,
                                 max_regions=8, max_audio_seconds=30, shortlist_ids=['C1'])
    assert {x['priority_reason'] for x in rows} == {'SHORTLIST_HOOK', 'SHORTLIST_PAYOFF'}


def test_targeted_respects_budget_and_keeps_exact_selection():
    c = [candidate('A', 0, 7), candidate('B', 25, 32), candidate('C', 60, 67)]
    rows = select_repair_windows([], c, [], [], 90, 2, 9, shortlist_ids=['A', 'C'])
    assert len(rows) <= 2 and sum(x['end']-x['start'] for x in rows) <= 9
    assert all('B' not in x['evidence_refs'] for x in rows)


def test_overlapping_speech_and_laugh_event_prompt_review_not_auto_transcription():
    words = [word('mas', 1, 1.5, speech_overlap=True), word('eu', 1.5, 2.1)]
    events = [{'type': 'laughter', 'start': .8, 'end': 2.4, 'method': 'panns_clipwise'}]
    report = review_selected_clips(words, [candidate()], ['C1'], events=events)
    clip = report['candidates']['C1']
    flags = clip['captions'][0]['issue_codes']
    assert 'overlapping_speech' in flags
    assert 'laughter_near_speech_review_audio' in flags
    assert clip['captions'][0]['final_text'] is None
    assert clip['approval_state'] == 'HUMAN_AUDIO_REVIEW_REQUIRED'


def test_asr_alternatives_never_replace_original_joke():
    words = [word('piada', 1, 2)]
    alt = [{'start': 0, 'end': 3, 'selected_text': 'piada', 'alternatives':
            [{'source': 'original_targeted', 'text': 'outra palavra', 'comparison':
              {'independent_audio_verification': False}}]}]
    report = review_selected_clips(words, [candidate()], ['C1'], alternatives=alt)
    assert report['candidates']['C1']['captions'][0]['asr_text'] == 'piada'
    assert report['candidates']['C1']['asr_alternatives'][0]['replacement_applied'] is False


def test_no_karaoke_based_solely_on_high_whisper_confidence():
    words = [word('perfeito', 1, 2, confidence=.99)]
    result = review_selected_clips(words, [candidate()], ['C1'])
    assert not result['candidates']['C1']['karaoke_allowed']
    assert 'word_alignment_not_verified' in result['candidates']['C1']['captions'][0]['issue_codes']


def test_verified_word_timestamps_can_opt_into_karaoke_but_not_publish():
    words = [word('teste', 1, 2, alignment_verified=True, audio_verified=True)]
    report = review_selected_clips(words, [candidate()], ['C1'])
    assert report['candidates']['C1']['karaoke_allowed']
    assert not report['candidates']['C1']['publication_ready']
    assert report['candidates']['C1']['approval_state'] == 'HUMAN_AUDIO_REVIEW_REQUIRED'


def test_interrupted_word_needs_audio_listening():
    result = review_selected_clips([word('mas—', 1, 2)], [candidate()], ['C1'])
    assert 'interrupted_or_incomplete_word' in result['candidates']['C1']['captions'][0]['issue_codes']


def test_missing_words_cannot_be_treated_as_approved_subtitles():
    result = review_selected_clips([], [candidate()], ['C1'])
    assert not result['candidates']['C1']['karaoke_allowed']
    assert result['candidates']['C1']['issue_counts']['no_words_in_candidate'] == 1


def test_csv_srt_review_files_and_no_auto_approval(tmp_path):
    report = review_selected_clips([word('graça', 1, 2)], [candidate()], ['C1'])
    result = write_review_kit(tmp_path, report)
    assert result['caption_count'] == 1
    assert '00:00:01,000 --> 00:00:02,000' in (tmp_path/'C1.draft.srt').read_text('utf-8')
    assert 'verified_text' in (tmp_path/'subtitle_human_review.csv').read_text('utf-8-sig')
    assert json.loads((tmp_path/'subtitle_review_s7.json').read_text('utf-8'))['audio_verification_performed'] is False


def test_csv_transcript_formula_injection_neutralized(tmp_path):
    report = review_selected_clips([word('=1+1', 1, 2)], [candidate()], ['C1'])
    write_review_kit(tmp_path, report)
    assert "'=1+1" in (tmp_path/'subtitle_human_review.csv').read_text('utf-8-sig')


def test_existing_caption_generator_keeps_draft_and_blocks_unverified_karaoke():
    result = captions([word('oi', 1, 2)], load_config()['captions'])
    assert result[0]['caption_status'] == 'DRAFT_REQUIRES_HUMAN_REVIEW'
    assert not result[0]['karaoke_eligible']


def test_auditor_offline_folder_and_zip(tmp_path):
    from scripts.dev.audit_subtitles_s7 import audit
    analysis = tmp_path/'analysis'
    analysis.mkdir()
    (analysis/'words.json').write_text(json.dumps([word('hello', 1, 2)]), encoding='utf-8')
    (analysis/'main_moments.json').write_text(json.dumps([candidate()]), encoding='utf-8')
    (analysis/'editorial_shortlist.json').write_text(json.dumps(['C1']), encoding='utf-8')
    folder = audit(analysis, tmp_path/'from_folder')
    assert folder['candidate_count'] == 1
    bundle = tmp_path/'analysis.zip'
    with zipfile.ZipFile(bundle, 'w') as archive:
        for item in analysis.iterdir():
            archive.write(item, 'nested/' + item.name)
    zip_result = audit(bundle, tmp_path/'from_zip')
    assert zip_result['candidate_count'] == 1


def test_auditor_requires_actual_shortlist(tmp_path):
    from scripts.dev.audit_subtitles_s7 import audit
    analysis = tmp_path/'analysis'
    analysis.mkdir()
    (analysis/'words.json').write_text('[]')
    (analysis/'main_moments.json').write_text(json.dumps([candidate()]))
    with pytest.raises(ValueError, match='editorial_shortlist'):
        audit(analysis, tmp_path/'output')


def test_alignment_only_is_not_enough_to_enable_karaoke():
    report = review_selected_clips([word('ok', 1, 2, alignment_verified=True)], [candidate()], ['C1'])
    assert not report['candidates']['C1']['karaoke_allowed']
    assert report['candidates']['C1']['word_alignment_verified']


def test_selected_asr_excludes_flagged_outside_shortlist():
    words = [word('flag', 1, 2, needs_review=True), word('flag', 50, 51, needs_review=True)]
    result = select_repair_windows(words, [candidate('IN', 0, 8)], [], [], 100,
                                   shortlist_ids=['IN'])
    assert result and all(item['end'] <= 10 for item in result)


def test_unsigned_csv_does_not_produce_final_subtitles(tmp_path):
    from ldporto.subtitle_review import apply_human_subtitle_review
    review_dir = tmp_path/'input'
    write_review_kit(review_dir, review_selected_clips([word('gíria', 1, 2)], [candidate()], ['C1']))
    with pytest.raises(ValueError, match='Unapproved'):
        apply_human_subtitle_review(review_dir, review_dir/'subtitle_human_review.csv', tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_human_review_csv_creates_srt_without_changing_raw(tmp_path):
    import csv
    from ldporto.subtitle_review import apply_human_subtitle_review
    review_dir = tmp_path/'input'
    write_review_kit(review_dir, review_selected_clips([word('trocado', 1, 2)], [candidate()], ['C1']))
    with (review_dir/'subtitle_human_review.csv').open('r', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    rows[0].update(decision='APPROVED', audio_listened='YES', reviewer='humano',
                   verified_text='É a graça!', verified_start='1.1', verified_end='1.9')
    csv_out = tmp_path/'approved.csv'
    with csv_out.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    result = apply_human_subtitle_review(review_dir, csv_out, tmp_path/'out')
    assert result['status'] == 'HUMAN_REVIEW_FIELDS_COMPLETE'
    assert result['publication_ready'] is False
    assert 'É a graça!' in (tmp_path/'out'/'C1.human_reviewed.srt').read_text('utf-8')
    assert 'trocado' in (review_dir/'C1.draft.srt').read_text('utf-8')
    assert json.loads((tmp_path/'out'/'REVIEW_PROVENANCE.json').read_text('utf-8'))['word_karaoke_approved'] is False


def test_human_review_rejects_timestamps_outside_cut(tmp_path):
    import csv
    from ldporto.subtitle_review import apply_human_subtitle_review
    review_dir = tmp_path/'input'
    write_review_kit(review_dir, review_selected_clips([word('ok', 1, 2)], [candidate()], ['C1']))
    with (review_dir/'subtitle_human_review.csv').open('r', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    rows[0].update(decision='APPROVED', audio_listened='YES', reviewer='humano',
                   verified_text='ok', verified_start='6.9', verified_end='8.0')
    csv_out = tmp_path/'outside.csv'
    with csv_out.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match='outside clip'):
        apply_human_subtitle_review(review_dir, csv_out, tmp_path/'final')
