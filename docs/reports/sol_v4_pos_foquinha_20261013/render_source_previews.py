"""Three bounded source-preserving review previews; no identity or approval inference."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
REPORT = Path(__file__).resolve().parent


def main():
    import cv2
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('local_ffmpeg_missing_no_install')
    source = ROOT / 'input/youtube/7laRa_F3FbA/7laRa_F3FbA.mp4'
    rows = json.loads((REPORT/'top10_gate_matrix_before.json').read_text(encoding='utf-8'))[:3]
    results = []
    for row in rows:
        folder = REPORT/'source_previews'/row['candidate_id']
        output = folder/'source_preserve.mp4'
        if output.exists():
            raise RuntimeError('preview_exists_no_overwrite')
        folder.mkdir(parents=True, exist_ok=True)
        duration = row['end']-row['start']
        command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
            '-ss', str(row['start']), '-i', str(source), '-t', str(duration),
            '-map', '0:v:0', '-map', '0:a:0?', '-vf', 'scale=480:270',
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-threads', '2',
            '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(output)]
        started = time.perf_counter()
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        if result.returncode:
            raise RuntimeError('bounded_preview_failed:' + result.stderr.decode('utf-8', 'replace')[:1000])
        cap = cv2.VideoCapture(str(output))
        if not cap.isOpened():
            raise RuntimeError('preview_decode_failed')
        fps = cap.get(cv2.CAP_PROP_FPS)
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        samples = []
        try:
            for frame_index in sorted({0, count//2, max(0, count-2)}):
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = cap.read()
                if not ok or frame.shape[:2] != (270, 480):
                    raise RuntimeError('preview_sample_invalid')
                path = folder/f'frame_{frame_index:05}.jpg'
                if not cv2.imwrite(str(path), frame):
                    raise RuntimeError('preview_sample_write_failed')
                samples.append({'frame_index': frame_index, 'source_time_seconds': row['start']+frame_index/fps,
                    'pixel_sha256': hashlib.sha256(frame.tobytes()).hexdigest(),
                    'file': str(path.relative_to(REPORT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        finally:
            cap.release()
        results.append({'candidate_id': row['candidate_id'], 'start': row['start'], 'end': row['end'],
            'requested_duration': duration, 'preview_frames': count, 'preview_fps': fps,
            'observed_video_duration': count/fps, 'wall_seconds': time.perf_counter()-started,
            'preview_path': str(output.relative_to(REPORT)), 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'command_argv': command,
            'samples': samples, 'layout': 'SOURCE_PRESERVE', 'output_resolution': [480,270],
            'aspect_ratio': '16:9', 'crop_applied': False, 'zoom_applied': False,
            'audio': 'original_source_reencoded_aac_no_music_or_replacement',
            'preview_approved': False, 'audio_verified': False, 'publication_ready': False})
        (REPORT/'source_previews_manifest.json').write_text(json.dumps({'schema_version':'1.0',
            'source_sha256':'0231c20cfd8147d92926bda4f452777f3803c38b248064e65548f0b12a5fb98b',
            'scope':'Three unapproved bounded source-preserving curator previews; CPU FFmpeg, no GPU/Ollama/ASR.',
            'results':results, 'human_visual_identity_ground_truth':None, 'publication_ready':False},indent=2),encoding='utf-8')
        print(json.dumps({'candidate_id':row['candidate_id'],'frames':count,'wall_seconds':results[-1]['wall_seconds']}),flush=True)


if __name__ == '__main__':
    main()
