# Vietnamese Text Encoding Fix

## Purpose

This fix restores Vietnamese UI text that had been saved as mojibake, such as
`Danh sÃ¡ch chÆ°Æ¡ng`, back to readable Vietnamese text like
`Danh sách chương`.

## Behavior

- Static labels in the main layout, novel detail page, chapter reader page, and
  shared JavaScript helpers display Vietnamese correctly.
- Static CSS and JavaScript URLs include a cache-busting version suffix so a
  browser with older assets does not overwrite fixed Vietnamese labels.
- Existing dynamic novel data remains unchanged.
- Browser verification on `/novels/1` confirms the main labels display
  correctly and no visible page lines contain common mojibake markers.

## Related Files

- `app/templates/base.html`
- `app/templates/novel.html`
- `app/templates/chapter.html`
- `app/static/js/app.js`
- `app/static/js/chapter-reader.js`
- `app/static/js/novel-detail.js`
- `tests/test_batch_translate_ui.py`
- `tests/test_chapter_ui.py`
- `tests/test_confirm_dialog.py`
- `tests/test_translation_quality.py`

## Verification

- Direct test-file execution passes for all `tests/test_*.py` files.
- The novel detail page response includes the corrected batch toolbar labels:
  `0 đã chọn`, `Có ... chương đủ điều kiện`, and `Dịch chương đã chọn`.
- `python -m pytest` could not be used because `pytest` is not installed in the
  project environment.
