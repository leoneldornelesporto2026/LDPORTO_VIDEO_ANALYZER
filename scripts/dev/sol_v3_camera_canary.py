"""Render annotated synthetic camera canaries on CPU; no human/model validation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(PROJECT/'src'), str(PROJECT/'src/tests')]


def run_canaries(output):
    import cv2
    import numpy as np
    from director_fixtures import fixture, turn
    from ldporto.camera_director import build_camera_director
    from ldporto.core import file_hash, write_json
    from ldporto.preview_renderer import render_preview
    output = Path(output)
    if output.exists():
        raise ValueError('Existing canary artifacts are preserved; choose a new output directory.')
    output.mkdir(parents=True)
    reports = []
    previous_threads = cv2.getNumThreads()
    cv2.setNumThreads(1)
    try:
        with tempfile.TemporaryDirectory(prefix='ldporto_annotated_camera_') as temporary:
            for name, width, height, grounded in [('positive_720p', 1280, 720, True), ('negative_240p', 320, 240, False)]:
                duration = 30 if grounded else 12
                metadata, vision, shots = fixture(duration)
                metadata.update(width=width, height=height, fps=15)
                voice = dict(turn(0, duration), active_person='PERSON_A' if grounded else None,
                             active_speaker_state='CONFIRMED' if grounded else 'UNCERTAIN')
                hook = {'moment_id': 'ANNOTATED_HOOK', 'start': 0, 'end': 10,
                        'categories': ['hook'], 'hook_score': .9,
                        'evidence_segment_ids': ['SYNTHETIC_SEGMENT']}
                director = build_camera_director(metadata, vision, shots, [voice], [],
                    {'output_width': 540, 'output_height': 960}, main_moments=[hook] if grounded else [])['data']
                source = Path(temporary)/(name+'.mp4')
                writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'mp4v'), 15, (width, height))
                if not writer.isOpened():
                    raise RuntimeError('Synthetic video writer unavailable.')
                face = vision['observations'][0]['face_bbox']
                image = np.full((height, width, 3), (50, 70, 90), np.uint8)
                x, y = round(face['x']*width), round(face['y']*height)
                fw, fh = round(face['width']*width), round(face['height']*height)
                cv2.rectangle(image, (x, y), (x+fw, y+fh), (20, 170, 230), -1)
                cv2.rectangle(image, (x-fw//2, y+fh), (x+fw+fw//2, min(height-1, y+fh*3)), (170, 100, 40), -1)
                cv2.putText(image, 'SYNTHETIC ANNOTATION', (8, height-12), cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1)
                try:
                    for _ in range(duration*15):
                        writer.write(image)
                finally:
                    writer.release()
                preview = output/(name+'.mp4')
                rendered = render_preview(source, director['timeline'], metadata, preview,
                    interval={'start': 4., 'end': 6.}, output_width=540, output_height=960)
                if rendered['status'] != 'ok':
                    raise RuntimeError('Canary rendering failed: '+rendered['status'])
                capture = cv2.VideoCapture(str(preview))
                frames = []
                try:
                    while True:
                        available, frame = capture.read()
                        if not available:
                            break
                        frames.append(frame)
                finally:
                    capture.release()
                observations = []
                for label, frame in [('first', frames[0]), ('last', frames[-1])]:
                    pixels = (frame[:, :, 2] > 180) & (frame[:, :, 1] > 125) & (frame[:, :, 1] < 220) & (frame[:, :, 0] < 80)
                    ys, xs = np.where(pixels)
                    margin = min(xs.min()/540, (539-xs.max())/540, ys.min()/960, (959-ys.max())/960) if len(xs) else None
                    still = output/(name+'_'+label+'.png')
                    if not cv2.imwrite(str(still), frame):
                        raise RuntimeError('Could not write observed canary frame.')
                    observations.append({'frame': label, 'png': still.name, 'png_sha256': file_hash(still),
                        'decoded_pixels_sha256': hashlib.sha256(frame.tobytes()).hexdigest(),
                        'synthetic_marker_pixels': int(len(xs)), 'synthetic_marker_minimum_margin_fraction': margin,
                        'laplacian_variance': float(cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()),
                        'not_a_face_detector_or_identity_measurement': True})
                reports.append({'case': name, 'validation_class': 'integration_local_synthetic_render',
                    'source_dimensions': [width, height], 'preview': preview.name,
                    'preview_sha256': file_hash(preview), 'rendered_frames': len(frames),
                    'director_focused': any(row['focus_person'] for row in director['timeline']),
                    'accepted_zoom_events': director['metrics']['zoom_accepted_event_count'],
                    'rendered_motion': rendered['data']['rendered_motion'],
                    'camera_gates': director['metrics']['zoom_gate_diagnostics'], 'observed_frames': observations,
                    'input_evidence': 'injected_synthetic_geometry_speaker_and_editorial_annotations',
                    'human_review': False, 'publication_ready': False})
    finally:
        cv2.setNumThreads(previous_threads)
    report = {'schema_version': '1.0', 'no_real_person_accuracy_claim': True, 'cases': reports}
    write_json(output/'canary_report.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    result = run_canaries(args.output_dir)
    print(json.dumps({'cases': [{key: row[key] for key in ('case', 'director_focused', 'accepted_zoom_events', 'rendered_frames')}
                               for row in result['cases']], 'report': str(args.output_dir/'canary_report.json')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
