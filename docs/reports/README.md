# Historical reports — original baseline preserved

The Windows candidate baseline `baseline/ldporto-20261012-prompt01` contains 1,022 tracked files under `docs/reports/` as of 2026-11-04; large historical artifacts include generated timelines, caches and provenance reports.

The current integration branch deliberately did **not** duplicate those files; all remain versioned in the **original baseline commit** `b28c78cc4c6f8b91196ebecfc7f36ac5dbea2e0d` and have not been deleted from Git. This avoids transplanting roughly 240 MB of historical data into the new development lineage and prevents false claims that historical evidence is new test output.

References:
- [Original reports tree](https://github.com/leoneldornelesporto2026/LDPORTO_VIDEO_ANALYZER/tree/b28c78cc4c6f8b91196ebecfc7f36ac5dbea2e0d/docs/reports)
- [2026-10-12 reorganization](https://github.com/leoneldornelesporto2026/LDPORTO_VIDEO_ANALYZER/blob/b28c78cc4c6f8b91196ebecfc7f36ac5dbea2e0d/docs/reports/restructuring_20261012/RELATORIO_TECNICO.md)
- [2026-10-13 SOL V3 report](https://github.com/leoneldornelesporto2026/LDPORTO_VIDEO_ANALYZER/blob/b28c78cc4c6f8b91196ebecfc7f36ac5dbea2e0d/docs/reports/sol_v3_20261013/RELATORIO_TECNICO.md)

These records are HISTORICAL, not runtime acceptance of the current branch. Check SHA256/provenance and actual consumers before restoring any individual fixture.

No newly copied media, transcripts, models, credentials, secrets, videos or private analysis archives belong in this public GitHub repository.
