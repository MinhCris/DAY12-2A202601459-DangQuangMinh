"""CP3 — Xác thực bằng API key.

Public URL = ai cũng gọi được. Không có lớp này, hóa đơn LLM của bạn do
người lạ quyết định.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from .config import get_settings

ANONYMOUS_USER = "anonymous"


def verify_api_key(
    x_api_key: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> str:
    """Kiểm tra header ``X-API-Key``; trả về user_id nếu hợp lệ.

    So sánh bằng ``secrets.compare_digest``, **không dùng** ``==``: toán tử
    ``==`` dừng ngay tại ký tự đầu khác nhau, nên thời gian trả lời rò rỉ
    thông tin về khóa (timing attack) — đoán đúng ký tự đầu thì phản hồi chậm
    hơn một chút, đo đủ nhiều lần là dò ra cả khóa. ``compare_digest`` luôn
    chạy hết chuỗi nên thời gian không phụ thuộc nội dung.
    """
    expected = get_settings().agent_api_key

    # encode() vì compare_digest chỉ nhận bytes hoặc chuỗi thuần ASCII —
    # client gửi khóa có ký tự Unicode sẽ làm nó ném TypeError.
    if x_api_key is None or not secrets.compare_digest(
        x_api_key.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing API key",
        )

    # user_id là đơn vị để rate limit và tính chi phí
    return x_user_id or ANONYMOUS_USER
