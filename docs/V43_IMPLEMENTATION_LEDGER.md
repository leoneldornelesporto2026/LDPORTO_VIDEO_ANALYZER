# V4.3 Implementation Ledger

Updated: 2026-10-06. Working branch: feature/v4.3-professional-hardening.
No commit, push, merge, rebase, destructive reset or cleanup is authorized.

Supported runtime: Python 3.11.x. Canonical tests and implementation validation
use .venv/Scripts/python.exe, now Python 3.11.17. Python 3.13 results below are
historical auxiliary evidence only, not V4.3 acceptance or runtime homologation.
The initial 3.13 environment is preserved in .cache/venv313_initial.
SciPy is required for Hungarian assignment, not to accommodate Python 3.13.

## Evidence Rules

- The open workspace is the only source of application code.
- Official benchmark: CHATGPT_REVIEW_video_31329be78ca4_20261005_232323_219590.zip.
- Extraction: .cache/v43_benchmark_official, excluded from Git.
- The earlier 225849 review is not used as the acceptance baseline.
- Measured replay, synthetic regression and unexecuted real inference are reported separately.
- An implementation or passing fixture does not prove a full-video performance gain.
- Missing identity, mouth, audio or visual evidence remains null with a reason.
- Existing ASR, diarization, overlaps, safe crops, dedup, provenance and checkpoints must survive.

## Baseline

| Check | Observation | Evidence |
| --- | --- | --- |
| Git | Requested branch; initially clean | git status --short --branch |
| Inventory | 144 nonignored files; engines in src/ldporto; tests in src/tests | Workspace inventory |
| Canonical tests | python -m pytest -q | pytest.ini |
| First test run | 226 passed, 2 failed, 0 skipped, 30.45 s | .cache/v43_baseline_tests.xml |
| Test failures | Both integration failures: ffmpeg executable unavailable | test_director_integration.py |
| Initial interpreter | Isolated Python 3.13.3; system-site-packages=false | .venv/pyvenv.cfg |
| Canonical interpreter | .venv/Scripts/python.exe, Python 3.11.17, system-site-packages=false | sys.executable, sys.version, pyvenv.cfg |
| Canonical test tooling | pytest 9.1.1, SciPy 1.17.1; Hungarian smoke passed | Python 3.11 runtime probe |
| Tracker reproduction in 3.11 | Same 5 failures and 3 passing safeguards; no expectations changed | test_v43_perception.py |
| Legacy gate in Python 3.11 | 228 passed, 0 failed, 0 skipped, 42.20 s after perception changes | .cache/v43_python311_legacy.xml |
| Local media tools | FFmpeg 7.1 and FFprobe in ignored .cache; no global installation | Executable version probe and legacy media tests |
| Official benchmark SHA256 | 9b7aba384c5364878f0870218c1bdde65e602035025389bcbb93bd73f8d76682 | Original ZIP, unchanged |
| Official source | 8245 s, 1920x1080, 30 fps | Benchmark metadata |
| Tracking | 8603 raw, 5998 micro, median 0.166 s | analysis_quality.json |
| Re-ID / participants | 2213 persistent identities, 220 participants | analysis_quality.json |
| Mapping / active speaker | 0 resolved coverage; 3 support windows | analysis_quality.json |
| Semantic | 11606.359 s, 76 calls, repair ratio 0.65217, fallback 0.19565 | analysis_quality.json |
| QA | 329 candidates, 10 answered, 6 complete | analysis_quality.json |
| Camera | 0 resolved coverage; source-preserving fallback | analysis_quality.json |
| Overall | partial / P1_DEGRADED; manifest has no causal root | run_manifest.json |

## Implementation And Verification

Statuses: PENDING, IN_PROGRESS, VERIFIED_FIXTURE, VERIFIED_REPLAY,
VERIFIED_RUNTIME, BLOCKED. No row is complete merely because code was added.

| ID | Specification | Owning implementation | Discriminating check | Status |
| --- | --- | --- | --- | --- |
| L01 | 0-6, 142, 156, 159 phase 1 | Git, pytest, benchmark inventory | Official hash, baseline JUnit, private inputs ignored | VERIFIED_RUNTIME |
| L02 | 123-131, tests 64-65 | Root BAT entrypoints, scripts/windows, path resolution | Wrapper references and Windows path with spaces | VERIFIED_FIXTURE |
| L03 | 7-11, tests 01-04 | vision.Tracker | Body/face box alternation, gap, cut, crossing | VERIFIED_FIXTURE |
| L04 | 12-15, tests 01-03 | PersonDetectionEngine, SamplingScheduler | Cascade call counts and stable/cut bursts; real-video accuracy pending | VERIFIED_FIXTURE |
| L05 | 16-19, tests 05-06 | person_reid | Median templates; simultaneous conflicts; switch proxy distinguished from ground truth | VERIFIED_FIXTURE |
| L06 | 20-25, 144 | understanding participants/entities | Editorial significance verified; entity/alias extraction pending | VERIFIED_FIXTURE |
| L07 | 26-33, tests 07-14 | vision.ActiveSpeakerEngine, active_speaker, asd_backend | Global affinity and real synthetic WAV windows verified; neural backend not benchmarked | VERIFIED_FIXTURE |
| L08 | 34-39, 93, tests 15 | planner, director, shots | Propagation, impossible planner states, A40/B1/A, source preserve | VERIFIED_FIXTURE |
| L09 | 40-43, tests 16-21 | editorial commercial classifier | Four benchmark false negatives, sponsor, editorial product discussion | VERIFIED_FIXTURE |
| L10 | 44-49, tests 22-25 | boundary optimizer, duration eligibility | Configured target/hard bounds, explicit story exception, incomplete boundaries | VERIFIED_FIXTURE |
| L11 | 50-56, tests 26-32 | semantic question/hook/answer extraction | Greeting/tag/rhetorical exclusion; interrupted multi-turn answer | VERIFIED_FIXTURE |
| L12 | 57-63, tests 33-36 | story classification, topic hierarchy, episode understanding | Discussion is not story; topic continuity and section hierarchy | VERIFIED_FIXTURE |
| L13 | 64-77, tests 41-46 | semantic, ollama_local, deterministic cache | Structured schema, empty content, prompt/schema/model invalidation | VERIFIED_FIXTURE |
| L14 | 78-81, tests 37-40 | Global Review reference contract | Quote refs, partial preservation and bounded targeted repair | VERIFIED_FIXTURE |
| L15 | 82-88, tests 47-48 | editorial ranking, second_curation | Coverage separate from score; missing-component uncertainty; propagation | VERIFIED_FIXTURE |
| L16 | 89-93, tests 49-51 | preview integration/renderer/verifier | Rendered-frame canaries; failure remains failure; bounded repairs | VERIFIED_FIXTURE |
| L17 | 94-97 | transcription review and timestamp evidence | Priority spans, retained alternatives, anomaly impact | PENDING |
| L18 | 98-102, tests 57-58 | run_status, analysis_quality | Partial roots, causal descendants, source-preserving camera status | VERIFIED_FIXTURE |
| L19 | 103-106, 112 | core, compact_artifacts, reports | Streaming summaries, serialization metrics, peak process memory | VERIFIED_FIXTURE |
| L20 | 107-111, tests 59-60 | exportar_ldporto, compact package validator | Required refs, checksums, explicit export state, no dangling files | VERIFIED_FIXTURE |
| L21 | 113-119, tests 52-54; addendum A-K, BG progress | Context events, GUI execution dashboard | Weighted progress, stage units, robust two-layer ETA, safe stop/resume | VERIFIED_FIXTURE |
| L22 | 120-122, tests 55-56 | Windows DLL bootstrap, preflight, diarization | Shared DLL handles retained; waveform decoding not falsely fatal | VERIFIED_FIXTURE |
| L23 | 132-136, tests 61-63 | Replay, cache DAG, checkpoint stores | Compatibility rejection, selective invalidation, resume integrity | VERIFIED_REPLAY |
| L24 | 137-139; addendum BH | compare_runs, performance artifacts | Missing metrics stay unmeasured; before/after provenance | VERIFIED_FIXTURE |
| L25 | Addendum L-W, AG-AK, AM-AO, AU | Automatic second-curation handoff | All candidates, full transcript, context, quality, grounded person refs | VERIFIED_REPLAY |
| L26 | Addendum X-AF, AB-AC, AL, AP-AQ, AV-AW | Contact sheets, visuals/previews | Real media included; missing JPG cannot be visual-ready | VERIFIED_FIXTURE |
| L27 | Addendum AR-AT, AZ-BF; BG package checks | Core ZIP and manifest validator | Checksums, schemas, private paths/secrets, readiness and unique names | VERIFIED_REPLAY |
| L28 | Addendum AX-AY, BD, BI-BJ | Final GUI screen, automatic stage | Package path, capability readiness, open/copy/new analysis | VERIFIED_FIXTURE |
| L29 | 140-155, 160-167; addendum BG-BI | Full regression, real replay, docs, Git output | Required regressions and explicit acceptance gaps | PENDING |
| L30 SMART_ZOOM_ARCHITECTURE | Smart Zoom 1-5, 23-26, 41-43 | Existing planner/director/motion contracts | Crop, scale and motion remain distinct; reuse visual evidence; downstream-only invalidation | VERIFIED_FIXTURE |
| L31 SMART_ZOOM_STATE_MACHINE | Smart Zoom 12-18, 22-23 | Director state and camera_motion | Deterministic easing, dwell, deadzone, rate limit, A40/B1/A and hysteresis | VERIFIED_FIXTURE |
| L32 SMART_ZOOM_SAFETY | Smart Zoom 7-11, 14, 30, 33 | camera_geometry, director, preview | Close source, unsafe crop, excessive upscale, moving source and target loss reject zoom | VERIFIED_FIXTURE |
| L33 SMART_ZOOM_EDITORIAL_RULES | Smart Zoom 4-6, 19-21, 25-26, 39-40 | Planner/director editorial evidence | Hook/payoff can motivate zoom; explanation stays stable; reaction needs evidence; explicit profiles | VERIFIED_FIXTURE |
| L34 SMART_ZOOM_PREVIEW | Smart Zoom 27-32, 35-36 | Preview renderer/verifier/closed loop | Real rendered curves; short zoom, pumping, jitter, clipping, quality and bounded repair | VERIFIED_FIXTURE |
| L35 SMART_ZOOM_GUI | Smart Zoom 37-40 | Existing native GUI dashboard/final screen | Explicit enabled/profile controls and meaningful zoom/validation summary | VERIFIED_FIXTURE |
| L36 SMART_ZOOM_HANDOFF | Smart Zoom 24-26, 34-36 | Second-curation/catalog/contact sheets/media | Modes, scale, target, reasons, safety and preview propagate; all visual refs resolve | VERIFIED_FIXTURE |
| L37 SMART_ZOOM_TESTS | Smart Zoom 44-49 | Existing camera tests plus V4.3 regressions, replay, compare_runs | All 30 specified regressions; measured zoom metrics; no motion-count success claim | VERIFIED_FIXTURE |
| L38 REPO_ROOT_HYGIENE | Cleanup 1-4, 31, 52 | Public entrypoints and explicit root allowlist | Root communicates run/install/code; legitimate exceptions documented | VERIFIED_FIXTURE |
| L39 WINDOWS_SCRIPT_ORGANIZATION | Cleanup 5-7, 40-42 | scripts/windows and necessary compatibility wrappers | Canonical scripts resolve project root with spaces; wrappers have contract comments | VERIFIED_FIXTURE |
| L40 REQUIREMENTS_ORGANIZATION | Cleanup 9-11, 34 | requirements/ and install/BAT/docs consumers | Eight 100% git renames; all groups resolve; installer/preflight gate passed | VERIFIED_RUNTIME |
| L41 DOCS_CONSOLIDATION | Cleanup 12-14, 33, 35, 43-45 | README and specialized docs | Useful setup retained; current links resolve; history is not runtime truth | VERIFIED_FIXTURE |
| L42 GENERATED_ARTIFACT_CLEANUP | Cleanup 16, 18-19, 29-30, 32, 36-38 | Export/work-package outputs and .gitignore | Proven generated files excluded; benchmark/models/secrets never tracked | VERIFIED_FIXTURE |
| L43 MANIFEST_AUDIT | Cleanup 15-20 | Historical manifests and exporter output ownership | Classify consumers/source-of-truth; no competing current release manifests | VERIFIED_FIXTURE |
| L44 PATH_RESOLUTION | Cleanup 8, 24, 49, 51 | Shared pathlib paths and thin entrypoints | CWD independence, schema/config discovery, paths with spaces | VERIFIED_FIXTURE |
| L45 FFMPEG_DISCOVERY_CONSOLIDATION | Cleanup 27-28, 49 | Shared FFmpeg discovery and Windows DLL bootstrap | CLI and DLL availability distinct; selected Python 3.11 executable reported | VERIFIED_FIXTURE |
| L46 DEAD_CODE_AUDIT | Cleanup 25-26 | Runtime/CLI/dynamic-import consumers | No deletion based solely on text-search absence; no giant utility refactor | PENDING |
| L47 EXPORT_STAGING_CLEANUP | Cleanup 21-23, 46-48 | Exporter, compare_runs, ignored staging/output | No generated manifest/tree/readme in source root; final packages use pacotes_para_enviar | VERIFIED_FIXTURE |
| L48 ROOT_ALLOWLIST_TEST | Cleanup 31-32, 50, 52 | Root/source hygiene regression | Generated artifacts cannot reappear as tracked source; canonical full pytest | VERIFIED_FIXTURE |
| L49 WINDOWS_PATH_COMPATIBILITY | Cleanup 7-8, 28, 49-51, 57-58 | BAT/bootstrap/discovery tests | Preserve public commands, selected 3.11 runtime and paths containing spaces | VERIFIED_FIXTURE |

Smart Zoom extends the current V4.3 work; it does not replace completed tracking,
Re-ID or resume changes. Its implementation belongs to the existing camera,
preview, observability and handoff phases. Natural is an explicit conservative
default, not an inferred video-type profile. Unsupported evidence keeps
SOURCE_PRESERVE, and real full-video acceptance remains separate from fixtures.

## Cleanup Checkpoint

Before the additional cleanup, git status --short recorded modified root BAT
wrappers, config/config.yaml, requirements.txt, src/ldporto/config.py,
person_reid.py, pipeline.py, understanding.py, vision.py and vision_checkpoint.py.
New ledger, scripts/windows implementations and V4.3 tests are also preserved.
Tracker, Re-ID and resume: 54 scoped tests passed in Python 3.11; participant
filtering: 44 scoped tests passed. These counts are overlapping suites, not additive.
Further tracked-file relocations use git mv after a reference audit. A move may
stage its rename but does not authorize a commit. Runtime patches are not reset.

## Repository Hygiene Inventory

| Category | Files | References/public interface | Decision |
| --- | --- | --- | --- |
| Runtime entrypoints | ABRIR_ANALYZER.bat, analyze.py, app.py | GUI/CLI and user documentation | Keep root paths |
| Developer interfaces | compare_runs.py, exportar_ldporto.py, install.py, pytest.ini, requirements*.txt | Tests, install, GUI, exporter | Keep root paths |
| Windows operations | CONFIGURAR_OLLAMA_MAXIMO_WINDOWS.bat, CORRIGIR_GPU_WINDOWS.bat, DIAGNOSTICO_GPU_WINDOWS.bat, DIAGNOSTICO_WINDOWS.bat, INSTALAR_AVANCADO_WINDOWS.bat, INSTALAR_WINDOWS.bat, TESTAR_WINDOWS.bat | GUI, nested BAT calls, install docs, safety tests | Relocate implementations with root compatibility wrappers |
| Setup/troubleshooting docs | LEIA_PRIMEIRO.md, GPU_FIX_NOTES.md, PATCH_OLLAMA_MAXIMO.md | Public links and BAT messages | Preserve public paths until links are migrated safely |
| Historical delivery manifests | DELIVERY_MANIFEST*.json, PROJECT_EXPORT_MANIFEST.json, WORK_PACKAGE_MANIFEST.json | Historical checksums; exporter denylist/tests | Preserve immutable historical provenance; do not regenerate as current inventory |
| Historical reports/trees | PROJECT_EXPORT_README.txt, PROJECT_EXPORT_TREE.txt, WORK_PACKAGE_*.txt, WORKER_FINAL_REPORT.md | Previous deliveries and audit evidence | Preserve historical evidence; not current runtime inputs |

## Initial Falsifiable Findings

- Tracker associates a changing body/face bbox using only IoU >=0.25. A same-face
  alternating-body fixture can disprove the claim that this is safe continuity.
- A missing frame embedding overwrites the last track embedding. A gap recovery
  fixture with contradictory later embedding can expose an identity collision.
- person_reid._embedding returns the first template, not a robust aggregate.
- build_second_curation_package reads topic/quality directly from candidates,
  although topic refs and global measured quality exist upstream.
- The benchmark manifest treats partial perception/semantic stages as unaffected.
- GUI currently parses text logs and force-kills its worker; there is no automatic core ZIP stage.

## Post-Credit Audit Checkpoint

Independent audit of commit 39d2193 found and corrected two missing canonical diagnostic BAT implementations referenced by root compatibility wrappers. The compact second-curation package now also includes `SECOND_CURATOR_BRIEF.json`, and `compare_runs` has a regression proving V4.3 readiness/Smart Zoom/handoff metrics remain visible.

Auxiliary Linux/Python 3.13 validation after these corrections: 351 tests passed under Xvfb with a temporary Git metadata directory. This is cross-platform regression evidence only; Windows/Python 3.11 remains the canonical runtime and still requires the final full post-patch suite on the user's machine.

L17 remains pending because targeted ASR re-review/prioritization was not completed in the WIP. L29 remains in progress because a new full-video V4.3 run and final Windows 3.11 post-patch acceptance have not yet been executed. L46 remains pending as a conservative dead-code audit item.

## Acceptance Boundaries

Real re-detection, ASR, Pyannote, Qwen throughput/VRAM and identity-switch accuracy
require source media, compatible installed models and, for accuracy, annotated truth.
The review ZIP is not assumed to contain omitted raw collections or actual images.
These limits do not block deterministic downstream replay or representative media tests.
No arbitrary human count, inflated coverage, forced name, face-only speaker identity,
relaxed quote validation or hidden failed preview is acceptable.
