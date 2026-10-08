"""Rebuild S7 subtitle review files from a completed analysis, with no ASR inference.

Usage (Windows):
  .venv\\Scripts\\python.exe scripts\\dev\\audit_subtitles_s7.py C:\\analyses\\EMERSON_CLOVIS --output C:\\analyses\\s7_review
  .venv\\Scripts\\python.exe scripts\\dev\\audit_subtitles_s7.py analysis.zip --output C:\\analyses\\s7_review
"""
import argparse
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.subtitle_review import review_selected_clips, write_review_kit
from ldporto.config import load_config


class Snapshot:
    def __init__(self, path):
        self.path = Path(path)
        self.archive = zipfile.ZipFile(self.path) if self.path.is_file() and zipfile.is_zipfile(self.path) else None
        if not self.archive and not self.path.is_dir():
            raise FileNotFoundError(path)

    def read(self, name):
        if self.archive:
            files = self.archive.namelist()
            matches = [name] if name in files else [f for f in files if f.endswith('/' + name)]
            if len(matches) != 1:
                return None
            text = self.archive.read(matches[0]).decode('utf-8-sig')
        else:
            file = self.path / name
            if not file.is_file():
                return None
            text = file.read_text(encoding='utf-8-sig')
        if name.endswith('jsonl'):
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        return json.loads(text)

    def close(self):
        if self.archive:
            self.archive.close()


def audit(source, output, *, explicit_ids=None):
    files = Snapshot(source)
    try:
        words = files.read('words.json')
        source_scope = 'full_words'
        if words is None:
            words = files.read('transcript/relevant_words.jsonl')
            source_scope = 'partial_candidate_words'
        if not isinstance(words, list):
            raise ValueError('words.json ausente. Pacote sem palavras nao permite medir os 24,2%.')
        candidates = files.read('main_moments.json')
        analysis = files.read('analysis.json') or {}
        if not isinstance(candidates, list):
            candidates = analysis.get('main_moments')
        selection = files.read('editorial_shortlist.json')
        if isinstance(selection, dict):
            selection = selection.get('candidate_ids')
        if selection is None:
            selection = analysis.get('editorial_shortlist')
        package = files.read('second_curation_package.json') or {}
        if not isinstance(candidates, list):
            candidates = package.get('candidates')
        if selection is None:
            selection = package.get('filtering_summary', {}).get('default_shortlist_ids')
        if not isinstance(candidates, list):
            raise ValueError('main_moments.json/second_curation_package.json ausente: sem candidatos nao ha revisao por corte.')
        if explicit_ids is not None:
            selection = explicit_ids
        if not isinstance(selection, list):
            raise ValueError('editorial_shortlist nao encontrado; informe --candidate-id ID (repetivel).')
        alt = files.read('targeted_asr_repair.json') or {}
        events = files.read('audio_events.json') or []
        config = load_config()
        report = review_selected_clips(words, candidates, selected_ids=selection,
                      alternatives=alt.get('alternatives', []),
                      events=events if isinstance(events, list) else events.get('events', []),
                      caption_config=config['captions'], threshold=config['transcription']['low_confidence'])
        report['source_scope'] = source_scope
        report['benchmark_24_2_comparable'] = source_scope == 'full_words'
        if source_scope != 'full_words':
            report['measurement_warning'] = 'Palavras parciais: porcentagem calculada NAO representa video completo.'
        return write_review_kit(output, report)
    finally:
        files.close()


def main():
    parser = argparse.ArgumentParser(description='Auditoria S7: legenda, baixa confiança e revisão por corte (offline).')
    parser.add_argument('analysis', nargs='?', help='Pasta de análise ou ZIP; dispensável com --apply-reviewed-csv')
    parser.add_argument('--output', required=True)
    parser.add_argument('--candidate-id', action='append', dest='candidate_ids', default=None)
    parser.add_argument('--apply-reviewed-csv', help='CSV assinado após escutar o áudio; valida e exporta SRT revisado')
    parser.add_argument('--review-dir', help='Pasta com subtitle_review_s7.json e .draft.srt')
    args = parser.parse_args()
    if args.apply_reviewed_csv:
        from ldporto.subtitle_review import apply_human_subtitle_review
        if not args.review_dir:
            parser.error('--review-dir é obrigatório com --apply-reviewed-csv')
        result = apply_human_subtitle_review(args.review_dir, args.apply_reviewed_csv, args.output)
    else:
        if not args.analysis:
            parser.error('analysis é obrigatório para construir revisão offline')
        result = audit(args.analysis, args.output, explicit_ids=args.candidate_ids)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
