# Batch Translation Auto Refresh

## Purpose

When a user selects multiple chapters and starts batch translation, the novel
detail table must update chapter statuses automatically. Users should not need
to press F5 to see `Queue`, `Translating`, `Translated`, or `Error` changes.

## Behavior

- After batch submit, selected rows are updated immediately in the browser:
  - the first selected row becomes `translating`,
  - the remaining selected rows become `queue`.
- Those optimistic rows are also given HTMX self-polling attributes so each row
  requests `/novels/{novel_id}/chapters/{chapter_id}/row` every 2 seconds.
- When a row response swaps in, the page recalculates:
  - whether a batch still appears active,
  - which chapters are eligible for selection,
  - selected checkboxes and hidden form inputs,
  - visible rows under the current search filter.
- The full chapter table refresh still exists as a backup and for stats
  updates.
- The `novel-detail.js` asset URL uses a new cache-busting version so browsers
  load the fixed script.

## Related Files

- `app/static/js/novel-detail.js`
- `app/templates/novel.html`
- `tests/test_batch_translate_ui.py`

## Limitations

- Row polling depends on HTMX being loaded on the page.
- If the server process restarts, in-memory batch state is lost; existing
  startup cleanup still handles stale translating rows separately.

## Verification

- `tests/test_batch_translate_ui.py` checks that optimistic batch rows attach
  row polling and that the page references the new script version.
