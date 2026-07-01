from __future__ import annotations

import json
import re
import time
from typing import Optional

import httpx

from ...config import get_settings
from .base import TranslationContext, TranslationProvider


TRANSLATION_SYSTEM_PROMPT = (
    "Bạn là một dịch giả chuyên nghiệp, chuyên dịch tiểu thuyết tu tiên (Tiên hiệp / Huyền huyễn / Truyện tu chân) "
    "từ tiếng Trung (giản thể) sang tiếng Việt. Yêu cầu bắt buộc:\n"
    "1. Giữ nguyên tên riêng theo bảng glossary đã cung cấp, không tự ý đổi cách phiên âm.\n"
    "2. Văn phong cổ trang, trang trọng, mượt mà, phù hợp thể loại tu tiên. Dùng từ Hán Việt khi thích hợp "
    "(ví dụ: tu luyện, cảnh giới, tông môn, đan dược, pháp bảo).\n"
    "3. GIỮ NGUYÊN CẤU TRÚC DÒNG của bản gốc. Mỗi dòng trong văn bản gốc (tách bằng \\n) phải tương ứng đúng MỘT dòng trong bản dịch. "
    "TUYỆT ĐỐI KHÔNG gộp nhiều dòng gốc thành một dòng dài, không tách một dòng gốc thành nhiều dòng mới nếu bản gốc không có dòng trống ở đó. "
    "Dòng trống trong bản gốc (ngắt đoạn) phải tương ứng đúng một dòng trống trong bản dịch.\n"
    "4. Giữ nhịp câu và dấu câu phù hợp tiếng Việt (ví dụ: dấu phẩy, dấu chấm, dấu chấm hỏi, dấu chấm than) "
    "tương ứng với dấu câu trong bản gốc. Không tự ý thêm dấu câu hoặc bỏ dấu câu so với bản gốc.\n"
    "5. Không thêm bình luận, không thêm ghi chú, không dịch tiêu đề chương (tiêu đề sẽ được xử lý riêng).\n"
    "6. Giữ nguyên thuật ngữ tu luyện, cảnh giới, chiêu thức, pháp bảo theo style guide nếu có.\n"
    "7. Nếu gặp tên riêng chưa có trong glossary, hãy tạm phiên âm Hán Việt nhất quán và ghi chú lại trong đầu.\n"
    "8. CHỈ trả về bản dịch tiếng Việt, không kèm theo bản gốc, không kèm theo chú thích kỹ thuật.\n"
    "9. Bản dịch phải là tiếng Việt hoàn toàn. TUYỆT ĐỐI không để sót bất kỳ chữ Hán nào "
    "(kể cả lượng từ như 一头/一只/一道/一个, hoặc trợ từ cổ điển, hoặc bất kỳ ký tự nào thuộc chữ Hán giản thể/phồn thể). "
    "Nếu gặp từ/cụm chưa biết cách dịch, hãy dịch sang tiếng Việt hoặc phiên âm Hán Việt bằng chữ Latin, "
    "không được giữ nguyên chữ Hán trong bản dịch (trừ ký hiệu/đơn vị mà tác giả cố tình giữ).\n"
    "10. Trước khi trả lời, tự kiểm tra: (a) số dòng khớp với bản gốc, (b) không còn ký tự CJK nào. "
    "Nếu chưa đạt, hãy sửa lại cho đạt rồi mới trả về."
)


TERM_EXTRACTION_PROMPT = (
    "Bạn là trợ lý trích xuất thuật ngữ cho bản dịch truyện tu tiên. "
    "Hãy đọc đoạn văn bản gốc tiếng Trung và bản dịch tiếng Việt tương ứng, "
    "sau đó trích xuất các thuật ngữ quan trọng cần giữ nhất quán xuyên suốt truyện.\n"
    "Trả về JSON thuần (không kèm giải thích), đúng định dạng:\n"
    '[{"source": "tên gốc tiếng Trung", "target": "bản dịch tiếng Việt", "category": "character|place|technique|item|cultivation|other"}]\n'
    "Chỉ trả về mảng JSON, không có văn bản khác."
)


SUMMARY_PROMPT = (
    "Bạn là trợ lý tóm tắt truyện tu tiên. Hãy đọc bản gốc tiếng Trung và bản dịch tiếng Việt, "
    "sau đó viết một đoạn tóm tắt ngắn gọn (tối đa 200 từ) bằng tiếng Việt về diễn biến chính của chương, "
    "tập trung vào: sự kiện chính, nhân vật tham gia, thay đổi cảnh giới/đan dược/pháp bảo (nếu có), "
    "và tình tiết mở ra cho chương sau. CHỈ trả về đoạn tóm tắt, không kèm theo tiêu đề hay ghi chú."
)


def _format_context_block(context: TranslationContext) -> str:
    parts: list[str] = []

    if context.style_guide:
        parts.append(f"### Style guide cho truyện\n{context.style_guide}")

    if context.glossary:
        glossary_lines = []
        for term in context.glossary:
            cat = term.get("category", "general")
            src = term.get("source", "").strip()
            tgt = term.get("target", "").strip()
            if src and tgt:
                glossary_lines.append(f"- [{cat}] {src} -> {tgt}")
        if glossary_lines:
            parts.append("### Glossary (bắt buộc dùng các bản dịch này)\n" + "\n".join(glossary_lines))

    if context.previous_summaries:
        joined = "\n\n".join(context.previous_summaries[-5:])
        parts.append(f"### Tóm tắt các chương trước (để giữ mạch truyện)\n{joined}")

    if context.chapter_title:
        parts.append(f"### Tiêu đề chương hiện tại: {context.chapter_title}")

    return "\n\n".join(parts)


def _safe_json_array(text: str) -> list[dict]:
    if not text:
        return []
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    cleaned: list[dict] = []
    for item in data:
        if isinstance(item, dict) and item.get("source") and item.get("target"):
            cleaned.append(
                {
                    "source": str(item["source"]).strip(),
                    "target": str(item["target"]).strip(),
                    "category": str(item.get("category", "other")).strip() or "other",
                }
            )
    return cleaned


_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def contains_cjk(text: str) -> bool:
    return bool(text and _CJK_RE.search(text))


def find_cjk_spans(text: str, max_examples: int = 3) -> list[str]:
    if not text:
        return []
    return _CJK_RE.findall(text)[:max_examples]


CLEANUP_PROMPT = (
    "Bản dịch tiếng Việt dưới đây vẫn còn sót chữ Hán (ví dụ: 一头, 只, đạo, 个, hoặc bất kỳ CJK nào). "
    "Hãy viết lại toàn bộ bằng tiếng Việt thuần, giữ nguyên cấu trúc dòng (số dòng tách bằng \\n phải khớp với bản gốc đã cho), "
    "giữ nguyên tên riêng trong glossary, "
    "và loại bỏ toàn bộ chữ Hán. Chỉ trả về bản tiếng Việt đã sửa sạch, không kèm giải thích."
)


LINE_ALIGNMENT_PROMPT = (
    "Bản dịch tiếng Việt dưới đây KHÔNG giữ đúng cấu trúc dòng như bản gốc tiếng Trung. "
    "Yêu cầu: viết lại bản dịch sao cho số dòng (tách bằng \\n) khớp đúng với bản gốc. "
    "Mỗi dòng trong bản gốc phải tương ứng đúng một dòng trong bản dịch; "
    "dòng trống trong bản gốc phải tương ứng đúng một dòng trống trong bản dịch. "
    "TUYỆT ĐỐI KHÔNG thay đổi nội dung dịch, KHÔNG dịch lại, KHÔNG thêm bình luận. "
    "CHỉ định dạng lại dòng cho khớp với bản gốc. "
    "Chỉ trả về bản tiếng Việt đã định dạng lại, không kèm giải thích."
)


METADATA_TRANSLATION_PROMPT = (
    "Bạn là trợ lý dịch metadata cho truyện tu tiên tiếng Trung. "
    "Nhiệm vụ: dịch một TIÊU ĐỀ ngắn (tên truyện hoặc tên chương) sang tiếng Việt.\n"
    "Yêu cầu bắt buộc:\n"
    "1. Chỉ trả về MỘT dòng tiêu đề tiếng Việt. Không kèm giải thích, không kèm dấu nháy, không prefix.\n"
    "2. Giữ nguyên tên riêng đã quen thuộc (ví dụ: Hồng Hoang, Trung Thổ). Nếu tên phiên âm Hán Việt phổ biến, ưu tiên dùng.\n"
    "3. Bỏ các tiền tố lặt vặt như '第...章', '序章', '番外', '后记', '外传', '终章', '附录' hoặc chuyển sang dạng rõ ràng "
    "(ví dụ: '第1章' -> 'Chương 1', '番外' -> 'Ngoại truyện', '后记' -> 'Lời bạt').\n"
    "4. Văn phong gọn, tự nhiên, không thêm chú thích.\n"
    "5. Bản dịch phải là tiếng Việt thuần, TUYỆT ĐỐI không để sót chữ Hán."
)


def translate_metadata(provider: "OpenAICompatProvider", text: str) -> str:
    """Translate a short metadata string (novel/chapter title) to Vietnamese.

    Uses the lightweight metadata prompt. Returns empty string on failure
    so callers can fall back to the original text.
    """
    if provider is None or not text or not text.strip():
        return ""
    try:
        out = provider._chat(METADATA_TRANSLATION_PROMPT, text.strip(), temperature=0.2).strip()
    except Exception:
        return ""
    if not out:
        return ""
    out = out.splitlines()[0].strip().strip('"').strip("'").strip()
    if not out:
        return ""
    if contains_cjk(out):
        try:
            out = provider._chat(CLEANUP_PROMPT, out, temperature=0.0).strip()
        except Exception:
            return ""
        out = out.splitlines()[0].strip().strip('"').strip("'").strip()
    return out


class OpenAICompatProvider:
    def __init__(self, name: str, api_key: str, base_url: str, model: str, group_id: Optional[str] = None):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.group_id = group_id

    def _headers(self) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.group_id:
            headers["X-Group-Id"] = self.group_id
        return headers

    def _chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
        is_minimax = "minimax" in self.base_url.lower()
        url = (
            f"{self.base_url}/text/chatcompletion_v2"
            if is_minimax
            else f"{self.base_url}/chat/completions"
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if is_minimax:
            payload["reply_constraints"] = {"sender_type": "BOT", "sender_name": "Translator"}

        settings = get_settings()
        timeout_s = getattr(settings, "translation_timeout", 600) or 600
        max_retries = max(0, int(getattr(settings, "translation_max_retries", 2) or 0))
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                with httpx.Client(timeout=timeout_s) as client:
                    resp = client.post(url, headers=self._headers(), json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                break
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout) as e:
                last_exc = e
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise
            except httpx.HTTPStatusError as e:
                code = e.response.status_code if e.response is not None else 0
                if code in (429, 500, 502, 503, 504) and attempt < max_retries:
                    last_exc = e
                    time.sleep(2 ** attempt)
                    continue
                raise

        if is_minimax:
            base_resp = data.get("base_resp") or {}
            status_code = base_resp.get("status_code", 0)
            if status_code and status_code != 0:
                status_msg = base_resp.get("status_msg", "")
                raise RuntimeError(
                    f"Minimax API lỗi (status_code={status_code}): {status_msg}"
                )

        content = self._extract_content(data)
        if not content or not content.strip():
            raise RuntimeError(
                f"Provider trả về nội dung rỗng. Response: {str(data)[:500]}"
            )
        return content

    @staticmethod
    def _extract_content(data: dict) -> str:
        # OpenAI-compatible schema
        choices = data.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
            if content:
                return content
            delta = choices[0].get("delta") or {}
            if delta.get("content"):
                return delta["content"]
            messages = message.get("messages") or []
            if messages:
                last = messages[-1]
                text = last.get("text") if isinstance(last, dict) else None
                if text:
                    return text
        # Minimax legacy single-turn schema
        if data.get("reply"):
            return data["reply"]
        if data.get("content"):
            return data["content"]
        return ""

    def ping(self) -> dict:
        """Lightweight API check. Returns dict with ``ok`` and details."""
        system_prompt = "Bạn là hệ thống kiểm tra kết nối."
        user_prompt = (
            "Hãy trả lời đúng một từ: OK. Không kèm giải thích, không kèm bất kỳ ký tự nào khác."
        )
        try:
            content = self._chat(system_prompt, user_prompt, temperature=0.0).strip()
        except Exception as e:
            return {"ok": False, "error": str(e)}
        reply = (content[:32] if content else "").strip()
        return {
            "ok": True,
            "reply": reply,
            "model": self.model,
            "base_url": self.base_url,
        }

    def translate(self, text: str, context: TranslationContext, system_prompt: str = TRANSLATION_SYSTEM_PROMPT) -> str:
        context_block = _format_context_block(context)
        user_prompt = f"{context_block}\n\n### Văn bản gốc cần dịch\n{text}"
        return self._chat(system_prompt, user_prompt, temperature=0.4).strip()

    def extract_terms(self, novel_title: str, chapter_title: str, original_text: str, translated_text: str) -> list[dict]:
        user_prompt = (
            f"Tiểu thuyết: {novel_title}\nChương: {chapter_title}\n\n"
            f"### Bản gốc tiếng Trung\n{original_text}\n\n"
            f"### Bản dịch tiếng Việt\n{translated_text}\n\n"
            "Hãy trích xuất thuật ngữ quan trọng (tên nhân vật, địa danh, tông môn, chiêu thức, pháp bảo, "
            "cảnh giới tu luyện, đan dược) dưới dạng mảng JSON."
        )
        raw = self._chat(TERM_EXTRACTION_PROMPT, user_prompt, temperature=0.2)
        return _safe_json_array(raw)

    def summarize_chapter(self, novel_title: str, chapter_title: str, original_text: str, translated_text: str) -> str:
        user_prompt = (
            f"Tiểu thuyết: {novel_title}\nChương: {chapter_title}\n\n"
            f"### Bản gốc tiếng Trung (tham khảo)\n{original_text}\n\n"
            f"### Bản dịch tiếng Việt\n{translated_text}\n\n"
            "Hãy viết đoạn tóm tắt bằng tiếng Việt."
        )
        return self._chat(SUMMARY_PROMPT, user_prompt, temperature=0.3).strip()

    def translate_metadata(self, text: str) -> str:
        return translate_metadata(self, text)


class MinimaxProvider(OpenAICompatProvider):
    def __init__(self, api_key: str, base_url: str, model: str, group_id: str = ""):
        super().__init__(name="minimax", api_key=api_key, base_url=base_url, model=model, group_id=group_id)


class DeepSeekProvider(OpenAICompatProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        super().__init__(name="deepseek", api_key=api_key, base_url=base_url, model=model)


class OpenRouterProvider(OpenAICompatProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        super().__init__(name="openrouter", api_key=api_key, base_url=base_url, model=model, group_id="")
