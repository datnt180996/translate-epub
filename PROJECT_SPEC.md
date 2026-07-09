# Ebook Translator — Project Spec

> Cập nhật theo code trong working tree ngày 2026-07-01. File này mô tả hành vi đang được triển khai, không phải roadmap.

## 1. Mục tiêu sản phẩm

Ebook Translator (UI dùng tên **Dịch Hiệp**) là web app local để import truyện tiếng Trung, lưu nội dung vào SQLite và dịch sang tiếng Việt bằng LLM. Ứng dụng tập trung vào truyện tiên hiệp, huyền huyễn và tu chân, dành cho người dùng không cần biết lập trình.

Nguyên tắc sản phẩm:

- Thao tác chính phải thực hiện được trên UI.
- Không xóa dữ liệu truyện, chương, glossary hoặc bản dịch nếu người dùng không chủ động yêu cầu.
- Tác vụ dịch chạy nền và có trạng thái tiến độ.
- Lỗi/cảnh báo cần hiển thị bằng tiếng Việt.
- Đây là local tool: hiện không có authentication, phân quyền hoặc CSRF protection.

## 2. Tính năng hiện có

- Import truyện từ URL; hỗ trợ riêng `69shuba.com` và có parser generic cho link `.html`.
- Import file `.epub`, đọc metadata và các document trong spine.
- Lấy title, author, description và cover khi nguồn cung cấp được.
- Tự dịch title/author lúc import nếu đã cấu hình và chọn provider mặc định; lỗi dịch metadata chỉ được log, không làm hỏng import.
- Sắp xếp chương theo số Ả Rập/số Hán, chương mở đầu và nhóm ngoại truyện/hậu ký/phụ lục.
- Fetch nội dung gốc từng chương; có route fetch toàn bộ nhưng chưa có nút tương ứng trên UI hiện tại.
- Dịch từng chương trong background daemon thread, chia chunk và dịch song song.
- Lưu raw text, translated text, title dịch, provider, lỗi và cảnh báo chất lượng trong SQLite.
- Theo dõi tiến độ chunk bằng `TranslationJob`.
- Quản lý style guide và glossary theo từng truyện; glossary hiện hỗ trợ thêm và xóa, chưa hỗ trợ sửa.
- Tự trích xuất glossary và tóm tắt chương sau khi dịch nếu cấu hình cho phép.
- Dùng tối đa 5 summary gần nhất (theo ID tạo) làm context cho chương tiếp theo.
- Cấu hình Minimax, OpenRouter và DeepSeek trên web; có lưu/test/xóa và chọn provider mặc định.
- Trang chi tiết truyện cập nhật bảng chương và thống kê mỗi 5 giây bằng HTMX.
- Reader hỗ trợ `Bản gốc`, `Bản dịch`, `Song song`, điều hướng trước/sau và modal danh sách chương có tìm kiếm.

Chưa có:

- Export TXT/DOCX/EPUB.
- Dịch hàng loạt nhiều chương.
- Resume job sau khi restart app.
- Editor sửa bản dịch trực tiếp.
- Authentication hoặc triển khai multi-user.

## 3. Tech stack và runtime

Backend:

- Python, FastAPI, SQLModel, SQLite, Jinja2.
- `httpx`, `curl_cffi`, BeautifulSoup/lxml cho web import.
- `ebooklib` cho EPUB.
- `playwright` có trong `requirements.txt`; chỉ dùng khi caller bật fallback và máy đã cài Chromium tương ứng.

Frontend:

- Server-rendered Jinja2, không có frontend build pipeline.
- CSS nằm trực tiếp trong `app/templates/base.html`.
- HTMX 1.9.10 và Google Fonts/Material Symbols được tải từ CDN.
- JavaScript thuần dùng cho modal reader, tìm kiếm chapter, toggle API key và giữ scroll khi HTMX swap.

Runtime:

- SQLite mặc định: `sqlite:///./ebook_translator.db`.
- FastAPI startup event gọi `init_db()` để tạo bảng và áp dụng schema patch.
- Session flash dùng cookie ký bởi `APP_SECRET`; nếu không đặt sẽ dùng chuỗi development mặc định.
- `app/static` được tạo ngay khi import `app.main`, sau đó mount tại `/static`.

## 4. Cấu trúc dự án

```text
app/
  main.py                         # FastAPI app, route, flash và template context
  config.py                       # Pydantic settings từ .env
  db.py                           # Engine, create_all, schema patch SQLite
  models.py                       # SQLModel tables
  services/
    chapter_cleaner.py            # Clean/split/join/chunk text
    chapter_order.py              # Sort chapter
    epub_importer.py              # Import EPUB
    web_importer.py               # HTTP fallback và parser HTML
    web_service.py                # Persist novel/chapter web
    glossary_service.py           # Context và pipeline dịch
    runner.py                     # Background thread registry
    translation_jobs.py           # Persist progress job
    provider_settings_service.py  # Config provider + default provider
    providers/
      base.py                     # Protocol và TranslationContext
      factory.py                  # Build/cache/resolve provider
      minimax.py                  # OpenAI-compatible providers và prompt
  templates/
    base.html
    index.html
    novel.html
    chapter.html
    api_settings.html
    partials/
      novel_chapter_row.html
      novel_stats.html

tests/
  test_parsers.py
  test_chapter_ui.py

DemoUI/                         # Tài liệu/demo thiết kế, không tham gia runtime
PROJECT_SPEC.md
README.md
requirements.txt
.env.example
```

## 5. Cấu hình

`app/config.py` đọc `.env` bằng `pydantic-settings` và bỏ qua biến dư.

| Biến | Mặc định | Trạng thái sử dụng |
|---|---|---|
| `APP_NAME` | `ebook-translator` | Có trong settings, chưa được dùng để đặt title app |
| `DATABASE_URL` | `sqlite:///./ebook_translator.db` | Đang dùng |
| `APP_HOST` | `127.0.0.1` | Dùng bởi `python -m app.main` |
| `APP_PORT` | `8000` | Dùng bởi `python -m app.main` |
| `MINIMAX_API_KEY` | rỗng | Fallback nếu DB không có row Minimax |
| `MINIMAX_GROUP_ID` | rỗng | Header `X-Group-Id` khi có giá trị |
| `MINIMAX_MODEL` | `MiniMax-M2.7-highspeed` | Đang dùng |
| `MINIMAX_BASE_URL` | `https://api.minimax.io/v1` | Đang dùng |
| `OPENROUTER_API_KEY` | rỗng | Fallback nếu DB không có row OpenRouter |
| `OPENROUTER_MODEL` | `deepseek/deepseek-v4-pro` | Đang dùng |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Đang dùng |
| `DEEPSEEK_API_KEY` | rỗng | Fallback nếu DB không có row DeepSeek |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Đang dùng |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | Đang dùng |
| `REQUEST_TIMEOUT` | `30` | Hiện chưa được route/service nối vào; service đang dùng default `30` riêng |
| `USE_CURL_CFFI_FALLBACK` | `true` | Có trong settings nhưng hiện chưa được route import đọc |
| `USE_PLAYWRIGHT_FALLBACK` | `false` | Có trong settings nhưng hiện chưa được route import đọc |
| `TRANSLATION_MAX_CHUNK_CHARS` | `600` | Đang dùng; chunk nhỏ hơn giúp provider giữ đúng cấu trúc dòng hơn |
| `TRANSLATION_CONCURRENCY` | `2` | Đang dùng, bị chặn trong khoảng `1..số chunk` |
| `TRANSLATION_TIMEOUT` | `600` giây | Timeout mỗi API call |
| `TRANSLATION_MAX_RETRIES` | `2` | Retry timeout/429/500/502/503/504 với exponential backoff |
| `AUTO_EXTRACT_GLOSSARY` | `true` | Đang dùng |
| `AUTO_SUMMARIZE_CHAPTER` | `true` | Đang dùng |

Lưu ý hiện trạng:

- `.env.example` chưa liệt kê ba biến OpenRouter dù `config.py` hỗ trợ chúng.
- Một row `ProviderSetting` trong DB ghi đè toàn bộ cấu hình `.env` của provider đó. Xóa row mới quay lại fallback `.env`.
- Form save đã được chuẩn hoá: để trống ô API key sẽ giữ nguyên key đã lưu; nhập key mới sẽ thay thế. Chỉ nút **Xóa khỏi DB** mới xoá hoàn toàn key/config provider. Lưu không có thay đổi sẽ báo flash info thay vì success.

## 6. Data model và migration

### `Novel`

- `id`, `title`, `translated_title`, `author`, `translated_author`.
- `source_type`, `source_url`, `description`, `cover_url`, `created_at`.

### `Chapter`

- Liên kết: `novel_id`; thứ tự: `index`.
- Metadata: `title`, `translated_title`, `source_url`.
- Nội dung: `raw_text`, `translated_text`.
- Dịch: `translation_provider`, `status`, `error_message`, `translation_warning`, `failed_translation_draft`.
- Thời gian: `created_at`, `updated_at`.

### Context dịch

- `GlossaryTerm`: source/target/category/notes theo `novel_id`.
- `ChapterSummary`: summary theo `novel_id` và `chapter_id`.
- `StyleGuide`: một row unique theo `novel_id`.

### Provider và app setting

- `ProviderSetting`: API key, base URL, model, group ID theo provider.
- `AppSetting`: key/value; hiện dùng key `default_provider`.

### `TranslationJob`

- Unique theo `chapter_id`, có `novel_id`, `provider`.
- `status`: `queued | running | done | error`.
- `total_chunks`, `done_chunks`, `failed_chunks`, `current_chunk`.
- `error_message`, `started_at`, `updated_at`.

`init_db()` gọi `create_all()` rồi `_apply_schema_patches()`. Schema patch chỉ chạy cho SQLite và thêm các cột còn thiếu bằng `ALTER TABLE`; không đổi type/constraint, không backfill và không thay Alembic. Patch hiện bao phủ các cột mới của `novel`, `chapter`, `translationjob` và `appsetting`.

## 7. HTTP routes thực tế

### Trang chủ và import

- `GET /`: danh sách novel, số chapter, trạng thái tổng hợp, cảnh báo provider.
- `POST /novels/import-url`: import URL, flash lỗi rồi redirect nếu thất bại.
- `POST /novels/import-epub`: đọc upload vào memory, từ chối file rỗng, import rồi redirect.
- `POST /novels/{novel_id}/delete`: xóa novel, chapter, glossary, summary và style guide.

### Novel detail và HTMX partial

- `GET /novels/{novel_id}`: hero, thống kê, bảng chapter, style guide, glossary.
- `GET /novels/{novel_id}/chapters`: trả các `<tr>` chapter; bảng gọi khi load, mỗi 5 giây và khi nhận event `novel-chapters-refresh`.
- `GET /novels/{novel_id}/chapters/{chapter_id}/row`: trả một row bọc trong table và stats OOB; hiện không được flow chính gọi trực tiếp.
- `GET /novels/{novel_id}/stats`: partial stats, tự poll mỗi 5 giây.
- `POST /novels/{novel_id}/style`: tạo/cập nhật style guide.
- `POST /novels/{novel_id}/glossary`: thêm term nếu source và target không rỗng.
- `POST /novels/{novel_id}/glossary/{term_id}/delete`: xóa term theo ID.
- `POST /novels/{novel_id}/fetch-all`: fetch tuần tự mọi chapter có URL và chưa có raw text; nuốt lỗi từng chapter.

### Chapter reader

- `GET /chapters/{chapter_id}?view=vi|raw|both`: mặc định `vi`; route không validate giá trị `view` ngoài ba giá trị trên.
- `POST /chapters/{chapter_id}/fetch`: fetch đồng bộ; từ reader redirect về `?view=raw`, từ novel detail trả response rỗng kèm HTMX event.
- `POST /chapters/{chapter_id}/translate`: kiểm tra raw/default provider/task đang chạy, đặt `translating`, khởi động background thread; từ reader redirect về `?view=vi`, từ novel detail phát HTMX event.

Hai POST chapter chấp nhận `return_to`. `_safe_return_to()` chỉ cho phép path nội bộ của đúng novel/chapter để tránh open redirect.

### Provider settings

- `GET /settings/api`.
- `POST /settings/api/{provider}/save`.
- `POST /settings/api/{provider}/clear`.
- `POST /settings/api/{provider}/test`.
- `POST /settings/api/{provider}/set-default`.

## 8. Luồng import

### Web

1. Route gọi `import_web_novel(session, url)` với default service hiện tại.
2. `smart_fetch()` thử `httpx`, sau đó `curl_cffi` nếu bật, rồi Playwright nếu bật.
3. HTML được decode theo HTTP charset, meta charset, rồi thử `utf-8`, `gb18030`, `gbk`, `gb2312`, `big5`, `latin-1`.
4. Với 69shuba, parser đọc trang hiện tại; URL `/book/{id}.htm` được đổi sang catalog `/book/{id}/` và fetch thêm khi cần. Dữ liệu tốt hơn được merge vào kết quả.
5. Site khác dùng generic parser: title từ `<title>`, author/cover theo selector, mọi anchor `.html` được xem là chapter.
6. Tạo `Novel`; nếu có default provider thì dịch title và author đồng bộ trong request import.
7. Sort chapter và tạo `Chapter(status="pending")`.

`parse_chapter_text()` ưu tiên các container content phổ biến; nếu không thấy sẽ chọn `div/section/article` có text dài nhất, clean HTML và bỏ một số dòng navigation.

### EPUB

1. Upload được đọc toàn bộ vào memory rồi ghi ra temporary `.epub`.
2. `ebooklib` đọc title/creator/description và document trong spine.
3. Title chapter lấy lần lượt từ `h1/h2/h3`, `<title>`, TOC hoặc fallback `Chapter N`.
4. Document có ít hơn 20 ký tự bị bỏ.
5. Novel title/author có thể được dịch đồng bộ bằng default provider.
6. Chapter được sort và lưu sẵn `raw_text`, `status="fetched"`.
7. Temporary file được xóa trong `finally`.

## 9. Luồng fetch và dịch chapter

### Fetch raw

1. `fetch_chapter_raw()` đặt `status="fetching"` và commit.
2. Fetch URL, parse text và cập nhật URL cuối sau redirect.
3. Thành công: lưu `raw_text`, đặt `fetched`.
4. Thất bại: đặt `error` rồi raise để route tạo flash.
5. Nếu chapter không có `source_url`, service trả chapter không thay đổi.

### Dịch nền

1. Route yêu cầu chapter có `raw_text`, không có thread sống cho cùng chapter và có default provider hợp lệ.
2. Route đặt `Chapter.status="translating"`, lưu provider rồi gọi `start_translation()`.
3. Runner đăng ký daemon thread trong dictionary in-memory.
4. Worker reset `TranslationJob`, mở session mới và gọi `translate_chapter()`.
5. Context gồm toàn bộ glossary, style guide, 5 summary gần nhất và title gốc của chapter.
6. Raw text được chia thành các chunk nhỏ theo dòng, mặc định 600 ký tự để dễ giữ đúng cấu trúc dòng.
7. Các chunk chạy bằng `ThreadPoolExecutor`; kết quả được ghép lại theo index gốc, không theo thứ tự hoàn thành.
8. Mỗi chunk thành công tăng `done_chunks`; chunk vẫn còn CJK sau cleanup tăng `failed_chunks`. `current_chunk = done + failed`.
9. Nếu output còn CJK, provider gọi lại `_chat()` với `CLEANUP_PROMPT` một lần. CJK còn lại tạo `translation_warning`, không tự fail cả chapter.
10. Nếu một chunk lệch dòng, provider được gọi lại với `LINE_ALIGNMENT_PROMPT` để thử căn dòng trước khi báo lỗi nghiêm trọng.
11. Output rỗng hoặc exception làm chapter/job chuyển `error`; draft lỗi được lưu vào `failed_translation_draft` khi có dữ liệu dịch nháp.
12. Nếu thiếu `translated_title`, provider dịch title sau khi phần nội dung hoàn tất nhưng trước khi chuyển chương sang `translated`.
13. Thành công: lưu `translated_text`, `translated_title`, `translation_provider`, `status="translated"`, job `done`.
14. Glossary extraction và summary chạy tiếp trong cùng worker; exception của hai bước này bị bỏ qua.
15. Runner lưu exception cuối vào `Chapter.error_message`, `TranslationJob.error_message` và cache `_last_errors`, sau đó gỡ task khỏi registry.

Job được đánh dấu `done` trước khi extract glossary/summary hoàn tất. App restart sẽ mất registry thread; không có resume/recovery cho trạng thái DB còn dở.

## 10. Provider

Provider hỗ trợ theo thứ tự hiển thị:

- `minimax`
- `openrouter`
- `deepseek`

Cả ba kế thừa `OpenAICompatProvider`:

- Minimax dùng `{base_url}/text/chatcompletion_v2` khi base URL chứa `minimax`, kèm `reply_constraints` và optional `X-Group-Id`.
- OpenRouter/DeepSeek dùng `{base_url}/chat/completions`.
- Parser response hỗ trợ `choices[].message.content`, delta content, `reasoning_content` khi `content` rỗng, Minimax legacy `reply` và top-level `content`.
- `ping()` vẫn là một chat completion nhỏ yêu cầu trả `OK`, không phải endpoint health riêng.
- Provider object được cache theo tên; save/clear/default route gọi `invalidate_cache()` phù hợp.

Default provider **không tự chọn theo thứ tự**. Người dùng phải bấm nút ngôi sao “Đặt làm mặc định”. Tên được lưu trong `AppSetting`; factory chỉ trả default nếu tên còn được hỗ trợ và provider vẫn có API key.

Prompt chính yêu cầu:

- Tiếng Việt hoàn toàn, không để CJK.
- Giữ glossary/style guide và cấu trúc paragraph.
- Văn phong tiên hiệp/huyền huyễn, không thêm bình luận.
- Không dịch title trong output nội dung; title dùng prompt metadata riêng.

## 11. Trạng thái và thống kê UI

Trạng thái persist của `Chapter`:

- `pending`, `fetching`, `fetched`, `translating`, `translated`, `error`.

UI dùng `_chapter_detail_status()` thay vì tin hoàn toàn vào `status`:

1. Có `translated_text` → `translated`.
2. Sau đó mới xét `translating`, `fetching`, `error`, `translated`.
3. Có raw text → `fetched`.
4. Còn lại → `not_fetched` (display-only, không phải status persist).

Trang chủ tổng hợp status novel từ `Chapter.status`. Novel chỉ hiện `translated` khi mọi chapter đều có status đó; chỉ hiện `fetched` khi toàn bộ chapter thuộc `fetched|translated` và có ít nhất một `fetched`.

Novel detail có bốn số:

- Tổng chương.
- Bản gốc.
- Đã dịch.
- Lỗi/Dịch = translating + fetching + error.

## 12. UI hiện tại

### Global

- Dark theme, sidebar desktop và mobile topbar trong `base.html`.
- Home/settings dùng shell chung.
- Novel detail và chapter reader ẩn sidebar/topbar, dùng canvas toàn chiều rộng.

### Home

- Cảnh báo khi chưa có API key hoặc chưa chọn default provider.
- Import URL/EPUB.
- Grid novel hiển thị cover, title/author đã dịch nếu có, source, số chapter, trạng thái và nút xóa.

### Novel detail

- Hero có cover, title/author/source/description và stats.
- Bảng chapter có status/action; fetch/translate/retry dùng HTMX và phát event refresh.
- Bảng và stats poll độc lập mỗi 5 giây; script giữ nguyên scroll table qua swap.
- Style guide và glossary nằm ở cột bên.

### Chapter reader

- Header chỉ hiển thị breadcrumb, title, badge và action phù hợp; không hiển thị title gốc/provider.
- Chapter đã có `translated_text` hiện `Đã dịch` và không hiện nút dịch.
- Tự reload mỗi 5 giây khi `Chapter.status` là `translating` hoặc `fetching`.
- Tabs: raw/vi/both; mặc định route là `vi`.
- Navigator trước/danh sách/sau nằm giữa tabs và reading area.
- Modal chapter list có search không dấu, active row, status badge và scrollbar custom.
- Danh sách được server-render; nếu context bị thiếu, JavaScript lazy-load từ `/novels/{id}/chapters`.
- Reader responsive: song song hai cột desktop, một cột mobile.

### API settings

- Ba card provider, mask key, hiển thị nguồn DB hoặc `.env`.
- Save, test, clear và chọn default.
- Toggle show/hide input key chỉ tác động input người dùng đang nhập; key đã lưu không được trả về browser.

## 13. Testing

Hai test script hiện có, tổng cộng 17 test function trong source:

```bash
python tests/test_parsers.py
python tests/test_chapter_ui.py
```

`test_parsers.py` kiểm tra cleaner, chunking, 69shuba, generic parser, charset và catalog URL. Direct runner cuối file gọi đủ 12 test function.

`test_chapter_ui.py` kiểm tra status derive, parallel reader, modal/search data, action dịch, lazy-load khi context cũ và default view `vi`.

Kiểm tra cơ bản sau thay đổi:

```bash
python -m compileall -q app tests
python tests/test_parsers.py
python tests/test_chapter_ui.py
git diff --check
```

Project chưa pin `pytest` trong `requirements.txt` và chưa có test tích hợp thật cho HTTP POST/background thread/provider network.

## 14. Rủi ro và technical debt đã biết

- `fetch-all` chạy đồng bộ, nuốt lỗi từng chapter và không có feedback chi tiết; route hiện không có nút trên template.
- `REQUEST_TIMEOUT`, `USE_CURL_CFFI_FALLBACK`, `USE_PLAYWRIGHT_FALLBACK` chưa được wiring từ settings vào route import. `import_web_novel(... allow_curl_cffi=...)` cũng không truyền tham số này xuống `import_from_url()`.
- Background translation registry chỉ ở memory; restart app có thể để `Chapter.translating`/`TranslationJob.running` bị treo.
- Xóa novel chưa xóa `TranslationJob`, nên có thể để orphan job hoặc gặp lỗi nếu môi trường bật foreign key enforcement.
- Xóa glossary term chỉ dùng `term_id`, chưa xác minh term thuộc `novel_id` trên URL.
- Stats `raw` hiện không cộng các chapter đã `translated`, dù chúng thường vẫn có raw text; số “Bản gốc” có thể thấp hơn thực tế.
- UI derive ưu tiên `translated_text`, vì vậy nếu retranslate bằng request thủ công trong lúc vẫn giữ bản dịch cũ, UI có thể vẫn hiển thị `translated` thay vì `translating/error`.
- Lỗi extract glossary và summarize bị bỏ qua; người dùng không biết hậu xử lý thất bại.
- Metadata translation chạy đồng bộ trong request import và có thể làm import chậm.
- Generic parser nhận mọi anchor `.html`, chưa deduplicate/filter mạnh như parser 69shuba.
- `fetch_chapter_raw()` không báo lỗi khi chapter không có `source_url`; nó trả nguyên object.
- Save provider với input key để trống ghi đè API key DB thành rỗng, trái với placeholder “nhập key mới để thay thế”.
- `.env.example` thiếu cấu hình OpenRouter.
- `TranslationProvider.translate()` trong Protocol yêu cầu `system_prompt`, trong khi implementation có default; type contract đang lệch.
- Type hint `_translate_one()` khai báo tuple 2 phần nhưng thực tế trả 3 phần `(index, text, warning)`.
- Không có auth/CSRF; chỉ phù hợp chạy local và không nên expose trực tiếp ra Internet.
- Không có Alembic, foreign-key cascade, pagination hoặc virtualized list; novel lớn render/poll danh sách chapter khá nặng.

## 15. Quy ước khi sửa dự án

1. Đọc `PROJECT_SPEC.md` và file liên quan trước khi sửa.
2. Giữ nguyên dữ liệu SQLite trừ khi người dùng yêu cầu xóa/migrate rõ ràng.
3. Với thay đổi schema, cập nhật model và xem xét `_SCHEMA_PATCHES`; patch hiện tại chỉ hỗ trợ thêm cột SQLite.
4. Với parser, đọc `web_importer.py`, `web_service.py` và cập nhật `test_parsers.py`.
5. Với pipeline dịch/provider, đọc `glossary_service.py`, `runner.py`, `translation_jobs.py`, factory và provider implementation.
6. Với UI, giữ CSS scoped theo page để không gây regression các template khác.
7. Nếu thêm provider, cập nhật settings, provider class/factory, `SUPPORTED_PROVIDERS`, API settings UI và `.env.example`.
8. Sau thay đổi, chạy compile, test script liên quan và `git diff --check`.

## 16. Lệnh thường dùng

Cài dependency:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Chạy app:

```bash
python -m app.main
# hoặc
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Nếu dùng Playwright fallback, cần cài browser riêng:

```bash
playwright install chromium
```
