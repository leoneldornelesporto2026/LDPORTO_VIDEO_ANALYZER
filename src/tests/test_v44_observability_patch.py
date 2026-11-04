from ldporto.scenes import summarize_scenes
from ldporto.progress import STAGE_LABELS


def test_scene_summary_distinguishes_scenes_from_boundaries():
    scenes = [
        {'start': 0.0, 'end': 10.0},
        {'start': 10.0, 'end': 20.0},
        {'start': 20.0, 'end': 30.0},
    ]
    summary = summarize_scenes(scenes, 30.0, window_seconds=10.0)
    assert summary['scene_count'] == 3
    assert summary['visual_boundary_count'] == 2
    assert STAGE_LABELS['06_scenes'] == 'Cenas visuais'


def test_scene_summary_flags_dense_tail_without_calling_it_identity_growth():
    scenes = []
    # Three calm windows, then a highly cut final window.
    for start in (0, 100, 200, 600, 700, 800, 1200, 1300, 1400):
        scenes.append({'start': float(start), 'end': float(start + 20)})
    for index in range(40):
        start = 1800 + index * 10
        scenes.append({'start': float(start), 'end': float(start + 5)})
    summary = summarize_scenes(scenes, 2400.0, window_seconds=600.0)
    assert summary['last_window_scene_count'] == 40
    assert summary['dense_tail_region'] is True
    assert summary['peak_scene_window']['scene_count'] == 40
