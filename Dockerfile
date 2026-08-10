# ═══════════════════════════════════════════════════════════════════
# CP2 — Containerization (bản production-ready)
#
#   [x] Multi-stage: stage `builder` cài dependency (được phép nặng, có
#       compiler), stage `runtime` chỉ nhận KẾT QUẢ đã cài
#   [x] Base image slim ở cả hai stage
#   [x] COPY requirements.txt + pip install TRƯỚC khi COPY source code
#   [x] Chạy bằng user thường `appuser` (uid 10001), không phải root
#   [x] HEALTHCHECK gọi vào /health
#   [x] Đọc cổng từ biến môi trường PORT (cloud tự gán cổng)
#
# Build:  docker build -t day12-agent:prod .
#         docker images day12-agent:prod
# ═══════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────
# Stage 1 — builder: cài thư viện vào một thư mục riêng (/install)
# Stage này bị vứt đi sau khi build, nên compiler và cache pip
# không bao giờ có mặt trong image cuối.
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Một số thư viện (uvloop, httptools...) có thể phải biên dịch khi
# nền tảng của bạn chưa có sẵn wheel — compiler chỉ cần ở đây.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Chỉ copy file khai báo thư viện trước. Docker cache theo layer và huỷ
# cache từ layer đầu tiên thay đổi trở đi: sửa code không đụng tới file
# này thì layer pip install bên dưới vẫn được dùng lại.
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ─────────────────────────────────────────────────────────────
# Stage 2 — runtime: đây mới là image được đóng gói
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# PYTHONUNBUFFERED: log ra stdout ngay lập tức, không nằm kẹt trong buffer
# khi container bị dừng — mất log đúng lúc cần đọc nhất.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Chỉ mang sang KẾT QUẢ của builder, không mang theo compiler
COPY --from=builder /install /usr/local

# User thường: kẻ tấn công thoát được khỏi app cũng chỉ là uid 10001,
# không phải root trên host.
RUN useradd --create-home --uid 10001 appuser

# Source code copy SAU cùng — layer thay đổi nhiều nhất nằm cuối
COPY app ./app
COPY utils ./utils

USER appuser

EXPOSE 8000

# Docker tự gọi /health định kỳ; 3 lần liên tiếp lỗi thì container bị đánh
# dấu unhealthy và orchestrator restart nó.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health').read()" || exit 1

# 0.0.0.0 chứ không phải 127.0.0.1: bind vào localhost thì bên ngoài
# container không gọi vào được.
# ${PORT:-8000}: Railway/Render/Cloud Run tự gán cổng qua biến PORT.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
