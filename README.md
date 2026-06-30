# Ebook Translator

Công cụ web local giúp dịch truyện tu tiên (Tiên hiệp / Huyền huyễn) từ tiếng Trung sang tiếng Việt.

## Tính năng

- Import truyện từ **URL web** (mặc định hỗ trợ `69shuba.com`, kèm parser generic cho các site khác).
- Import truyện từ file **EPUB**.
- Tự động tách thành **danh sách chương**.
- **Fetch & dịch từng chương** theo lựa chọn của bạn.
- **Dịch nền**: bấm "Dịch chương này" là trả trang ngay, trạng thái `translating`,
  trang tự tải lại khi xong — không còn treo trình duyệt khi dịch lâu.
- **Glossary** tên nhân vật, địa danh, chiêu thức, cảnh giới... được dùng xuyên suốt các chương.
- **Style guide** riêng cho từng truyện.
- Sau mỗi chương, hệ thống tự rút trích thuật ngữ mới và tóm tắt chương để giữ mạch truyện.
- Sắp xếp danh sách chương theo số chương (`第1章` → cuối), `序章` trước, `番外`/`后记`/`感言` sau.
- Hỗ trợ **2 provider dịch**: `Minimax` (mặc định) và `DeepSeek`.

## Cài đặt

```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> **Không cần cài Playwright/Chromium.** Tool dùng `curl_cffi` để giả lập Chrome
> xử lý các site chặn bot (như 69shuba) nhẹ và nhanh hơn Playwright.
>
> Nếu muốn bật fallback Playwright (cho site JS nặng), cài thêm:
> `playwright install chromium` và đặt `USE_PLAYWRIGHT_FALLBACK=true` trong `.env`.

## Cấu hình

Sao chép `.env.example` thành `.env` và điền API key:

```env
MINIMAX_API_KEY=your_key
MINIMAX_GROUP_ID=your_group_id     # bắt buộc với Minimax
MINIMAX_MODEL=MiniMax-M2.7-highspeed
MINIMAX_BASE_URL=https://api.minimax.io/v1   # Minimax quốc tế; bản Trung Quốc: https://api.minimax.chat/v1

DEEPSEEK_API_KEY=your_key
DEEPSEEK_MODEL=deepseek-chat

# Tốc độ & chất lượng dịch
TRANSLATION_MAX_CHUNK_CHARS=5000   # lớn hơn -> ít lời gọi API hơn, nhanh hơn
TRANSLATION_CONCURRENCY=2          # số chunk dịch song song (1 tuần tự, 2-4 song song)
TRANSLATION_TIMEOUT=600            # timeout mỗi lời gọi API (giây) — model reasoning cần lâu
TRANSLATION_MAX_RETRIES=2          # thử lại khi timeout / 429 / 5xx
AUTO_EXTRACT_GLOSSARY=true         # tự trích thuật ngữ sau khi dịch xong
AUTO_SUMMARIZE_CHAPTER=true        # tự tóm tắt chương sau khi dịch xong
```

## Chạy app

```bash
python -m app.main
# hoặc
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Mở trình duyệt: http://127.0.0.1:8000

## Hướng dẫn sử dụng

1. **Import truyện**
   - Nhập URL mục lục (ví dụ: `https://www.69shuba.com/book/51256.htm`) hoặc upload file `.epub`.
   - App sẽ parse và tạo danh sách chương.

2. **Cấu hình glossary / style guide**
   - Vào trang chi tiết truyện, thêm các thuật ngữ bắt buộc giữ nhất quán.
   - Style guide giúp kiểm soát văn phong (Hán Việt, mức độ cổ trang, v.v.).

3. **Fetch chương** (với truyện từ web)
   - Bấm "Tải nội dung gốc" trên từng chương, hoặc "Fetch toàn bộ" ở trang truyện.

4. **Dịch chương**
   - Mở chương, chọn provider (Minimax / DeepSeek), bấm "Dịch chương này".
   - Bản dịch sẽ được lưu lại để xem lại bất kỳ lúc nào.

5. **Giữ tên nhân vật xuyên suốt**
   - Sau mỗi chương dịch, app tự gọi model để rút glossary.
   - Glossary này sẽ được đưa vào prompt cho các chương tiếp theo.

## Kiến trúc

```
app/
  main.py                      # FastAPI routes
  config.py                    # Settings (pydantic-settings)
  db.py                        # SQLModel engine & session
  models.py                    # Novel, Chapter, GlossaryTerm, ChapterSummary, StyleGuide
  services/
    chapter_cleaner.py         # Clean HTML, chunk text theo đoạn
    epub_importer.py           # Import EPUB
    web_importer.py            # Fetch web (httpx + Playwright fallback)
    web_service.py             # Import truyện web, fetch từng chương
    glossary_service.py        # Glossary, style guide, dịch chương
    providers/
      base.py                  # Interface TranslationProvider
      minimax.py               # Provider OpenAI-compat (dùng cho cả Minimax & DeepSeek)
      factory.py               # Lấy provider theo tên
templates/                     # Jinja2 templates
static/                        # CSS / JS tĩnh
```

## Lưu ý về provider

- `Minimax` dùng endpoint OpenAI-compatible (`/text/chatcompletion_v2`) và cần `MINIMAX_GROUP_ID`.
- `DeepSeek` dùng endpoint OpenAI-compatible (`/chat/completions`).
- Nếu không cấu hình key của provider nào thì provider đó sẽ không xuất hiện trong dropdown.

## Tùy biến

- `REQUEST_TIMEOUT`: timeout cho HTTP request (giây).
- `USE_CURL_CFFI_FALLBACK=true` để dùng `curl_cffi` (giả lập Chrome) khi `httpx` bị 403 (mặc định bật).
- `USE_PLAYWRIGHT_FALLBACK=false` để tắt fallback Playwright (mặc định tắt).

## Kiểm thử

```bash
python tests/test_parsers.py
```

Test bao gồm: làm sạch HTML, chia chunk, parser 69shuba (mục lục + nội dung chương), parser generic.
