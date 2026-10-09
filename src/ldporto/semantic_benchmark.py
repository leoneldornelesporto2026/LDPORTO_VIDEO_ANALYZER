"""Offline metric parsing and hash-bound human review for isolated Ollama A/B."""
import csv
import math
from pathlib import Path

from .core import digest


def number(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        return None
    return value


def parse_metrics(meta):
    """Accept Ollama API fields or normalized chat metadata; missing proof stays null."""
    result = {}
    for name in ('total_duration', 'load_duration', 'eval_duration', 'prompt_eval_duration'):
        result[name + '_ns'] = number(meta.get(name + '_ns', meta.get(name)))
    for name in ('eval_count', 'prompt_eval_count'):
        value = number(meta.get(name))
        result[name] = value if value is not None and value == int(value) else None
    count, duration = result['eval_count'], result['eval_duration_ns']
    result['tokens_per_second'] = count * 1e9 / duration if count is not None and duration else None
    return result


def benchmark_hash(report):
    return digest({k: v for k, v in report.items() if k not in ('quality_review', 'acceptance', 'benchmark_sha256')})


def quality_approved(report):
    """Human ratings are declarations, never inferred from valid JSON or counts.

    Review: reviewer, benchmark_sha256, samples[{index, repeat, legacy/compact:
    {qa, stories, ranking}}]. Ratings 0..1 use a documented human rubric.
    Every compact rating must be >= .8 and >= its paired baseline rating.
    """
    review = report.get('quality_review') or {}
    if not isinstance(review, dict):
        return False
    if (report.get('scope') != 'non_destructive_model_AB_test' or
            review.get('benchmark_sha256') != benchmark_hash(report) or
            not isinstance(review.get('reviewer'), str) or not review['reviewer'].strip() or
            not isinstance(review.get('rubric'), str) or not review['rubric'].strip()):
        return False
    samples = report.get('samples') or []
    ratings = review.get('samples') or []
    if not isinstance(ratings, list) or not samples or len(ratings) != len(samples):
        return False
    seen = set()
    for sample in samples:
        key = (sample.get('index'), sample.get('repeat', 0))
        matches = [r for r in ratings if isinstance(r, dict) and (r.get('index'), r.get('repeat', 0)) == key]
        if key in seen or len(matches) != 1:
            return False
        seen.add(key)
        for mode in ('legacy', 'compact'):
            row = (sample.get('modes') or {}).get(mode) or {}
            if (row.get('status') != 'valid_first_pass' or row.get('grounded_output') is None or
                    row.get('output_sha256') != digest(row['grounded_output'])):
                return False
        rating = matches[0]
        if not all(isinstance(rating.get(mode), dict) for mode in ('legacy', 'compact')):
            return False
        for dimension in ('qa', 'stories', 'ranking'):
            a = number((rating.get('legacy') or {}).get(dimension))
            b = number((rating.get('compact') or {}).get(dimension))
            if a is None or b is None or a > 1 or b > 1 or b < .8 or b < a:
                return False
    return True


def write_csv(report, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fields = ('model', 'model_digest', 'ollama_version', 'seed',
              'index', 'repeat', 'subset_sha256', 'mode', 'status', 'system_prompt_chars',
              'elapsed_seconds', 'attempts', 'retries', 'eval_count', 'prompt_eval_count',
              'total_duration_ns', 'load_duration_ns', 'eval_duration_ns', 'prompt_eval_duration_ns',
              'tokens_per_second', 'topic_count', 'moment_count', 'output_sha256', 'error_type')
    for mode in ('legacy', 'compact'):
        with (directory / (mode + '.csv')).open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for sample in report['samples']:
                row = dict(sample['modes'][mode], index=sample['index'], repeat=sample['repeat'],
                           subset_sha256=sample['subset_sha256'], mode=mode)
                provenance = report.get('provenance') or {}
                row.update({key: provenance.get(key) for key in ('model', 'model_digest', 'ollama_version')})
                row['seed'] = (provenance.get('options') or {}).get('seed')
                writer.writerow({field: row.get(field) for field in fields})
