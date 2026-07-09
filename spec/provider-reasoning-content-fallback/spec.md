# Dự phòng khi provider trả bản dịch trong reasoning_content

## Mục tiêu

Một số model có thể trả `message.content` rỗng nhưng lại đặt nội dung hữu ích
trong `message.reasoning_content`. Khi gặp trường hợp này, app không nên báo
lỗi "Provider trả về nội dung rỗng" nếu vẫn có thể lấy được bản dịch.

## Hành vi

- App ưu tiên dùng `message.content` như trước.
- Nếu `message.content` rỗng, app thử đọc `message.reasoning_content`.
- Nếu response dạng streaming/delta cũng có `reasoning_content`, app cũng thử
  đọc trường đó.
- Khi dùng `reasoning_content`, app bỏ các dòng mở đầu ngắn có vẻ là suy nghĩ
  thừa, ví dụ một dòng tiếng Trung ngắn trước bản dịch.
- Nếu cả `content` và `reasoning_content` đều rỗng, app vẫn báo lỗi như cũ.

## Lý do

Ảnh lỗi thực tế cho thấy provider trả:

- `content`: rỗng.
- `reasoning_content`: có đoạn bản dịch tiếng Việt sau một dòng suy nghĩ ngắn.

Trước thay đổi này, app chỉ nhìn `content`, nên đánh dấu chương lỗi dù response
vẫn có bản dịch.

## File liên quan

- `app/services/providers/minimax.py`
- `tests/test_translation_quality.py`
- `PROJECT_SPEC.md`

## Giới hạn

- Đây chỉ là cơ chế cứu dữ liệu khi provider trả sai trường. Nếu
  `reasoning_content` chỉ chứa suy luận mà không có bản dịch, các bước kiểm tra
  chất lượng phía sau vẫn có thể chặn bản dịch.
- App vẫn ưu tiên khuyến nghị dùng model trả bản dịch trong `content` chuẩn.

## Kiểm tra

- `tests/test_translation_quality.py` có test mô phỏng response với
  `content=""` và `reasoning_content` chứa bản dịch sau một dòng tiếng Trung
  ngắn.
