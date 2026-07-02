# Graph Report - .  (2026-07-02)

## Corpus Check
- 37 files · ~107,417 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 395 nodes · 1055 edges · 13 communities
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 35 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_FastAPI Routes & main.py|FastAPI Routes & main.py]]
- [[_COMMUNITY_Chapter Text Cleaner|Chapter Text Cleaner]]
- [[_COMMUNITY_Design Concepts & Rationale|Design Concepts & Rationale]]
- [[_COMMUNITY_Template Status Helpers & Chapters|Template Status Helpers & Chapters]]
- [[_COMMUNITY_Translation Provider Interface & Providers|Translation Provider Interface & Providers]]
- [[_COMMUNITY_SQLModel Tables & Glossary Service|SQLModel Tables & Glossary Service]]
- [[_COMMUNITY_Config, DB Engine & Fetch Runner|Config, DB Engine & Fetch Runner]]
- [[_COMMUNITY_Novel Detail Performance Tests|Novel Detail Performance Tests]]
- [[_COMMUNITY_Chapter Ordering & EPUB Importer|Chapter Ordering & EPUB Importer]]
- [[_COMMUNITY_Python Dependencies|Python Dependencies]]
- [[_COMMUNITY_Provider Settings Service|Provider Settings Service]]

## God Nodes (most connected - your core abstractions)
1. `Novel` - 45 edges
2. `Chapter` - 34 edges
3. `translate_chapter()` - 17 edges
4. `get_settings()` - 16 edges
5. `TranslationProvider` - 15 edges
6. `default_provider()` - 15 edges
7. `OpenAICompatProvider` - 15 edges
8. `_chapter_detail_status()` - 14 edges
9. `get_provider()` - 14 edges
10. `novel_detail()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `test_poll_active_only_for_running_work()` --calls--> `_novel_poll_active()`  [EXTRACTED]
  tests/test_novel_detail_performance.py → app/main.py
- `test_stats_partial_has_no_self_polling()` --calls--> `Novel`  [EXTRACTED]
  tests/test_novel_detail_performance.py → app/models.py
- `test_display_status_from_row_matches_chapter_helper()` --calls--> `_chapter_detail_status()`  [EXTRACTED]
  tests/test_novel_detail_performance.py → app/main.py
- `test_novel_stats_aggregate_matches_legacy_counts()` --calls--> `_novel_stats_aggregate()`  [EXTRACTED]
  tests/test_novel_detail_performance.py → app/main.py
- `test_novel_stats_from_rows_matches_legacy_counts()` --calls--> `_novel_stats_from_chapters()`  [EXTRACTED]
  tests/test_novel_detail_performance.py → app/main.py

## Import Cycles
- None detected.

## Communities (13 total, 0 thin omitted)

### Community 0 - "FastAPI Routes & main.py"
Cohesion: 0.06
Nodes (77): get_session(), Session, add_glossary_term(), api_settings_clear(), api_settings_save(), api_settings_set_default(), api_settings_test(), api_settings_view() (+69 more)

### Community 1 - "Chapter Text Cleaner"
Cohesion: 0.09
Nodes (50): chunk_text(), clean_html_to_text(), count_non_empty_lines(), join_lines(), join_paragraphs(), line_count_mismatch(), Compare non-empty line counts between source and translation.      Returns ``(, Split text into lines preserving empty lines (which represent paragraph     bre (+42 more)

### Community 2 - "Design Concepts & Rationale"
Cohesion: 0.06
Nodes (48): 5-summary context window for next chapter, Background translation daemon thread, Chunk-parallel translation via ThreadPoolExecutor, DB ProviderSetting overrides .env fallback, Automatic glossary extraction post-translation, HTMX 5s polling for chapters and stats, In-memory thread registry (tech debt: no resume after restart), Three-view reader (raw/vi/both) (+40 more)

### Community 3 - "Template Status Helpers & Chapters"
Cohesion: 0.11
Nodes (40): _batch_display_status(), _chapter_detail_status(), _novel_stats_from_chapters(), Derive a UI display status from chapter fields.      Priority order ensures ac, Overlay in-memory batch progress on the persisted chapter status., _row_partial(), _stats_partial(), Chapter (+32 more)

### Community 4 - "Translation Provider Interface & Providers"
Cohesion: 0.12
Nodes (17): TranslationContext, TranslationProvider, _build_provider(), get_provider(), get_provider_no_session(), Return a provider using saved DB config (fallback to .env).      Uses the DB-b, Backward-compatible getter that reads .env only (no DB).      Some legacy call, DeepSeekProvider (+9 more)

### Community 5 - "SQLModel Tables & Glossary Service"
Cohesion: 0.15
Nodes (30): AppSetting, ChapterSummary, GlossaryTerm, ProviderSetting, StyleGuide, TranslationJob, add_term(), build_translation_context() (+22 more)

### Community 6 - "Config, DB Engine & Fetch Runner"
Cohesion: 0.13
Nodes (25): get_settings(), Settings, _apply_schema_patches(), init_db(), _claim_chapters(), _fetch_one_with_text(), _mark_error(), _mark_fetched() (+17 more)

### Community 7 - "Novel Detail Performance Tests"
Cohesion: 0.24
Nodes (18): _display_status_from_row(), _novel_stats_from_rows(), Same priority order as `_chapter_detail_status` but works on lightweight row dic, Compute novel stats from lightweight row dicts (no text loaded)., _chapter(), Regression tests for novel detail performance optimizations (phase 1).  Covers:, Aggregate stats computed via SQL must match the row-based stats helper., _render_novel_html() (+10 more)

### Community 8 - "Chapter Ordering & EPUB Importer"
Cohesion: 0.24
Nodes (15): chapter_sort_key(), ChapterSortKey, _cn_to_int(), sort_chapters(), _chapter_title_from_item(), _get_item_text(), import_epub_bytes(), import_epub_file() (+7 more)

### Community 9 - "Python Dependencies"
Cohesion: 0.12
Nodes (15): beautifulsoup4>=4.12.3, curl_cffi>=0.7.0, ebooklib>=0.18, fastapi>=0.110,<0.120, httpx>=0.27, itsdangerous>=2.2, jinja2>=3.1.3,<3.1.4, lxml>=5.1.0 (+7 more)

### Community 10 - "Provider Settings Service"
Cohesion: 0.42
Nodes (9): clear_provider_setting(), _defaults_for(), get_default_provider_name(), get_provider_config(), list_provider_settings(), mask_key(), Session, save_provider_setting() (+1 more)

## Knowledge Gaps
- **32 isolated node(s):** `Partial: novel stats card (total/raw/translated/error) with HTMX OOB swap`, `GET / (homepage)`, `POST /novels/{id}/translate-selected`, `Novel (SQLModel table)`, `Chapter (SQLModel table)` (+27 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Novel` connect `Template Status Helpers & Chapters` to `FastAPI Routes & main.py`, `SQLModel Tables & Glossary Service`, `Config, DB Engine & Fetch Runner`, `Novel Detail Performance Tests`, `Chapter Ordering & EPUB Importer`?**
  _High betweenness centrality (0.101) - this node is a cross-community bridge._
- **Why does `Chapter` connect `Template Status Helpers & Chapters` to `FastAPI Routes & main.py`, `SQLModel Tables & Glossary Service`, `Config, DB Engine & Fetch Runner`, `Novel Detail Performance Tests`, `Chapter Ordering & EPUB Importer`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Why does `get_settings()` connect `Config, DB Engine & Fetch Runner` to `FastAPI Routes & main.py`, `Provider Settings Service`, `Translation Provider Interface & Providers`, `SQLModel Tables & Glossary Service`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **What connects `Derive a UI display status from chapter fields.      Priority order ensures ac`, `Same priority order as `_chapter_detail_status` but works on lightweight row dic`, `Overlay in-memory batch progress on the persisted chapter status.` to the rest of the system?**
  _77 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `FastAPI Routes & main.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06234177215189873 - nodes in this community are weakly interconnected._
- **Should `Chapter Text Cleaner` be split into smaller, more focused modules?**
  _Cohesion score 0.09084556254367575 - nodes in this community are weakly interconnected._
- **Should `Design Concepts & Rationale` be split into smaller, more focused modules?**
  _Cohesion score 0.05714285714285714 - nodes in this community are weakly interconnected._