# Translation Quality Guard

## Purpose

This feature protects translated chapters from being saved when the provider
returns incomplete, badly aligned, or mostly untranslated output.

The original failure case was chapter translation where one source chunk had 39
non-empty lines but the provider returned 58 translated lines. Saving that text
would risk missing or duplicated content.

## Behavior

- Chapter text is split into smaller chunks by default: `600` characters per
  chunk instead of `1000`.
- Each chunk is still checked after translation and CJK cleanup.
- If a chunk has a line-count mismatch, the app asks the provider to reformat
  the translation so each source line maps to one translated line.
- The repaired chunk is accepted only when source and translated non-empty line
  counts match, the repaired text is not bad quality, and the repair does not
  increase leftover CJK characters.
- If a chunk still has a severe line mismatch after repair, the chapter is set
  to `error` and the failed draft is kept for inspection.
- If the final whole-chapter output is severely misaligned or bad quality, the
  final failed draft is also kept.
- Successful translations clear any previous failed draft.

## Data

- `Chapter.failed_translation_draft` stores failed provider output for
  debugging.
- This draft is not treated as a valid translation and is not shown as the
  translated chapter body.
- SQLite schema patching adds the column automatically on startup for existing
  local databases.

## Related Files

- `app/config.py`
- `app/models.py`
- `app/db.py`
- `app/services/glossary_service.py`
- `tests/test_translation_quality.py`

## Limitations

- The app still depends on provider behavior. The repair step improves recovery
  but cannot guarantee every difficult chapter will pass.
- More, smaller chunks can increase translation API calls for long chapters.
- Failed drafts are stored for diagnosis, not for direct user editing yet.

## Verification

- `tests/test_translation_quality.py` covers the smaller default chunk size and
  the line-alignment repair helper.
