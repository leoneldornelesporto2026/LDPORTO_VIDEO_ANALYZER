"""Compare decoder scene boundaries against OpenCV, with one-source-frame tolerance."""
from pathlib import Path
import json

REPORT=Path(__file__).resolve().parent

def main():
    baseline=json.loads((REPORT/'after_opencv_scenes/result.json').read_text(encoding='utf-8'))
    fps=baseline['metadata']['fps']
    tolerance=1/fps
    rounding_epsilon=0.5e-6  # OpenCV SceneDetect boundaries are rounded to six decimals.
    original=[row['start'] for row in baseline['scene_data']['scenes'][1:]]
    comparisons={}
    for mode in ['after_pyav_slice','after_pyav_auto']:
        current=json.loads((REPORT/mode/'result.json').read_text(encoding='utf-8'))
        fresh=[row['start'] for row in current['scene_data']['scenes'][1:]]
        remaining=list(original)
        matched=[]; added=[]
        for value in fresh:
            nearest=min(remaining,key=lambda old:abs(old-value)) if remaining else None
            if nearest is not None and abs(nearest-value)<=tolerance+rounding_epsilon:
                matched.append({'opencv':nearest,'pyav':value,'delta_seconds':value-nearest,
                                'source_frame_delta':round(value*fps)-round(nearest*fps)})
                remaining.remove(nearest)
            else:added.append(value)
        comparisons[mode]={'matches':matched,'new_relative_to_opencv':added,'lost_relative_to_opencv':remaining,
            'boundaries_equivalent_within_tolerance':not added and not remaining,
            'opencv_seconds':baseline['scene_seconds'],'pyav_seconds':current['scene_seconds'],
            'speedup_x':baseline['scene_seconds']/current['scene_seconds'],
            'opencv_peak_ram_bytes':baseline['resources']['peak_process_memory_bytes'],
            'pyav_peak_ram_bytes':current['resources']['peak_process_memory_bytes'],
            'ram_scope':'Fresh scenes-only processes, no visual model or GPU inference.',
            'opencv_decoded_frames':baseline['scene_data']['performance']['frames_returned'],
            'pyav_decoded_frames':current['scene_data']['performance']['frames_returned']}
    result={'fps':fps,'tolerance_seconds':tolerance,'timestamp_rounding_epsilon_seconds':rounding_epsilon,'comparisons':comparisons,
            'human_cut_ground_truth':None,'default_backend':'opencv',
            'scope':'Same ContentDetector, thresholds, frame_skip=0, native resolution/fps and downscale. Decoder is the experimental variable. Reference equivalence does not establish human cut accuracy.'}
    (REPORT/'scene_decoder_comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':main()
