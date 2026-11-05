# Repository Structure

Runtime: Python 3.11.x. The root is the public interface, not artifact staging.

| Location | Responsibility |
| --- | --- |
| src/ldporto/ | Runtime engines, contracts, progress, replay and core package |
| src/tests/ | Canonical pytest suite and deterministic fixtures |
| config/ | Shared configuration; no credentials |
| schemas/ | Versioned JSON contracts and backward readers |
| requirements.txt | Base dependencies |
| requirements/ | Separate optional/development groups |
| scripts/windows/ | Install, diagnostics, GPU, Ollama and test tools |
| scripts/dev/, scripts/export/ | Canonical developer/export implementations |
| docs/setup/, troubleshooting/ | Installation and operational guides |
| docs/releases/, reports/ | Historical release evidence, not current runtime inputs |
| docs/archive/, briefings/ | Explicit historical records and preserved engineering briefs |
| src/tests/fixtures/historical_evidence/ | Read-only regression ZIPs with ORIGEM.json hashes |
| analysis/ | Ignored local analysis, checkpoints and replay results |
| pacotes_para_enviar/ | Ignored product packages: SECOND_CURATION and FORENSIC_REVIEW |
| .cache/ | Ignored tools, benchmark extraction and local runtime history |

Root allowlist: .gitignore, ABRIR_ANALYZER.bat, analyze.py, app.py, install.py,
README.md, requirements.txt, pytest.ini and CHANGELOG_V43.md. The seven auxiliary root Windows .bat entrypoints are retained for compatibility:
five delegate to scripts/windows/, while the two diagnostics call the existing
Python doctor and CUDA check directly. ABRIR_ANALYZER.bat is the GUI launcher.
The former scripts/windows/diagnostics/ paths did not exist. The public
compare_runs.py/exportar_ldporto.py entrypoints are also preserved.
See scripts/README.md for an operational inventory.

Root PROJECT_EXPORT_* and WORK_PACKAGE_* are generated package outputs. Existing
user-modified .package/PROJECT_EXPORT_* files are preserved unchanged. Historical delivery manifests v3
and v4 are intentionally distinct immutable snapshots in docs/releases/.
