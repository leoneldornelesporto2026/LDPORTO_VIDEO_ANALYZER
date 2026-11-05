"""Pure helper for bounded Tk Canvas scrolling."""


def scroll_fraction(target_y, total_height, visible_height):
    total = max(float(total_height), 1.0)
    visible = max(float(visible_height), 0.0)
    if visible >= total:
        return 0.0
    position = min(max(0.0, float(target_y)), total - visible)
    return position / total
