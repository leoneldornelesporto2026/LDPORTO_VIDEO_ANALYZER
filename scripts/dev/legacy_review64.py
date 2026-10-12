"""Auditar evidências históricas sem ASR/OCR/LLM; criar entrada de revisão opcional.

A entrada derivada é SOMENTE para revisão humana; não é replay verificado de 21.
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ldporto.legacy_review import plan_legacy_review, create_legacy_review_input
from ldporto.export_privacy import safe_path


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--analysis', required=True)
    p.add_argument('--report', help='Arquivo JSON em pasta separada da análise (dry-run)')
    p.add_argument('--apply-review', action='store_true', help='Criar ENTRADA DE REVISÃO, sem executar etapa 21')
    p.add_argument('--reviewed-plan', help='Arquivo JSON de um plano anterior explicitamente revisado')
    p.add_argument('--output', help='Novo diretório de saída; nunca dentro da análise original')
    args = p.parse_args(argv)
    if args.apply_review and (not args.reviewed_plan or not args.output):
        p.error('--apply-review requer --reviewed-plan e --output')
    if not args.apply_review and (args.reviewed_plan or args.output):
        p.error('--reviewed-plan/--output exigem --apply-review')
    source = safe_path(args.analysis)
    try:
        plan = plan_legacy_review(source)
        if args.apply_review:
            reviewed = json.loads(safe_path(args.reviewed_plan).read_text('utf-8'))
            if (reviewed.get('mode') != 'legacy_artifact_review'
                    or reviewed.get('historical_authentication') != 'not_established'
                    or reviewed.get('source_reference_hashes') != plan['source_reference_hashes']
                    or reviewed.get('signed_export_hashes') != plan['signed_export_hashes']):
                raise ValueError('reviewed_plan_mismatch')
            result = create_legacy_review_input(source, args.output,
                                                expected_hashes=reviewed['source_reference_hashes'])
        else:
            result = plan
        if args.report:
            path = Path(args.report).absolute()
            if path.is_relative_to(source):
                raise ValueError('report_inside_original_analysis')
            path.parent.mkdir(parents=True, exist_ok=True)
            safe_path(path.parent)
            if path.exists():
                safe_path(path)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True)
                tmp = Path(handle.name)
            try:
                os.replace(tmp, path)
            finally:
                tmp.unlink(missing_ok=True)
        print(json.dumps({'status': result['status'], 'review_input_possible': plan['review_input_possible'],
                          'historical_authentication': 'not_established',
                          'publication_ready': False}, ensure_ascii=False))
        return 0 if plan['review_input_possible'] else 2
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        # Only error class and controlled reason; never leak input data.
        print(json.dumps({'status': 'blocked', 'reason': str(exc) if isinstance(exc, ValueError)
                          else type(exc).__name__, 'publication_ready': False}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
