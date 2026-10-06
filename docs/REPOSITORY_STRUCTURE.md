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
| analysis/ | Ignored local analysis, checkpoints and replay results |
| pacotes_para_enviar/ | Ignored product packages: SECOND_CURATION and FORENSIC_REVIEW |
| .cache/ | Ignored tools, benchmark extraction and local runtime history |

Root allowlist: .gitignore, ABRIR_ANALYZER.bat, analyze.py, app.py, install.py,
README.md, requirements.txt, pytest.ini and CHANGELOG_V43.md. The seven small
Windows compatibility wrappers and compare_runs.py/exportar_ldporto.py remain
public entrypoints because older documented workflows and callers use them.
They dispatch only; canonical implementations are under scripts/.

PROJECT_EXPORT_* and WORK_PACKAGE_* were reproducible package outputs and are
removed/ignored, not relocated into an archive. Historical delivery manifests v3
and v4 are intentionally distinct immutable snapshots in docs/releases/.