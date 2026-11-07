# Versão Git da análise R6 — escuta, transcrição e evidências

## Responsabilidade de cada etapa

1. Analyzer: analisa o vídeo completo e entrega transcrição literal, timestamps e evidências no ZIP canônico R6. Não certifica as palavras nem cria legendas finais.
2. Curator: recebe em input/analyzer/<video_id>/<run_id> e faz **segunda conferência do áudio**, revisando termos, idioma, pontuação, contexto, duração e sincronização. Gera SRT/ASS específicos por Reel/Story. Nunca marca revisão humana automaticamente.
3. Studio R57: só inclui legenda após a segunda curadoria confirmar texto + áudio e permitir o modo subtitles. A prévia anterior continua preservada até uma nova renderização.

## Publicar análise textual no Git, mediante revisão

O código `scripts/dev/export_r6_git_review.py` cria **snapshots versionáveis de todos os membros textuais canônicos do ZIP oficial R6**. Inclui transcrição SRT, segmentos/JSONL, scores, catálogo de candidatos, câmera, roteiro, provas de origem e manifesto SHA256 quando presentes no ZIP. Objetos visuais e binários são inventariados por nome/hash/tamanho, **não copiados**.

Na raiz do Analyzer, com ambos os projetos em develop:

Inspecionar sem escrever:

    python scripts/dev/export_r6_git_review.py --delivery "C:\Users\leone\Documentos\Meus Projetos\LDPORTO_VIDEO_CURATOR\input\analyzer\Eo2bUJcxASI\2131f80ae982b4dc"

Gerar snapshot para inspeção local:

    python scripts/dev/export_r6_git_review.py --delivery "C:\Users\leone\Documentos\Meus Projetos\LDPORTO_VIDEO_CURATOR\input\analyzer\Eo2bUJcxASI\2131f80ae982b4dc" --save --confirm-git-text-review

Destino padrão: docs/analyzer_runs/<video_id>/<run_id>_<ZIP_sha_prefix>/. Cada arquivo textual mantém seu conteúdo integral em `evidence/<caminho-original>` no snapshot; o manifesto lista também os binários excluídos, sua origem e hashes.

Revisar conteúdo antes de versionar:

    git status --short
    Get-Content -LiteralPath "docs/analyzer_runs/<video_id>/<run_id>_<sha>/README.md"

Depois da revisão humana de confidencialidade, dados pessoais, direitos e segredos, o operador pode executar `git add docs/analyzer_runs/<video_id>/<run_id>_<sha>` e um commit local. **O script não executa git add, commit, push, merge ou deploy.**

## Limites e rastreabilidade

- `analysis/`, mídia, modelos, imagens, prévias e ZIPs continuam ignorados. Snapshot contém **todos os textos do ZIP R6 oficial**, não todos os arquivos temporários fora dele.
- O SHA256 do MP4 e do ZIP R6 permanecem no manifesto. Não se presume que a transcrição original seja 100% correta.
- O `.srt` é exceção explícita apenas sob `docs/analyzer_runs/`, não em diretórios de runtime.
- Os snapshots são idempotentes e não sobrescrevem alterações; se houver nova análise, um novo run/hash ganha outra pasta.
- Snapshot não equivale a material aprovado para publicação. Nenhuma mídia é disponibilizada pelo script.

### Testes

    python -m unittest discover -s src/tests -p test_r6_git_evidence.py -v