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
    "3. Giữ nguyên cấu trúc đoạn văn gốc. Mỗi đoạn văn trong bản gốc phải tương ứng đúng một đoạn văn trong bản dịch.\n"
    "4. Không thêm bình luận, không thêm ghi chú, không dịch tiêu đề chương (tiêu đề sẽ được xử lý riêng).\n"
    "5. Giữ nguyên thuật ngữ tu luyện, cảnh giới, chiêu thức, pháp bảo theo style guide nếu có.\n"
    "6. Nếu gặp tên riêng chưa có trong glossary, hãy tạm phiên âm Hán Việt nhất quán và ghi chú lại trong đầu.\n"
    "7. CHỈ trả về bản dịch tiếng Việt, không kèm theo bản gốc, không kèm theo chú thích kỹ thuật."
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


class MinimaxProvider(OpenAICompatProvider):
    def __init__(self, api_key: str, base_url: str, model: str, group_id: str = ""):
        super().__init__(name="minimax", api_key=api_key, base_url=base_url, model=model, group_id=group_id)


class DeepSeekProvider(OpenAICompatProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        super().__init__(name="deepseek", api_key=api_key, base_url=base_url, model=model)
