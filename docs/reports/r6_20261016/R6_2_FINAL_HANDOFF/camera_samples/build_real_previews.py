"""Read existing evidence, call the real Curator renderer, and retain receipts.

This is a technical validation driver, not a second camera or rendering engine.
It never opens approval stores or writes into the Curator project.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
CURATOR = ROOT.parent / "LDPORTO_VIDEO_CURATOR"
SOURCE = ROOT / "input/youtube/9UCGZia2p1k/9UCGZia2p1k.mp4"
SOURCE_SHA256 = "5d089e1825b396dafd6b5918274f3a785eb2d8be2f622497cb7d06fdd7b3b7ea"
CASES = [
    ("01_isolated", 113.75, 116.75),
    ("02_guitar", 156.25, 158.25),
    ("03_full_band", 139.75, 144.75),
    ("04_duo", 105.75, 109.75),
    ("05_difficult_light", 174.25, 176.75),
]


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")


def run(command, receipt):
    command = [str(v) for v in command]
    result = subprocess.run(command, capture_output=True, text=True)
    write_json(receipt, {"command": command, "returncode": result.returncode,
                         "stderr": result.stderr, "stdout": result.stdout})
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:])
    return result


def probe(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                             "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def extract_sources():
    for name, start, end in CASES:
        folder = HERE / name
        out = folder / "SOURCE_EXCERPT.mp4"
        if out.exists():
            continue
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-threads", "2",
             "-ss", start, "-i", SOURCE, "-t", end-start, "-map", "0:v:0", "-map", "0:a?",
             "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-threads", "2", "-movflags", "+faststart", out],
            folder / "source_extract_command.json")
        write_json(folder / "source_excerpt.json", {
            "source": str(SOURCE), "source_sha256": SOURCE_SHA256,
            "source_start_s": start, "source_end_s": end, "interval": "end_exclusive",
            "derivative_sha256": sha256(out), "probe": probe(out), "approved": False,
            "audio": "original content reencoded AAC; no transcript or alignment claim"})
        print("source extracted", name, flush=True)


def render_case(name, start, end, camera_plan, *, revision="engine_r62"):
    sys.path.insert(0, str(CURATOR))
    from ldporto_curator.render import _base_cmd, validate_output
    from ldporto_curator.subtitles import write_subtitles
    folder = HERE / name / revision
    folder.mkdir(exist_ok=False)
    clip = {"clip_id": "R62_" + name, "source_start": start, "source_end": end,
            "duration": end-start, "camera_plan": camera_plan, "title_text": "",
            "preview_approved": False, "publish_ready": False}
    cfg = {"render": {"final_width": 1080, "final_height": 1920, "prefer_nvenc": False},
           "subtitles": {}}
    ass = write_subtitles(SimpleNamespace(captions=[], words=[]), clip, folder, cfg, preview=False)
    output = folder / "TECHNICAL_PREVIEW.mp4"
    command, w, h = _base_cmd(None, clip, SOURCE, output, ass, None, cfg, False, "libx264")
    command = ["-n" if v == "-y" else v for v in command]
    command[1:1] = ["-hide_banner", "-loglevel", "error", "-threads", "2"]
    command[-1:-1] = ["-threads", "2", "-filter_complex_threads", "2"]
    write_json(folder / "render_command_original.json", {"command": command})
    # The exact native graph may exceed Windows CreateProcess' command limit.
    # Move only its transport into a script; no graph/filter changes are made.
    if sum(len(str(v))+3 for v in command) > 24000:
        graph_index = command.index("-filter_complex")
        graph = folder / "native_curator_filter_complex.ffscript"
        graph.write_text(command[graph_index+1], encoding="utf8")
        command[graph_index:graph_index+2] = ["-filter_complex_script", str(graph)]
    write_json(folder / "camera_plan_consumed.json", camera_plan)
    write_json(folder / "clip_consumed.json", clip)
    write_json(folder / "renderer_identity.json", {
        "module": str(CURATOR / "ldporto_curator/render.py"),
        "module_sha256": sha256(CURATOR / "ldporto_curator/render.py"),
        "entry_point": "ldporto_curator.render._base_cmd (same graph used by render_clip)",
        "technical_only": True, "preview_approved": False, "publish_ready": False,
        "captions": "omitted: camera isolation, no caption readiness claim",
        "titles": "omitted: camera isolation, no overlay safety claim",
        "inference": "none", "encoder": "libx264", "cpu_threads": 2})
    run(command, folder / "render_command_result.json")
    validate_output(output, w, h)
    metadata = probe(output)
    write_json(folder / "render_integrity.json", {
        "sha256": sha256(output), "probe": metadata, "source_sha256": SOURCE_SHA256,
        "camera_plan_sha256": sha256(folder / "camera_plan_consumed.json"),
        "preview_approved": False, "publish_ready": False})
    print("rendered", name, revision, flush=True)
    return output


def render_baseline_cases():
    sys.path.insert(0, str(ROOT / "src"))
    from ldporto.camera_handoff import build_camera_handoff
    timeline_path = HERE.parent / "camera_replay_r62/timeline.json"
    timeline = json.loads(timeline_path.read_text(encoding="utf8"))
    for name, start, end in CASES:
        handoff = build_camera_handoff({"metadata": {"duration": 5840.094},
                                       "camera_director_timeline": timeline},
                                      intervals=[{"start": start, "end": end}])
        write_json(HERE / name / "analyzer_camera_handoff_r62.json", handoff)
        # All five selected intervals have unresolved focus in the actual replay.
        # Equivalent source-fit spans may be merged without changing their image.
        if any(s["recommended_composition"] != "SOURCE_FIT_BLUR" for s in handoff["segments"]):
            raise ValueError("Focused plan needs explicit geometry/keyframe adapter: " + name)
        cam = {"mode": "adaptive_timeline", "segments": [{"start": 0., "end": end-start,
               "mode": "full_frame_blur", "analyzer_composition": "SOURCE_FIT_BLUR",
               "source_interval": {"start": start, "end": end},
               "reason": "actual Analyzer replay unresolved; preserve entire source"}],
               "provenance": {"analyzer_timeline": str(timeline_path),
                              "analyzer_timeline_sha256": sha256(timeline_path),
                              "handoff_sha256": sha256(HERE / name / "analyzer_camera_handoff_r62.json"),
                              "mapping": "SOURCE_FIT_BLUR -> full_frame_blur; identical spans merged"},
               "preview_approved": False, "publish_ready": False}
        render_case(name, start, end, cam)


def render_focus_case(timeline_path):
    sys.path.insert(0, str(ROOT / "src"))
    from ldporto.curator_camera_adapter import build_curator_camera_plan
    from ldporto.camera_handoff import build_camera_handoff
    name, start, end = "06_isolated_replanned", 1601.7920000000001, 1607.7920000000001
    timeline_path = Path(timeline_path).resolve()
    timeline = json.loads(timeline_path.read_text(encoding="utf8"))
    metadata = {"width": 1920, "height": 1080, "duration": 5840.094}
    folder = HERE / name
    folder.mkdir(exist_ok=False)
    out = folder / "SOURCE_EXCERPT.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-threads", "2",
         "-ss", start, "-i", SOURCE, "-t", end-start, "-map", "0:v:0", "-map", "0:a?",
         "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-threads", "2", "-movflags", "+faststart", out],
        folder / "source_extract_command.json")
    write_json(folder / "source_excerpt.json", {"source": str(SOURCE), "source_sha256": SOURCE_SHA256,
        "source_start_s": start, "source_end_s": end, "interval": "end_exclusive",
        "derivative_sha256": sha256(out), "probe": probe(out), "approved": False})
    handoff = build_camera_handoff({"metadata": metadata, "camera_director_timeline": timeline},
                                  intervals=[{"start": start, "end": end}])
    write_json(folder / "analyzer_camera_handoff_r62.json", handoff)
    plan = build_curator_camera_plan(timeline, start, end, metadata)
    write_json(folder / "adapter_provenance.json", {"timeline": str(timeline_path),
        "timeline_file_sha256": sha256(timeline_path), "profile": "explicit Curator-compatible engine replay; max_zoom_factor 1.04",
        "adapter": str(ROOT / "src/ldporto/curator_camera_adapter.py"),
        "adapter_sha256": sha256(ROOT / "src/ldporto/curator_camera_adapter.py"),
        "render_dimensions": [1080, 1920], "source_sha256": SOURCE_SHA256,
        "instrument_preservation": "not applicable to selected primary person; other background performers not focused",
        "hands": "not certified by current Analyzer face geometry; visual review required"})
    render_case(name, start, end, plan, revision="engine_r62_compat")


if __name__ == "__main__":
    if "--render-baseline" in sys.argv:
        render_baseline_cases()
    elif "--render-focus" in sys.argv:
        render_focus_case(sys.argv[sys.argv.index("--render-focus")+1])
    else:
        extract_sources()
