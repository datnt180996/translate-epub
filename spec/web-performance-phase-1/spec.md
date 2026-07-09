# Web Performance Phase 1

## Purpose

This phase reduces the amount of database data loaded by common web pages.
It keeps the current user experience unchanged while making large libraries
and novels with many chapters cheaper to render.

## Behavior

- The homepage loads all novels as before, but chapter counts and status
  summaries are gathered in one grouped query instead of one query per novel.
- The novel detail page continues to use lightweight chapter rows that avoid
  loading `raw_text` and `translated_text`.
- The chapter reader loads full text only for the currently opened chapter.
  The previous/next chapter links are found with small index-based queries.
- The chapter list dialog on the reader uses lightweight chapter metadata.
  It does not recalculate translation quality for every chapter body.
- The batch translation eligible count is computed directly in SQL instead of
  loading every chapter for a novel.

## Related Files

- `app/main.py`
  - `_query_homepage_chapter_meta`
  - `_query_chapter_neighbors`
  - `index`
  - `chapter_view`
- `app/services/batch_translation_runner.py`
  - `eligible_count_for_novel`
- `tests/test_novel_detail_performance.py`
- `tests/test_batch_runner.py`

## Known Limits

- The chapter list dialog still renders every chapter item when opening a
  chapter. For very large novels, a later phase can paginate or lazy-load that
  list.
- CSS and JavaScript are still embedded in templates. Moving them to static
  files is planned for a separate phase.
- Translation quality is still calculated live for the currently opened
  chapter. Persisting quality state can be considered later if needed.
