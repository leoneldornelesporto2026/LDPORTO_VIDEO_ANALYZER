"""Explicit OCR edits preserve surrounding YAML and the scalar quote style."""
import pytest

from ldporto.config import load_config, save_ocr_options


@pytest.mark.parametrize('path_literal', [
    'C:/Program Files/Tesseract-OCR/tesseract.exe',
    "'C:/Program Files/Tesseract-OCR/tesseract.exe'",
    '"C:/Program Files/Tesseract-OCR/tesseract.exe"'])
def test_restore_ocr_path_keeps_scalar_style_comments_and_crlf_bytes(tmp_path, path_literal):
    path = tmp_path/'config.yaml'
    original = ('# synthetic local configuration\r\nocr:\r\n  enabled: true\r\n'
                '  languages: por+eng\r\n  tesseract_cmd: '+path_literal+' # preserved comment\r\n'
                'audio_events:\r\n  enabled: false\r\n').encode('utf-8')
    path.write_bytes(original)
    before = load_config(path)
    save_ocr_options(path, {'tesseract_cmd': 'C:/Program Files/OCR/tesseract.exe'})
    assert path.read_bytes().split(b' # preserved comment')[1] == original.split(b' # preserved comment')[1]
    save_ocr_options(path, {'tesseract_cmd': before['ocr']['tesseract_cmd']})
    assert path.read_bytes() == original


def test_yaml_ambiguous_string_remains_a_string_when_plain_scalar_was_used(tmp_path):
    path = tmp_path/'config.yaml'
    path.write_text('ocr:\n  enabled: true\n  languages: por+eng\n  tesseract_cmd: synthetic\n', encoding='utf-8')
    after = save_ocr_options(path, {'tesseract_cmd': 'true'})
    assert after['ocr']['tesseract_cmd'] == 'true'
