# Cập nhật tên chương sau khi dịch

## Mục tiêu

Khi một chương dịch xong, bảng danh sách chương phải hiện tên chương đã dịch
ngay, không để trạng thái `Translated` đi kèm tên chương gốc tiếng Trung.

## Hành vi

- Nếu `Chapter.translated_title` đang trống, hệ thống dịch tên chương sau khi
  nội dung chương đã qua bước kiểm tra chất lượng.
- Tên chương được dịch trước khi chương chuyển sang `status="translated"`.
- Lần lưu cuối cùng ghi chung `translated_text`, `translated_title`,
  `translation_provider` và `status="translated"`.
- Nếu dịch tên chương lỗi hoặc trả về rỗng, bản dịch nội dung vẫn được lưu và
  app tạm dùng lại tên chương gốc.

## File liên quan

- `app/services/glossary_service.py`
- `tests/test_translation_quality.py`

## Giới hạn

- Những chương cũ đã dịch nhưng còn thiếu `translated_title` không được tự động
  điền lại bởi thay đổi này.
- Chất lượng tên chương đã dịch vẫn phụ thuộc vào provider dịch.

## Kiểm tra

- `tests/test_translation_quality.py` kiểm tra rằng `translate_metadata()` chạy
  khi chương vẫn còn trạng thái `translating`, trước khi trạng thái cuối
  `translated` được lưu.
