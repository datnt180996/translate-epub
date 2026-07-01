# Ebook Translator - Project Spec

## 1. Muc Tieu Du An

Ebook Translator la mot web app local dung de import va dich truyen tieng Trung sang tieng Viet, tap trung vao the loai tien hiep, huyen huyen, tu chan.

Nguoi dung chinh la non-code user. App can uu tien thao tac qua giao dien web, han che yeu cau nguoi dung sua code thu cong.

## 2. Tinh Nang Hien Co

App hien ho tro:

- Import truyen tu URL web.
- Ho tro dac biet cho `69shuba.com`.
- Co parser generic cho site khac co link chuong dang `.html`.
- Import truyen tu file `.epub`.
- Tu tao danh sach chuong.
- Sap xep chuong theo thu tu hop ly, gom `序章`, `第1章`, `第一章`, `Chapter 1`, `番外`, `后记`, `外传`, `终章`, `附录`.
- Fetch noi dung goc tung chuong tu web. Sau khi fetch thanh cong, UI mac dinh mo `view=raw` de xem ban goc truoc.
- Fetch toan bo chuong web.
- Dich chuong bang provider AI.
- Dich nen bang thread de trinh duyet khong bi treo.
- Theo doi tien trinh dich theo chunk (progress bar) thong qua bang `TranslationJob` trong DB.
- Luu ban goc va ban dich trong SQLite.
- Luu loi dich (`error_message`) va canh bao chat luong (`translation_warning`) rieng, khong lan vao ban dich.
- Quan ly glossary theo tung truyen.
- Quan ly style guide theo tung truyen.
- Tu extract glossary sau khi dich.
- Tu tom tat chuong sau khi dich.
- Dung summary cac chuong truoc de giu mach dich.
- Xem ban goc, ban dich, hoac ca hai.
- Cau hinh API key cho provider tren web (khong can sua `.env`).
- Kiem tra ket noi provider bang nut "Kiem tra ket noi" (ping nhe).

## 3. Tech Stack

Backend:

- Python
- FastAPI
- SQLModel
- SQLite
- Jinja2 template
- httpx
- curl_cffi
- BeautifulSoup
- ebooklib
- optional Playwright fallback

Frontend:

- Server-rendered HTML bang Jinja2.
- CSS inline trong `app/templates/base.html`.
- Khong co build frontend.
- Co import htmx CDN nhung hien chua dung nhieu.

Database:

- SQLite mac dinh: `ebook_translator.db`.
- Cau hinh qua `DATABASE_URL`.

## 4. Cau Truc Thu Muc

```text
app/
  main.py
  config.py
  db.py
  models.py
  services/
    chapter_cleaner.py
    chapter_order.py
    epub_importer.py
    web_importer.py
    web_service.py
    glossary_service.py
    runner.py
    provider_settings_service.py
    translation_jobs.py
    providers/
      base.py
      factory.py
      minimax.py
  templates/
    base.html
    index.html
    novel.html
    chapter.html
    api_settings.html

tests/
  test_parsers.py

README.md
requirements.txt
.env.example
```

Luu y: `app/static` duoc tu tao khi app khoi dong neu chua ton tai (de tranh loi Starlette khi mount).

## 5. Cac File Quan Trong

### `app/main.py`

Entry point chinh cua web app.

Chua:

- Khoi tao FastAPI app.
- Mount static folder (tu tao `app/static` neu chua co).
- Session middleware.
- Routes import truyen.
- Routes xem truyen/chuong.
- Routes fetch raw chapter.
- Routes dich chuong.
- Routes glossary/style guide.
- Routes quan ly provider tren web.

Routes chinh:

- `GET /`
- `POST /novels/import-url`
- `POST /novels/import-epub`
- `POST /novels/{novel_id}/delete`
- `GET /novels/{novel_id}`
- `POST /novels/{novel_id}/style`
- `POST /novels/{novel_id}/glossary`
- `POST /novels/{novel_id}/fetch-all`
- `GET /chapters/{chapter_id}`
- `POST /chapters/{chapter_id}/fetch` (thanh cong redirect ve `?view=raw`)
- `POST /chapters/{chapter_id}/translate`
- `GET /settings/api`
- `POST /settings/api/{provider}/save`
- `POST /settings/api/{provider}/clear`
- `POST /settings/api/{provider}/test`

### `app/models.py`

Chua database models:

- `Novel`: truyen.
- `Chapter`: chuong (co them `error_message`, `translation_warning`).
- `GlossaryTerm`: thuat ngu dich co dinh.
- `ChapterSummary`: tom tat chuong.
- `StyleGuide`: style guide rieng cua tung truyen.
- `ProviderSetting`: cau hinh provider luu trong DB (key, base URL, model, group_id).
- `TranslationJob`: job dich nen (chapter_id, novel_id, provider, status, total/done/failed/current chunks, error_message).

### `app/config.py`

Doc cau hinh tu `.env`.

Bien cau hinh quan trong:

- `DATABASE_URL`
- `APP_HOST`
- `APP_PORT`
- `MINIMAX_API_KEY`
- `MINIMAX_GROUP_ID`
- `MINIMAX_MODEL`
- `MINIMAX_BASE_URL`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL`
- `DEEPSEEK_BASE_URL`
- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL` (mac dinh `deepseek/deepseek-v4-pro`)
- `OPENROUTER_BASE_URL` (mac dinh `https://openrouter.ai/api/v1`)
- `REQUEST_TIMEOUT`
- `USE_CURL_CFFI_FALLBACK`
- `USE_PLAYWRIGHT_FALLBACK`
- `TRANSLATION_MAX_CHUNK_CHARS`
- `TRANSLATION_CONCURRENCY`
- `TRANSLATION_TIMEOUT`
- `TRANSLATION_MAX_RETRIES`
- `AUTO_EXTRACT_GLOSSARY`
- `AUTO_SUMMARIZE_CHAPTER`

Cau hinh provider co the duoc ghi de tren web (luu SQLite) qua trang `Cấu hình API`. Khi do gia tri trong DB se duoc uu tien, neu khong co moi fallback sang `.env`.

### `app/services/web_importer.py`

Phu trach fetch va parse web.

Chuc nang chinh:

- Fetch HTML bang `httpx`.
- Fallback bang `curl_cffi`.
- Optional fallback bang Playwright.
- Decode HTML tu nhieu encoding nhu `utf-8`, `gb18030`, `gbk`, `gb2312`, `big5`.
- Parse muc luc `69shuba`.
- Parse chuong.
- Parser generic cho site khac.

Function quan trong:

- `smart_fetch`
- `parse_69shuba_index`
- `parse_generic_index`
- `parse_chapter_text`
- `import_from_url`
- `fetch_chapter_text`

### `app/services/web_service.py`

Noi parser web voi database.

Chuc nang:

- Import novel tu URL.
- Tao `Novel`.
- Tao danh sach `Chapter`.
- Fetch raw text cho chapter.

### `app/services/epub_importer.py`

Import EPUB.

Chuc nang:

- Doc metadata title/author/description.
- Doc spine documents.
- Extract text tu HTML trong EPUB.
- Tao `Novel`.
- Tao `Chapter`.
- Sap xep chuong.

### `app/services/chapter_cleaner.py`

Xu ly text.

Chuc nang:

- Clean HTML thanh text.
- Loai bo `script`, `style`, `nav`, `header`, `footer`, v.v.
- Split paragraph.
- Join paragraph.
- Chunk text de gui API dich. Chunk theo doan van, neu doan qua dai se cat theo dau cau (`。.!?！？;；:：`), neu cau van qua dai thi fallback cat theo ky tu.

### `app/services/chapter_order.py`

Sap xep chuong.

Chuc nang:

- Nhan title chuong.
- Tinh sort key.
- Ho tro so chuong Trung Quoc nhu `第一章`, `第十章`, `第二百章`.
- Dua chuong mo dau len truoc.
- Dua ngoai truyen/hau ky/phu luc ve cuoi.

### `app/services/glossary_service.py`

Logic dich chinh.

Chuc nang:

- Lay glossary.
- Lay style guide.
- Lay summary chuong truoc.
- Build translation context.
- Chia chuong thanh chunks (qua `chapter_cleaner.chunk_text`).
- Goi provider dich.
- Dich song song bang `ThreadPoolExecutor` (su dung `as_completed` de cap nhat progress theo thoi gian thuc).
- Luu ban dich vao `Chapter.translated_text`. **Canh bao chat luong (sot chu Han) duoc luu rieng vao `Chapter.translation_warning`**, khong append vao `translated_text`.
- Cap nhat `TranslationJob` qua `translation_jobs` de theo doi tien trinh.
- Tu extract glossary.
- Tu summarize chapter.

### `app/services/runner.py`

Chay dich nen.

Chuc nang:

- Theo doi chapter nao dang dich (in-memory thread registry).
- Tao background thread.
- Luu loi dich gan nhat vao `Chapter.error_message` trong DB de UI hien thi lai sau khi reload.
- Tranh dich trung cung mot chapter.
- Reset va cap nhat `TranslationJob` truoc/sau khi dich.

### `app/services/provider_settings_service.py`

Quan ly cau hinh provider luu trong DB.

Chuc nang:

- `SUPPORTED_PROVIDERS`: tuple cac provider ho tro (`minimax`, `openrouter`, `deepseek`).
- `list_provider_settings(session)`: liet ke trang thai provider cho trang `Cấu hình API`.
- `get_provider_config(session, provider)`: doc cau hinh DB, fallback `.env`.
- `save_provider_setting(session, provider, ...)`: luu key/base_url/model/group_id.
- `clear_provider_setting(session, provider)`: xoa khoi DB.
- `mask_key(value)`: mask key khi hien thi (dung `xxx...yyy`).

### `app/services/translation_jobs.py`

Quan ly job dich ben vung trong DB.

Ham:

- `get_or_create`, `reset`: tao/reset job theo `chapter_id`.
- `mark_running`: cap nhat `total_chunks`, status `running`.
- `increment_progress`: cap nhat `done_chunks` / `failed_chunks` / `current_chunk`.
- `mark_done`: status `done`.
- `mark_error`: status `error` kem `error_message`.

### `app/services/providers/minimax.py`

Provider dich OpenAI-compatible.

Hien co:

- `MinimaxProvider`
- `DeepSeekProvider`
- `OpenRouterProvider`

Ca ba dung chung base class `OpenAICompatProvider`.

Minimax endpoint:

- `/text/chatcompletion_v2`

DeepSeek endpoint:

- `/chat/completions`

OpenRouter endpoint:

- `/chat/completions` (mac dinh base URL `https://openrouter.ai/api/v1`)

File nay cung chua prompt chinh:

- `TRANSLATION_SYSTEM_PROMPT`
- `TERM_EXTRACTION_PROMPT`
- `SUMMARY_PROMPT`
- `CLEANUP_PROMPT` (prompt phu de sua ban dich con sot chu Han)

Helper:

- `contains_cjk(text)`, `find_cjk_spans(text)` de phat hien ky tu CJK con sot trong ban dich.

Lop `OpenAICompatProvider` cung cap:

- `translate(text, context)`: dich mot chunk.
- `extract_terms(...)`, `summarize_chapter(...)`: phu trinh.
- `ping()`: test ket noi nhe.

## 6. Luong Import URL

1. User nhap URL o trang chu.
2. `POST /novels/import-url`.
3. `main.py` goi `import_web_novel`.
4. `web_service.py` goi `import_from_url`.
5. `web_importer.py` fetch HTML.
6. Neu URL la `69shuba`, dung `parse_69shuba_index`.
7. Neu khong, dung `parse_generic_index`.
8. Tao `Novel`.
9. Sort chapters.
10. Tao cac `Chapter` voi status `pending`.
11. Redirect ve trang chi tiet truyen.

## 7. Luong Import EPUB

1. User upload file `.epub`.
2. `POST /novels/import-epub`.
3. `main.py` doc bytes.
4. Goi `import_epub_bytes`.
5. EPUB duoc ghi tam ra temp file.
6. `ebooklib` doc EPUB.
7. Extract metadata.
8. Extract spine document text.
9. Sort chapters.
10. Tao `Novel`.
11. Tao `Chapter` voi `raw_text` san va status `fetched`.

## 8. Luong Fetch Chapter

1. User mo chapter.
2. Neu chua co `raw_text`, UI hien nut tai noi dung goc.
3. `POST /chapters/{chapter_id}/fetch`.
4. `main.py` goi `fetch_chapter_raw`.
5. Status chuyen sang `fetching`.
6. Fetch HTML tu `chapter.source_url`.
7. Parse noi dung chuong.
8. Luu vao `chapter.raw_text`.
9. Status thanh `fetched`.
10. Redirect ve `/chapters/{id}?view=raw` de mac dinh mo ban goc.

## 9. Luong Dich Chapter

1. User bam "Dich chuong nay".
2. `POST /chapters/{chapter_id}/translate`.
3. Neu chua co raw text, bao loi.
4. Neu dang dich, bao loi.
5. Set status `translating`.
6. Reset `TranslationJob` trong DB.
7. `runner.py` tao background thread.
8. Trong thread, goi `translate_chapter`.
9. `translate_chapter` build context gom glossary, style guide, summaries gan nhat, chapter title.
10. `TranslationJob` duoc cap nhat `total_chunks`, status `running`.
11. Raw text duoc chia chunk theo doan/cau.
12. Provider dich tung chunk. **Sau moi chunk xong**, `TranslationJob` duoc cap nhat `done_chunks`/`failed_chunks`.
13. Neu phat hien CJK con sot trong ban dich, goi `cleanup_translation` (prompt `CLEANUP_PROMPT`) mot lan de sua.
14. Neu van con CJK, **khong fail ca chuong**. Chunk do duoc dem lai vao `failed_chunks` va gom warning luu vao `chapter.translation_warning`.
15. Ghep chunks thanh ban dich, luu `translated_text`. Status thanh `translated`. `TranslationJob` thanh `done`.
16. Neu co loi (provider raise...), `chapter.status=error`, `error_message` duoc luu vao DB, `TranslationJob` cung chuyen `error`.
17. Optional extract glossary.
18. Optional summarize chapter.
19. UI hien progress bar theo chunk khi dang dich. Khi xong, alert vang se hien canh bao chat luong (neu co), alert do se hien loi (neu co). UI co the tu reload.

## 10. Trang Thai Chapter

Status dang dung:

- `pending`: moi tao, chua fetch.
- `fetching`: dang fetch raw text.
- `fetched`: da co raw text.
- `translating`: dang dich nen.
- `translated`: da dich xong.
- `error`: loi fetch hoac dich.

Ngoai ra, moi chapter co mot `TranslationJob` lien ket voi cac truong:

- `status`: `queued` | `running` | `done` | `error`.
- `total_chunks`, `done_chunks`, `failed_chunks`, `current_chunk`: de UI hien progress.
- `error_message`: ly do loi neu `status=error`.

## 11. Provider Dich

Provider hien co:

- `minimax`
- `openrouter` (mac dinh model `deepseek/deepseek-v4-pro`, base URL `https://openrouter.ai/api/v1`)
- `deepseek`

Provider duoc liet ke trong UI neu co API key (uu tien trong DB, fallback `.env`).

Cau hinh provider tren web: vao `Cấu hình API` tren topbar. Moi provider co card rieng voi:

- API key (mat khi hien thi - mask dang `sk-...abcd`).
- Base URL.
- Model.
- Group ID (chi Minimax).
- Nut `Lưu cấu hình`, `Kiểm tra kết nối`, `Xóa khỏi DB`.

Default provider:

- Uu tien `minimax` neu co key.
- Tiep theo `openrouter` neu co key.
- Tiep theo `deepseek` neu co key.
- Neu khong co provider nao, UI bao chua cau hinh API key.

## 12. Prompt Dich

Prompt dich chinh yeu cau:

- Dich tu tieng Trung gian the sang tieng Viet.
- Van phong tien hiep/huyen huyen.
- Giu glossary.
- Giu cau truc doan.
- Khong them binh luan.
- Khong dich tieu de chuong.
- Chi tra ban dich tieng Viet.
- **Bat buoc tieng Viet thuan, khong duoc de sot chu Han** (ke ca luong tu nhu `一头/一只/一道/一个`). Neu gap tu chua biet, dich sang tieng Viet hoac phien am Han Viet bang chu Latin.
- Truoc khi tra loi, tu kiem tra CJK va sua sach.

`CLEANUP_PROMPT` la prompt phu dung de sua lai ban dich con sot chu Han (chi goi khi detect CJK trong output).

Khi sua prompt, can kiem tra file:

- `app/services/providers/minimax.py`

## 13. UI

Templates:

- `base.html`: layout, CSS, topbar (co link `Trang chủ`, `Cấu hình API`).
- `index.html`: import URL/EPUB, danh sach truyen.
- `novel.html`: chi tiet truyen, chuong, glossary, style guide.
- `chapter.html`: xem/fetch/dich chuong. Hien thi progress bar khi dang dich, alert canh bao chat luong (vang) neu co, alert loi (do) neu co.
- `api_settings.html`: trang `Cấu hình API` cho phep nhap/luu/test/xoa key provider.

Hien CSS nam truc tiep trong `base.html`.

## 14. Testing

Test hien co:

```bash
python tests/test_parsers.py
```

Test bao gom:

- clean HTML.
- split/join/chunk text.
- chunk theo dau cau khi doan van qua dai.
- parse 69shuba index.
- parse chapter content.
- parse generic index.
- decode charset.
- convert 69shuba book URL sang catalog URL.

Khi sua parser hoac cleaner, nen chay test nay.

## 15. Quy Uoc Khi AI Sua Du An

Khi yeu cau AI sua tinh nang, AI nen:

1. Doc `PROJECT_SPEC.md` truoc.
2. Doc file lien quan truoc khi sua.
3. Khong rewrite toan bo app neu chi can sua nho.
4. Uu tien thay doi nho, dung trong tam.
5. Neu sua parser web, doc `web_importer.py` va `tests/test_parsers.py`.
6. Neu sua dich/prompt/provider, doc `glossary_service.py`, `runner.py`, `providers/minimax.py`, `translation_jobs.py`.
7. Neu sua UI, doc template tuong ung trong `app/templates`.
8. Neu sua database model, doc `models.py`, `db.py`, va kiem tra anh huong du lieu SQLite cu. Co the them cot moi vao `_SCHEMA_PATCHES` trong `db.py` de migration tu dong.
9. Khong xoa du lieu user trong SQLite tru khi user yeu cau ro.
10. Khong doi provider API contract neu khong can.
11. Sau khi sua parser, chay `python tests/test_parsers.py`.
12. Sau khi sua app startup/routes, nen chay import app hoac khoi dong uvicorn neu co the.
13. Neu co thay doi `.env.example`, giai thich ro bien moi cho user non-code.
14. Neu them provider moi, can cap nhat: `config.py`, `providers/minimax.py` (them class), `providers/factory.py` (`_build_provider`, `get_provider_no_session`, `available_providers`), `provider_settings_service.py` (`SUPPORTED_PROVIDERS`, `_defaults_for`), `templates/api_settings.html` (placeholder/label rieng neu can).

## 16. Cac Diem Rui Ro Hien Biet

- `fetch-all` dang nuot loi tung chuong, nen user kho biet chuong nao loi.
- Background translation van dung in-memory thread registry, nen neu app restart giua luc dich thi `TranslationJob` trong DB se giu status cu (co the la `running`/`translating`). Can co co che resume/recover sau.
- **Da co migration nhe**: `app/db.py` co `_apply_schema_patches()` tu them cot moi vao bang `chapter` va `translationjob` qua `ALTER TABLE`. Van chay tot voi SQLite cu, khong can reset DB.
- Glossary extraction va chapter summary dang nuot loi im lang. Nen ghi warning de user biet.
- `provider.translate` trong `base.py` khai bao `system_prompt` bat buoc, nhung implementation co default. Day la lech nhe ve type/interface.
- `web_service.import_web_novel()` co tham so `allow_curl_cffi` nhung khong truyen ro xuong `import_from_url`.
- Canh bao chat luong (`translation_warning`) duoc luu rieng nhung chi hien thi tren UI, chua co co che retry tu dong chi chunk loi.
- Khi cleanup CJK that bai nhieu lan (vi du model chat luong thap), user phai tu sua ban dich thu cong.
- Khong co authentication. App mac dinh la local tool.
- Khong co export EPUB sau dich.
- Canh bao sot chu Han chi dem vao `failed_chunks` khi phat hien CJK sau cleanup; khong dem cleanup that bai don le.

## 17. Nhung Tinh Nang De Mo Rong

Cac huong mo rong hop ly:

- Export ban dich ra `.txt`, `.docx`, `.epub`.
- Dich hang loat nhieu chuong (da co `TranslationJob` lam nen tang).
- Retry chapter loi (da co `TranslationJob` + `error_message` de retry).
- Hien thi log loi fetch/dich tren UI.
- Cho chinh sua ban dich thu cong (editor text + luu lai).
- Quan ly glossary tot hon: edit term, merge duplicate, import/export glossary.
- Them provider khac (vi du OpenAI, Gemini, Claude) - khoi diem la OpenRouter da duoc them.
- Them parser rieng cho cac web truyen khac.
- Them progress bar tong cho nhieu chuong (ta da co progress theo chunk).
- Them co che resume job khi app restart (can cleanup `TranslationJob` co status `running` luc khoi dong).
- Da co migration nhe qua `_apply_schema_patches()`, nhuong van nen nang cap dung Alembic neu schema phuc tap hon.
- Tach CSS ra static file neu can UI lon hon.
- UI cho phep xem/clear `translation_warning` rieng (khong phai sua ca chapter).

## 18. Cach Giao Nhiem Vu Cho AI Trong Session Sau

Khi nho AI sua tinh nang, nen dua prompt dang:

```text
Doc PROJECT_SPEC.md truoc. Toi la non-code user.
Toi muon sua/them tinh nang: [mo ta tinh nang].
Hay tu doc file lien quan, sua code, chay test phu hop, roi bao lai ngan gon.
Khong xoa du lieu cu neu toi khong yeu cau.
```

Vi du:

```text
Doc PROJECT_SPEC.md truoc. Toi muon them nut export ban dich toan truyen ra file txt.
Hay tu sua code va them UI don gian cho toi.
```

Vi du:

```text
Doc PROJECT_SPEC.md truoc. Toi muon khi dich loi thi UI hien ly do loi thay vi chi status error.
Hay sua toi thieu va chay test neu phu hop.
```

## 19. Lenh Thuong Dung

Cai dependency:

```bash
pip install -r requirements.txt
```

Chay app:

```bash
python -m app.main
```

Hoac:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Chay test parser:

```bash
python tests/test_parsers.py
```

Khi sua `glossary_service.py`, `runner.py` hoac provider, nen chay them smoke test (neu co) de kiem tra progress/job va canh bao chat luong.

Cau hinh API key tren web: mo `Cấu hình API` tren topbar, chon provider, nhap key/model, luu. Co the test ket noi truoc khi dich. Neu muon quay ve dung `.env`, chon `Xóa khỏi DB`.

## 20. Nguyen Tac San Pham

Vi user la non-code user:

- Uu tien UI ro rang.
- Loi can hien thi bang tieng Viet de hieu.
- Khong yeu cau user mo database thu cong.
- Khong yeu cau user sua code thu cong.
- Neu can cau hinh `.env`, phai huong dan cu the bien nao can them/sua.
- Cac thao tac lau nhu fetch/dich nen chay nen hoac co trang thai tien trinh.
- Khong lam mat du lieu truyen, chuong, glossary, ban dich da luu.
