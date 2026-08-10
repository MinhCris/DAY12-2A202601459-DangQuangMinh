# Thông Tin Deploy — Checkpoint 5

> **Chỉ ghi TÊN biến môi trường, tuyệt đối không dán giá trị API key vào đây.**
> Repo này công khai — dán khóa vào là mất khóa.

## Thông Tin Học Viên

| Mục | Nội dung |
|-----|----------|
| Họ và tên | Đặng Quang Minh |
| Mã học viên | 2A202601459 |
| Repo | https://github.com/MinhCris/DAY12-2A202601459-DangQuangMinh |

## Service

| Mục | Nội dung |
|-----|----------|
| Public URL | https://day12-2a202601459-dangquangminh-production.up.railway.app |
| Platform | Railway (project `confident-truth`, region `ams`, build từ Dockerfile) |
| Ngày deploy | 2026-08-10 |

## Biến Môi Trường Đã Set Trên Cloud

Ghi tên biến và **nguồn giá trị**, không ghi giá trị:

| Biến | Đã set | Ghi chú |
|------|--------|---------|
| `PORT` | ✅ | Railway tự gán lúc chạy, app đọc qua `${PORT:-8000}` |
| `AGENT_API_KEY` | ✅ | set bằng `railway variables --set-from-stdin`, giá trị chỉ nằm trong `.env` ở máy và trong dashboard — không có trong repo |
| `REDIS_URL` | ✅ | tham chiếu `${{Redis.REDIS_URL}}` tới Redis add-on của Railway trong cùng project |
| `RATE_LIMIT_PER_MINUTE` | ✅ | 10 |
| `MONTHLY_BUDGET_USD` | ✅ | 10.0 |
| `LOG_LEVEL` | ✅ | INFO |

## Lệnh Kiểm Tra

Thay `<URL>` bằng Public URL ở trên:

```bash
# 1. Liveness — mong đợi 200 {"status":"ok"}
curl -i <URL>/health

# 2. Readiness — mong đợi 200 {"status":"ready"} (đã nối được Redis)
curl -i <URL>/ready

# 3. Không có API key — mong đợi 401
curl -i -X POST <URL>/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'

# 4. Có API key — mong đợi 200 kèm câu trả lời
curl -i -X POST <URL>/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "X-User-Id: sv-test" \
  -d '{"question":"Deploy là gì?"}'

# 5. Rate limit — gọi 15 lần, những lần cuối phải trả 429
for i in $(seq 1 15); do
  curl -s -o /dev/null -w "%{http_code} " -X POST <URL>/ask \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $AGENT_API_KEY" \
    -H "X-User-Id: sv-test" \
    -d '{"question":"test"}'
done; echo
```

## Kết Quả Chạy Thật

Chạy lúc 2026-08-10, gọi vào bản deploy trên Railway:

```
### 1. GET /health
HTTP/2 200
{"status":"ok","service":"day12-agent","version":"1.0.0"}

### 2. GET /ready
HTTP/2 200
{"status":"ready","redis":true}

### 3. POST /ask không có key
HTTP/2 401
{"detail":"invalid or missing API key"}

### 4. POST /ask có key
HTTP/2 200
{"answer":"Câu hỏi hay. Deploy là gì thường được giải quyết bằng cách chuẩn hóa
môi trường chạy: cùng một image chạy giống nhau ở laptop và trên cloud. (Mình
đang nhớ 2 lượt trao đổi trước đó.)","user_id":"sv-test","history_length":2,
"cost_usd":3.315e-05,"tokens":{"in":41,"out":45}}

### 5. Rate limit — gọi 15 lần với cùng X-User-Id
200 200 200 200 200 200 200 200 200 200 429 429 429 429 429
```

Đọc kết quả:

- `/ready` trả `"redis":true` → service trên cloud thật sự mở được kết nối tới
  Redis add-on, không phải chỉ "process còn sống"
- `/ask` không key trả 401 → URL công khai nhưng không ai gọi chùa được
- Đúng 10 lần 200 rồi 5 lần 429 → cửa sổ trượt khớp `RATE_LIMIT_PER_MINUTE=10`
- `history_length` tăng dần giữa các lần gọi → state nằm ở Redis chứ không ở
  RAM của container

## Ảnh Chụp Màn Hình

Đặt ảnh trong thư mục `screenshots/`:

- `screenshots/dashboard.png` — trang quản lý service trên Railway
- `screenshots/health.png` — kết quả gọi `/health` từ trình duyệt hoặc curl

## Sự Cố Trong Quá Trình Deploy

Lần deploy đầu tiên **thất bại** ở bước healthcheck (build thì thành công).
Log runtime trên Railway:

```
Starting Container
Usage: uvicorn [OPTIONS] APP
Try 'uvicorn --help' for help.

Error: Invalid value for '--port': '$PORT' is not a valid integer.
Stopping Container
```

```
====================
Starting Healthcheck
====================
Path: /health
Retry window: 30s

Attempt #1 failed with service unavailable. Continuing to retry for 19s
Attempt #2 failed with service unavailable. Continuing to retry for 8s

1/1 replicas never became healthy!
Healthcheck failed!
```

Nguyên nhân: `startCommand` trong `railway.toml` ghi đè `CMD` của Dockerfile, và
Railway chạy `startCommand` **không qua shell** nên `$PORT` không được khai
triển — uvicorn nhận đúng chuỗi ký tự `"$PORT"`.

Cách sửa: bọc lệnh trong `sh -c` để có shell khai triển biến, kèm giá trị dự
phòng `${PORT:-8000}`.

```toml
# trước — hỏng
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT"

# sau — chạy được
startCommand = "sh -c 'uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}'"
```

Ngoài ra project lúc đó chưa có Redis add-on và service chưa được set biến môi
trường nào, nên đã bổ sung: tạo Redis bằng `railway add --database redis`, trỏ
`REDIS_URL` sang `${{Redis.REDIS_URL}}`, và set `AGENT_API_KEY` qua stdin để giá
trị không đi qua tham số dòng lệnh.
