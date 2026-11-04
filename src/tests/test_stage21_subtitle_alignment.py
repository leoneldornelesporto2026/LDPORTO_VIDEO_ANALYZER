"""Synthetic offline captions: no recognition, real listening or media required."""
import csv
import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from ldporto.subtitle_review import (review_selected_clips, write_review_kit,
    apply_human_subtitle_review, approve_reviewed_subtitles, subtitle_finalization_gate)


def word(text='fixture.', start=101., end=102., **extra):
    return dict(word=text, raw=text, start=start, end=end, confidence=.9,
                needs_review=False, **extra)


def report(words=None, start=100., end=110.):
    return review_selected_clips(words if words is not None else [word()],
        [dict(candidate_id='CUT', start=start, end=end)], selected_ids=['CUT'])


def prepare(tmp_path, dossier=None, **changes):
    kit, out, review = tmp_path/'kit', tmp_path/'out', tmp_path/'listening.csv'
    write_review_kit(kit, dossier or report())
    with (kit/'subtitle_human_review.csv').open(encoding='utf-8-sig', newline='') as source:
        rows = list(csv.DictReader(source))
    for row in rows:
        row.update(decision='APPROVED', audio_listened='YES', reviewer='synthetic tester',
            verified_text=row['asr_text'], verified_start=row['start_asr'], verified_end=row['end_asr'])
        row.update(changes)
    with review.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return kit, review, out


def approve(out):
    digest = hashlib.sha256((out/'CUT.human_reviewed.srt').read_bytes()).hexdigest()
    return approve_reviewed_subtitles(out, 'CUT', expected_sha256=digest,
        reviewer='synthetic tester', audio_listened=True)


def test_correct_timecode_relative_to_cut_and_original_preserved(tmp_path):
    dossier = report()
    original = deepcopy(dossier)
    kit, review, out = prepare(tmp_path, dossier)
    before = {p.name: p.read_bytes() for p in kit.iterdir()}
    assert '00:00:01,000 --> 00:00:02,000' in (kit/'CUT.draft.srt').read_text('utf-8')
    apply_human_subtitle_review(kit, review, out)
    assert '00:00:01,000 --> 00:00:02,000' in (out/'CUT.human_reviewed.srt').read_text('utf-8')
    assert not subtitle_finalization_gate(out, 'CUT')['subtitles_final_allowed']
    approval = approve(out)
    assert approval['srt_sha256'] == hashlib.sha256((out/'CUT.human_reviewed.srt').read_bytes()).hexdigest()
    assert subtitle_finalization_gate(out, 'CUT')['subtitles_final_allowed']
    assert not subtitle_finalization_gate(out, 'CUT')['publication_ready']
    assert dossier == original
    assert before == {p.name: p.read_bytes() for p in kit.iterdir()}


def test_drift_requires_explicit_resolution_after_listening(tmp_path):
    kit, review, out = prepare(tmp_path, verified_start='102', verified_end='103')
    with pytest.raises(ValueError, match='caption_temporal_drift'):
        apply_human_subtitle_review(kit, review, out)
    assert not out.exists()
    kit, review, out = prepare(tmp_path, verified_start='102', verified_end='103',
        resolved_issue_codes='caption_temporal_drift')
    apply_human_subtitle_review(kit, review, out)
    provenance = json.loads((out/'REVIEW_PROVENANCE.json').read_text('utf-8'))
    assert provenance['caption_decisions']['CUT_CAP_000000']['resolved_issue_codes'] == ['caption_temporal_drift']


@pytest.mark.parametrize('words,issue', [
    ([word('corta—', 99.5, 100.1)], 'cut_splits_word'),
    ([word('corta—')], 'interrupted_or_incomplete_word'),
    ([word(end=101.1)], 'caption_duration_too_short'),
    ([word(end=105.)], 'caption_duration_too_long'),
    ([word('voz A.', 101, 103, speaker='A'), word('voz B.', 102, 104, speaker='B')], 'multiple_voices_overlap'),
    ([word('primeira.', 101, 103), word('segunda.', 102, 104)], 'caption_overlap'),
])
def test_critical_fixtures_detected_and_blocked(tmp_path, words, issue):
    dossier = report(words)
    assert issue in dossier['candidates']['CUT']['issue_counts']
    kit, review, out = prepare(tmp_path, dossier)
    with pytest.raises(ValueError):
        apply_human_subtitle_review(kit, review, out)
    assert not out.exists()


def test_two_sequential_voices_are_not_invented_overlap():
    dossier = report([word('A.', 101, 102, speaker='A'), word('B.', 103, 104, speaker='B')])
    assert len(dossier['candidates']['CUT']['captions']) == 2
    assert 'multiple_voices_overlap' not in dossier['candidates']['CUT']['issue_counts']


def test_phrase_split_uses_source_context_without_inventing_text(tmp_path):
    words = [word('porque', 99.5, 100), word('eu', 100, 101), word('continuo.', 101, 102)]
    dossier = report(words, end=101)
    clip = dossier['candidates']['CUT']
    assert 'phrase_boundary_requires_listening' in clip['issue_counts']
    assert clip['captions'][0]['asr_text'] == 'eu'
    assert clip['captions'][0]['final_text'] is None
    kit, review, out = prepare(tmp_path, dossier)
    with pytest.raises(ValueError, match='phrase_boundary_requires_listening'):
        apply_human_subtitle_review(kit, review, out)


@pytest.mark.parametrize('changed', ['srt', 'csv', 'report', 'provenance'])
def test_modifications_invalidate_hash_approval(tmp_path, changed):
    kit, review, out = prepare(tmp_path)
    apply_human_subtitle_review(kit, review, out)
    approve(out)
    paths = dict(srt=out/'CUT.human_reviewed.srt', csv=review,
                 report=kit/'subtitle_review_s7.json', provenance=out/'REVIEW_PROVENANCE.json')
    with paths[changed].open('ab') as stream:
        stream.write(b'\n')
    assert not subtitle_finalization_gate(out, 'CUT')['subtitles_final_allowed']


def test_approval_requires_exact_hash_and_listening(tmp_path):
    kit, review, out = prepare(tmp_path)
    apply_human_subtitle_review(kit, review, out)
    with pytest.raises(ValueError, match='hash'):
        approve_reviewed_subtitles(out, 'CUT', expected_sha256='0'*64, reviewer='fixture', audio_listened=True)
    with pytest.raises(ValueError, match='listening'):
        approve_reviewed_subtitles(out, 'CUT', expected_sha256='0'*64, reviewer='fixture', audio_listened=False)


def test_source_changed_before_import_rejected(tmp_path):
    kit, review, out = prepare(tmp_path)
    with (kit/'subtitle_review_s7.json').open('a') as stream:
        stream.write('\n')
    with pytest.raises(ValueError, match='Stale'):
        apply_human_subtitle_review(kit, review, out)


def test_empty_evidence_cannot_be_approved(tmp_path):
    kit = tmp_path/'kit'
    write_review_kit(kit, report([]))
    with pytest.raises(ValueError, match='Missing subtitle evidence'):
        apply_human_subtitle_review(kit, kit/'subtitle_human_review.csv', tmp_path/'out')


def test_cli_gate_has_blocking_exit_code_and_accepts_exact_version(tmp_path):
    kit, review, out = prepare(tmp_path)
    apply_human_subtitle_review(kit, review, out)
    script = Path(__file__).resolve().parents[2]/'scripts/dev/audit_subtitles_s7.py'
    cmd = [sys.executable, str(script), '--output', str(out), '--check-srt-approval', 'CUT']
    blocked = subprocess.run(cmd, capture_output=True, text=True)
    assert blocked.returncode == 2
    assert json.loads(blocked.stdout)['subtitles_final_allowed'] is False
    digest = hashlib.sha256((out/'CUT.human_reviewed.srt').read_bytes()).hexdigest()
    approved = subprocess.run([sys.executable, str(script), '--output', str(out),
        '--approve-srt', 'CUT', '--srt-sha256', digest, '--reviewer', 'synthetic tester',
        '--audio-listened'], capture_output=True, text=True)
    assert approved.returncode == 0, approved.stderr
    passed = subprocess.run(cmd, capture_output=True, text=True)
    assert passed.returncode == 0
    assert json.loads(passed.stdout)['subtitles_final_allowed'] is True
