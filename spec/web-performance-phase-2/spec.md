# Web Performance Phase 2

## Purpose

This phase moves large inline CSS and JavaScript blocks out of rendered HTML
templates and into static files. The browser can cache these files, so repeated
page loads send and parse less duplicated HTML.

## Behavior

- `base.html` now links shared CSS through `/static/css/app.css`.
- `base.html` now loads shared app JavaScript through `/static/js/app.js`.
- The novel detail page loads its page-specific JavaScript through
  `/static/js/novel-detail.js`.
- The chapter reader page loads its page-specific JavaScript through
  `/static/js/chapter-reader.js`.
- Dynamic values that page scripts need are passed through `data-*` attributes:
  - `novel.html` passes `data-novel-id` on `#nd-batch-form`.
  - `chapter.html` passes `data-novel-id`, `data-chapter-id`, and
    `data-auto-reload` on `.cr-reader`.
- User-facing behavior should stay the same: confirm dialogs, toast messages,
  batch selection, chapter polling, chapter dialog search, keyboard navigation,
  and auto reload still work.

## Related Files

- `app/templates/base.html`
- `app/templates/novel.html`
- `app/templates/chapter.html`
- `app/static/css/app.css`
- `app/static/js/app.js`
- `app/static/js/novel-detail.js`
- `app/static/js/chapter-reader.js`
- `tests/test_confirm_dialog.py`
- `tests/test_chapter_ui.py`
- `tests/test_batch_translate_ui.py`

## Known Limits

- External dependencies such as Google Fonts and HTMX are still loaded from
  their public URLs.
- Static file cache busting is not versioned yet. If CSS or JS changes while a
  browser has an old cache, the user may need a hard refresh.
- This phase does not redesign the interface or split CSS by page. It only
  moves the existing shared stylesheet into one cacheable file.
