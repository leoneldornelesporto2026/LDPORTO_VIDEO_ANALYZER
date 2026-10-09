"""Offline social text constraints; geometry is a proposal, never render approval."""
import math
import re


def wrap_text(text, max_chars=38, *, line_fits=None):
    """Keep every token; prefer punctuation near a balanced two-line break."""
    tokens = str(text).split()
    if not tokens:
        return ''
    whole = ' '.join(tokens)
    fits = lambda line: len(line) <= max_chars and (line_fits is None or line_fits(line))
    if fits(whole):
        return whole
    options = []
    for i in range(1, len(tokens)):
        left, right = ' '.join(tokens[:i]), ' '.join(tokens[i:])
        if fits(left) and fits(right):
            punctuation = tokens[i-1].endswith(('.', ',', ';', ':', '!', '?'))
            options.append((not punctuation, abs(len(left)-len(right)), i, left, right))
    if options:
        *_, left, right = min(options)
        return left + '\n' + right
    lines, current = [], ''
    for token in tokens:
        if current and not fits(current + ' ' + token):
            lines.append(current)
            current = ''
        current = (current + ' ' + token).strip()
    return '\n'.join(lines + [current])


def checked_text(text, max_chars=38, *, font_size_px=None, max_width_px=None):
    width_fits = None
    if font_size_px is not None and max_width_px is not None:
        # Conservative glyph budget, not a font-engine measurement or approval.
        def advance(char):
            if char.isspace():
                return .4
            if char in 'ilI.,:;!|\'':
                return .4
            if char in 'MWmw@%':
                return 1.1
            if char.isascii() and char.islower():
                return .7
            return 1.
        width_fits = lambda line: sum(advance(c) for c in line)*font_size_px <= max_width_px
    wrapped = wrap_text(text, max_chars, line_fits=width_fits)
    if width_fits and any(not width_fits(line) for line in wrapped.splitlines()):
        raise ValueError('TEXT_LAYOUT_REVIEW_REQUIRED: glyph width budget exceeded')
    if len(wrapped.splitlines()) > 2 or any(len(line) > max_chars for line in wrapped.splitlines()):
        raise ValueError('TEXT_LAYOUT_REVIEW_REQUIRED: shorten/review text or split at an evidenced phrase boundary')
    return wrapped


def _color(value, default):
    return value.upper() if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) else default


def contrast_on_black(color):
    rgb = [int(color[i:i+2], 16)/255 for i in (1, 3, 5)]
    linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb]
    return (sum(v*w for v, w in zip(linear, (.2126, .7152, .0722)))+.05)/.05


def style_rules(width=1080, height=1920, *, font='Arial', scale=1., primary='#FFFFFF', highlight='#F4FF26'):
    width, height = int(width), int(height)
    if min(width, height) <= 0:
        raise ValueError('Invalid text canvas')
    try:
        size_scale = float(scale)
    except (TypeError, ValueError):
        size_scale = 1.
    if not math.isfinite(size_scale):
        size_scale = 1.
    size_scale = max(.85, min(1.25, size_scale))
    family = font if isinstance(font, str) and re.fullmatch(r'[\w -]{1,60}', font) else 'Arial'
    colors = [_color(primary, '#FFFFFF'), _color(highlight, '#F4FF26')]
    colors = [c if contrast_on_black(c) >= 4.5 else '#FFFFFF' for c in colors]
    base = min(width, height)
    return {'font_family': family, 'font_fallback': 'Arial', 'font_availability_verified': None,
            'font_size_px': round(base * .053 * size_scale),
            'title_font_size_px': round(base * .062 * size_scale), 'effective_size_scale': size_scale,
            'primary_color': colors[0], 'highlight_color': colors[1],
            'background_color': '#000000', 'background_opacity': 1.,
            'minimum_contrast_ratio': 4.5, 'contrast_scope': 'text_on_opaque_black_box',
            'max_lines': 2, 'max_chars_per_line': 24, 'title_max_chars_per_line': 21,
            'line_break_policy': 'punctuation_then_balanced_whole_words_no_truncation',
            'glyph_width_policy': 'conservative_budget_requires_actual_font_render_review',
            'proposed_safe_rect': {'x': round(width*.10), 'y': round(height*.18),
                                   'width': round(width*.72), 'height': round(height*.60)},
            'safe_area_policy': 'conservative_ui_reserve_requires_post_crop_render_inspection',
            'safe_area_verified': False, 'publication_ready': False}
