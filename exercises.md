# Phiếu Phản Ánh — K3 Ngày 12

> **Bài làm cá nhân.** Trả lời bằng lời của chính bạn, dựa trên những gì bạn
> quan sát được khi chạy code — không sao chép đáp án của người khác.
>
> Cách trả lời: thay dòng placeholder in nghiêng dưới mỗi câu bằng câu trả lời.
> `grade.py` đếm số câu đã trả lời (15 điểm cho 10 câu).
>
> Họ và tên: Đặng Quang Minh  Mã học viên: 2A202601459

---

### Câu 1 — Fail fast (CP1)

Trong `Settings`, `agent_api_key` không có giá trị mặc định nên app chết ngay
khi khởi động nếu thiếu biến môi trường. Hãy mô tả một tình huống cụ thể mà
việc "chết sớm" này cứu bạn, so với việc để mặc định `"changeme"`.

Tình huống: mình deploy lên Railway, tạo service từ Dockerfile, nhưng quên
chưa `railway variables --set AGENT_API_KEY=...` trong dashboard.

**Với bản không có mặc định (bản mình đang làm):** uvicorn import `app.main`,
`get_settings()` chạy, pydantic ném lỗi ngay và process thoát. Mình thử lại ở
máy bằng cách bỏ biến môi trường đi:

```
ValidationError: 1 validation error for Settings
agent_api_key
  Field required [type=missing, input_value={}, input_type=dict]
```

Container không bao giờ lên tới trạng thái healthy → health check của Railway
timeout → deploy bị đánh dấu thất bại và bản cũ vẫn được giữ nguyên phục vụ.
Mình biết mình sai trong khoảng 30 giây, lúc còn đang nhìn màn hình deploy, và
production không hề bị ảnh hưởng.

**Nếu để mặc định `"changeme"`:** app khởi động bình thường, `/health` trả 200,
Railway báo deploy thành công, mình đóng laptop đi ngủ. Nhưng lúc đó endpoint
`/ask` đang được bảo vệ bằng một chuỗi mà bất kỳ ai đọc repo (hoặc đoán) cũng
biết — mà repo này là public. Bot quét Internet tìm ra URL trong vài giờ, thử
vài khóa mặc định phổ biến, và bắt đầu gọi LLM bằng tiền của mình. Cơ chế duy
nhất còn chặn được là cost guard, nghĩa là mình chỉ phát hiện khi ngân sách đã
bị tiêu và user thật bắt đầu nhận 402. Lỗi vẫn là lỗi đó, chỉ khác là nó hiện
ra sau vài ngày và sau khi đã mất tiền, thay vì hiện ra ngay lúc deploy.

Ý chung: một biến thiếu là lỗi cấu hình. Fail fast biến nó thành lỗi *lúc
deploy* (rẻ, dễ sửa); giá trị mặc định biến nó thành lỗ hổng *lúc chạy* (đắt,
khó phát hiện).

---

### Câu 2 — Log cho máy đọc (CP1)

Chạy service và gọi `/ask` vài lần. Dán một dòng log JSON bạn thu được, rồi
nêu **hai** việc bạn làm được với dòng log đó mà `print("đã trả lời xong")`
không làm được.

Một dòng log thật lấy từ `docker compose logs agent`:

```json
{"event": "ask_completed", "level": "info", "timestamp": "2026-08-10T04:46:30.354806+00:00", "user_id": "sv01", "tokens_in": 36, "tokens_out": 50, "cost_usd": 3.54e-05}
```

**Việc 1 — cộng tiền theo user mà không cần viết regex.** Mỗi trường là một
khóa JSON nên chỉ cần `json.loads` rồi gom nhóm. Mình chạy thật trên log của
15 request vừa gọi:

```bash
docker compose logs --no-log-prefix agent | grep '"event": "ask_completed"' | python -c "..."
  sv-rl: 10 request, 0.000540 USD
  sv01:  5 request, 0.000202 USD
```

Trả lời được câu "user nào tiêu nhiều tiền nhất hôm nay". Với
`print("đã trả lời xong")` thì trong dòng log không hề có `user_id` lẫn
`cost_usd` — không có dữ liệu để cộng, muốn có phải sửa code và deploy lại.

**Việc 2 — lọc và cảnh báo theo trường.** Vì có `level` và `timestamp` chuẩn
ISO-8601 kèm offset, mình đếm được số dòng `level="error"` trong 5 phút gần
nhất và đặt ngưỡng cảnh báo. Trên Railway/Render/Datadog, log JSON một dòng
được tự động index theo trường, nên gõ `user_id:"sv01"` là ra ngay mọi lượt
của user đó, không phải `grep` mò trong văn bản tự do. Còn `print()` cho ra
chuỗi tiếng Việt không cấu trúc: muốn lọc phải đoán định dạng bằng regex, và
regex đó vỡ ngay lần đầu ai đó sửa câu chữ trong `print`.

Chi tiết nhỏ nhưng quan trọng: log phải nằm gọn **một dòng**. Nếu dùng
`json.dumps(..., indent=2)` thì cloud gom log theo dòng sẽ cắt một event thành
8 mảnh rời rạc, không mảnh nào parse được.

---

### Câu 3 — Kích thước image (CP2)

Build cả hai phiên bản và ghi lại số đo thật:

```bash
docker build -f <Dockerfile-1-stage> -t agent:single .
docker build -t agent:multi .
docker images | grep agent
```

| Bản | Dung lượng |
|-----|-----------|
| 1 stage (bản đầu) | **1190 MB** (1.19 GB) |
| Multi-stage | **183 MB** |

Giải thích: phần dung lượng chênh lệch đó là những gì?

Chênh lệch khoảng **1.0 GB**, gồm ba phần:

1. **Base image (~975 MB — phần lớn nhất).** `python:3.11` bản đầy đủ là
   1.1 GB, `python:3.11-slim` chỉ 125 MB. Bản đầy đủ mang theo cả toolchain
   Debian: gcc/g++, make, git, các gói `-dev`, tài liệu, locale... Service của
   mình chạy xong rồi thì không cần một cái nào trong số đó.

2. **Compiler và cache của lúc cài đặt.** Trong bản multi-stage, `build-essential`
   và toàn bộ thư mục tạm của pip nằm ở stage `builder` — stage này bị vứt đi,
   image cuối chỉ nhận `COPY --from=builder /install /usr/local`. Xem
   `docker history day12-agent:prod`, layer thư viện Python chỉ 42.4 MB.
   Bản 1 stage thì cài trực tiếp nên mọi thứ ở lại trong image.

3. **Rác từ `COPY . .`.** Bản đầu copy nguyên thư mục làm việc, tức là cả
   `.git`, `.venv`, `tests/`, screenshots. `.dockerignore` mình viết ở CP2 loại
   hết những thứ đó, và image chỉ còn `app/` với `utils/` (khoảng 60 kB).

Vì sao phải quan tâm: 183 MB thay vì 1.19 GB nghĩa là mỗi lần deploy đẩy/kéo
ít hơn ~6 lần dữ liệu qua mạng, cold start nhanh hơn hẳn. Và image production
không còn sẵn compiler — kẻ tấn công vào được container cũng không có công cụ
để biên dịch thêm gì.

---

### Câu 4 — Thứ tự lệnh trong Dockerfile (CP2)

Sửa một ký tự trong `app/main.py` rồi build lại. Với Dockerfile của bạn, những
layer nào được dùng lại từ cache, layer nào phải chạy lại? Nếu bạn đặt
`COPY . .` lên trước `RUN pip install` thì kết quả khác thế nào?

Mình thêm một dòng comment vào `app/main.py` rồi `docker build` lại. Kết quả
thật (build lần đầu mất **7 phút 24 giây**, lần này mất khoảng **4 giây**):

**Được dùng lại từ cache — `CACHED`:**
- `[builder 2/5] WORKDIR /app`
- `[builder 3/5] RUN apt-get update && apt-get install build-essential`
- `[builder 4/5] COPY requirements.txt .`
- `[builder 5/5] RUN pip install --prefix=/install -r requirements.txt` ← nặng nhất, 113 giây
- `[runtime 3/6] COPY --from=builder /install /usr/local`
- `[runtime 4/6] RUN useradd --uid 10001 appuser`

**Phải chạy lại:**
- `[runtime 5/6] COPY app ./app` (0.4 s) — đúng layer chứa file mình vừa sửa
- `[runtime 6/6] COPY utils ./utils` (0.2 s) — nằm sau nên bị kéo theo
- bước export image

Lý do: Docker cache theo từng layer và hủy cache **từ layer đầu tiên thay đổi
trở đi**. `requirements.txt` không đổi nên checksum của layer `COPY
requirements.txt .` không đổi → layer `pip install` ngay sau nó vẫn hợp lệ.

**Nếu đặt `COPY . .` trước `RUN pip install`:** layer copy đó gộp cả
`app/main.py`, nên sửa một dấu phẩy là checksum đổi → cache hỏng từ đó →
`apt-get install build-essential` và `pip install` phải chạy lại toàn bộ. Nói
cách khác, mỗi lần sửa một ký tự sẽ tốn lại gần đúng 7 phút của lần build đầu
thay vì 4 giây. Nhân với vài chục lần build một ngày thì đó là khác biệt giữa
làm việc được và không.

---

### Câu 5 — Vì sao không chạy bằng root (CP2)

Container mặc định chạy bằng root. Mô tả chuỗi sự kiện dẫn từ "một lỗ hổng
trong code Python của bạn" tới "kẻ tấn công có quyền cao trên máy host", và
lệnh `USER` cắt đứt chuỗi đó ở chỗ nào.

Chuỗi sự kiện khi container chạy bằng root:

1. **Lỗ hổng RCE trong app.** Ví dụ một endpoint nhận chuỗi từ user rồi đưa
   vào `subprocess`/`eval`, hoặc một thư viện phụ thuộc dính lỗi
   deserialization. Kẻ tấn công chạy được lệnh tùy ý *trong* container, với
   đúng quyền của tiến trình uvicorn.
2. **Tiến trình đó là uid 0** → họ là root trong container: đọc được mọi file
   của image, đọc biến môi trường của tiến trình chính (`/proc/1/environ` —
   nơi chứa `AGENT_API_KEY` và `REDIS_URL` có mật khẩu), cài thêm công cụ bằng
   `apt-get`, ghi đè cả code của app.
3. **Bước ra host.** Container không phải máy ảo, nó dùng chung kernel với
   host. Với uid 0 trong container, kẻ tấn công khai thác được những đường mà
   user thường không đụng tới: nếu container mount `/var/run/docker.sock` thì
   họ tạo container mới với `--privileged` và mount `/` của host; nếu có
   bind-mount thư mục host thì họ ghi vào đó với quyền root; nếu chạy
   `--privileged` hoặc có `CAP_SYS_ADMIN` thì thao tác trực tiếp với thiết bị;
   và các lỗ hổng escape của runc/kernel gần như đều yêu cầu uid 0 trong
   container.
4. **Kết quả:** uid 0 trong container ánh xạ thẳng thành uid 0 trên host
   (khi không bật user-namespace remapping) → root trên máy host, tức là mọi
   container khác trên cùng máy cũng mất.

**`USER appuser` cắt ở bước 2 → 3.** Sau lệnh đó tiến trình chạy bằng uid
10001 (mình kiểm tra trong container: `uid=10001(appuser) gid=10001(appuser)`).
Kẻ tấn công vẫn thực hiện được bước 1 — `USER` không sửa lỗ hổng code — nhưng
từ đó trở đi họ chỉ là một user thường: không ghi được vào `/usr` hay `/app`
(đều thuộc root), không cài được package, không bind được cổng dưới 1024, và
những con đường escape ở bước 3 hầu hết đóng lại vì đòi hỏi quyền root. Nếu
họ có thoát ra host thì cũng chỉ là uid 10001 vô danh, không sở hữu gì.

Nói gọn: `USER` không ngăn được việc bị xâm nhập, nó ngăn việc "xâm nhập một
app" leo thang thành "chiếm cả máy chủ".

---

### Câu 6 — Cửa sổ trượt (CP3)

Rate limit của bạn dùng sliding window 60 giây. Nếu thay bằng cách đếm theo
phút đồng hồ (reset lúc giây 00), một người dùng có thể gửi tối đa bao nhiêu
request trong 2 giây liên tiếp khi hạn mức là 10/phút? Giải thích cách đạt được
con số đó.

**20 request trong 2 giây** — gấp đôi hạn mức.

Cách đạt được: bộ đếm kiểu fixed window gắn với nhãn phút đồng hồ (ví dụ key
`ratelimit:sv01:10:00`) và tự reset về 0 khi sang phút mới.

- 10:00:59 — gửi 10 request. Bộ đếm của phút `10:00` chạy từ 0 lên 10, tất cả
  đều được cho qua vì chưa vượt hạn mức của phút đó.
- 10:01:00 — sang phút mới, key đổi thành `ratelimit:sv01:10:01`, bộ đếm bắt
  đầu lại từ 0.
- 10:01:01 — gửi tiếp 10 request. Cũng hợp lệ, vì đây là quota của phút mới.

Tổng: 20 request trong khoảng 2 giây, và không request nào "phạm luật" theo
cách đếm đó. Lỗ hổng nằm ở chỗ fixed window chỉ hỏi "request này thuộc phút
nào", chứ không hỏi "60 giây vừa qua đã có bao nhiêu request". Ở đúng ranh
giới cửa sổ, hai nửa quota của hai phút liền kề dồn lại thành một burst gấp
đôi — server nhận tải gấp đôi thiết kế đúng vào thời điểm nó không ngờ tới.

Sliding window của mình không có kẽ hở đó vì mỗi lần `check()` đều tính lại
cửa sổ từ thời điểm hiện tại: `zremrangebyscore(key, 0, now - 60)` vứt các
request đã quá 60 giây, rồi `zcard` đếm phần còn lại. Tại 10:01:01, 10 request
của 10:00:59 mới trôi qua 2 giây nên vẫn nằm trong cửa sổ → request thứ 11 bị
429 ngay. Đo thực tế trên stack đang chạy (hạn mức 10/phút, 15 request liên
tiếp):

```
200 200 200 200 200 200 200 200 200 200 429 429 429 429 429
```

---

### Câu 7 — Rate limit và cost guard (CP3)

Hai cơ chế này khác nhau ở điểm nào? Cho một tình huống mà rate limit cho qua
nhưng cost guard phải chặn, và một tình huống ngược lại.

| | Rate limit | Cost guard |
|---|---|---|
| Đếm cái gì | **số lượng** request | **số tiền** đã tiêu |
| Cửa sổ | 60 giây trượt | tháng dương lịch (`cost:<user>:2026-08`) |
| Bảo vệ | tài nguyên: worker, CPU, độ trễ cho user khác | ngân sách của mình |
| Mã lỗi | 429 — chờ một chút rồi gọi lại là được | 402 — thử lại cũng vô ích cho tới tháng sau |
| Cấu trúc | ZSET, score = timestamp | string, `incrbyfloat` |

**Rate limit cho qua nhưng cost guard chặn.** Một user gửi 5 request mỗi phút
— chỉ bằng một nửa hạn mức 10/phút, hoàn toàn "ngoan". Nhưng mỗi request là
một tài liệu 50.000 token dán vào ô câu hỏi, tốn cỡ 0,5 USD một lượt. Sau
khoảng 4 phút, tổng chi tiêu vượt `MONTHLY_BUDGET_USD=10` → `guard.check()`
trả 402, trong khi rate limiter không thấy gì bất thường cả vì nó chỉ biết đếm
5 < 10. Đây chính là lý do rate limit một mình là không đủ: nó không biết gì
về kích thước của từng request.

**Cost guard cho qua nhưng rate limit chặn.** Một user mới, `spent()` đang là
0.0. Họ (hoặc script của họ) bắn 20 request "Hi" trong 3 giây. Mỗi request chỉ
tốn khoảng 0,00004 USD — mình đo được 10 request thật chỉ hết 0,00054 USD —
nên ngân sách còn nguyên và cost guard không có cớ gì để chặn. Nhưng 20
request đồng thời chiếm hết worker của uvicorn và làm chậm mọi user khác, nên
rate limit phải chặn từ request thứ 11 bằng 429.

Hai lớp trả lời hai câu hỏi khác nhau ("gọi có quá nhanh không?" và "đã tiêu
hết tiền chưa?") nên phải có cả hai; bỏ lớp nào cũng để hở đúng phần lớp kia
không nhìn thấy.

---

### Câu 8 — /health khác /ready (CP4)

Nếu gộp hai endpoint làm một và cho nó kiểm tra Redis, chuyện gì xảy ra với cụm
3 container khi Redis mất kết nối 30 giây? Trả lời theo đúng thứ tự sự kiện.

Giả sử `/health` (endpoint mà orchestrator dùng làm **liveness** probe) có gọi
`store.ping()`:

1. **t = 0s** — Redis mất kết nối. Cả 3 container đều trỏ tới *cùng một*
   Redis nên `ping()` trả `False` ở cả ba, cùng lúc. Đây là điểm mấu chốt:
   chúng hỏng vì cùng một nguyên nhân bên ngoài, không phải vì bản thân
   container nào có vấn đề.
2. **t ≈ 0–30s** — Liveness probe gọi `/health`, nhận 503 ở cả 3 container.
   Bộ đếm `retries` của cả ba bắt đầu chạy song song.
3. **t ≈ 30–60s** — Đủ số lần thất bại liên tiếp (ví dụ `--retries=3`), cả 3
   container bị đánh dấu unhealthy **đồng thời**.
4. **Orchestrator xử lý liveness thất bại bằng cách RESTART** — nó hiểu 503 ở
   đây là "process này hỏng, giết đi tạo lại". Cả 3 container bị giết cùng
   lúc. Mọi request đang xử lý dở bị cắt giữa chừng, user nhận 502.
5. **Không còn instance nào phục vụ.** Trước bước này hệ thống chỉ "không lưu
   được lịch sử"; sau bước này nó chết hẳn. Một sự cố cục bộ vừa biến thành
   downtime toàn phần — do chính cơ chế tự phục hồi gây ra.
6. **t ≈ 30s** — Redis quay lại, nhưng 3 container vẫn đang khởi động. Nếu
   chúng lên trước khi Redis kịp hồi, probe lại đỏ và vòng restart lặp lại
   (CrashLoopBackOff), mỗi lần orchestrator lại chờ lâu hơn. Thời gian phục
   hồi thật kéo dài hơn nhiều so với 30 giây sự cố gốc.
7. **Khi cả cụm cùng lên lại**, toàn bộ traffic đang dồn ứ đổ vào các container
   vừa khởi động, chưa warm-up → dễ sập tiếp lần hai.

**Khi tách đúng như bài làm của mình:** `/health` không nhận `Depends` nào,
không chạm Redis → luôn 200 → không container nào bị restart. `/ready` gọi
`store.ping()` → trả 503 → load balancer **ngừng gửi** request mới vào (nhưng
không giết process). Đến giây thứ 30, Redis lên lại, `/ready` xanh trở lại,
LB đưa cả 3 container về vòng xoay ngay lập tức, không mất một giây khởi động
nào. Sự cố 30 giây đúng là 30 giây, không hơn.

---

### Câu 9 — Stateless (CP4)

Chạy `docker compose up --scale agent=3` rồi gọi `/ask` nhiều lần với cùng một
`X-User-Id`. Quan sát `history_length` trong response. Nếu lịch sử được lưu
trong một dict Python thay vì Redis, bạn sẽ thấy con số đó thay đổi thế nào?

Mình chạy `docker compose up -d --scale agent=3` (3 container agent + nginx
làm load balancer + redis) rồi gọi 5 lượt qua nginx với cùng `X-User-Id: sv01`:

```
lượt 1 → history_length = 0
lượt 2 → history_length = 2
lượt 3 → history_length = 4
lượt 4 → history_length = 6
lượt 5 → history_length = 8
```

Tăng đều 2 đơn vị mỗi lượt (một message `user` + một message `assistant`).
Mà request thì rõ ràng có đi qua nhiều container khác nhau — đếm log
`ask_completed` của 15 request sau đó cho thấy nginx chia round-robin
**4 / 5 / 6** cho ba container. Nghĩa là lượt 2 gần như chắc chắn rơi vào một
container khác lượt 1, nhưng nó vẫn "nhớ" được lượt 1, vì lịch sử nằm ở key
`history:sv01` trong Redis chứ không nằm trong RAM của container nào.

**Nếu lưu trong một dict Python:** mỗi container có một dict riêng, không
container nào biết về container khác. Với nginx chia round-robin cho 3
container (lượt 1→A, 2→B, 3→C, 4→A, 5→B), con số sẽ là:

```
lượt 1 (A) → 0     A chưa từng thấy sv01
lượt 2 (B) → 0     B cũng chưa từng thấy sv01
lượt 3 (C) → 0     C cũng vậy
lượt 4 (A) → 2     A nhớ đúng 1 lượt mà chính nó phục vụ
lượt 5 (B) → 2
```

`0, 0, 0, 2, 2` thay vì `0, 2, 4, 6, 8`. Với người dùng, agent trả lời như
người mất trí nhớ ngẫu nhiên: có lúc nhớ ngữ cảnh, có lúc quên sạch, không
theo quy luật nào — và bug này *không bao giờ tái hiện* trên máy dev vì ở đó
chỉ có một instance. Thêm hai hệ quả nữa: container bị restart (deploy, vá
lỗi, dời máy) là mất toàn bộ lịch sử; và rate limit cũng như cost guard sẽ bị
chia ba — hạn mức 10/phút thành 30/phút thật sự, vì mỗi container đếm riêng.

Vì vậy stateless không phải một lựa chọn kiến trúc "cho đẹp": nó là điều kiện
để scale ngang được.

---

### Câu 10 — Deploy thật (CP5)

Ghi lại **một** lỗi bạn gặp khi deploy lên cloud (build fail, health check
timeout, sai REDIS_URL, app không đọc `$PORT`...): thông báo lỗi là gì, bạn
tìm ra nguyên nhân bằng cách nào, và sửa ra sao?

Lỗi: **health check timeout** trên Railway, mà nguyên nhân thật lại là app
không đọc được `$PORT`.

**Triệu chứng.** Deploy lên Railway (project `confident-truth`, build từ
Dockerfile), build chạy trót lọt tới tận `image push` rồi hỏng ở bước cuối:

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

**Tìm nguyên nhân.** Điều đầu tiên là tách "build hỏng" khỏi "chạy hỏng", vì
hai loại lỗi này sửa ở hai chỗ khác nhau. Mình đọc log build trước:

```bash
railway logs --build 36556495-ca85-4bd9-aaf4-30e9d019420f
```

Log build chạy hết cả 6 layer của stage `runtime` rồi `exporting to docker
image format` → `image push`. Không có lỗi. Vậy image build ra được, vấn đề
nằm ở lúc chạy. Đổi sang log runtime:

```bash
railway logs --deployment 36556495-ca85-4bd9-aaf4-30e9d019420f
```

Và nó hiện ra ngay, lặp lại 4 lần liền:

```
Starting Container
Usage: uvicorn [OPTIONS] APP
Try 'uvicorn --help' for help.

Error: Invalid value for '--port': '$PORT' is not a valid integer.
Stopping Container
```

Chuỗi `'$PORT'` nằm trong dấu nháy của thông báo lỗi là chi tiết quyết định:
uvicorn nhận được đúng **6 ký tự `$PORT`** chứ không phải một con số. Nghĩa là
không ai khai triển biến này cả.

Chỗ khó hiểu lúc đó: `CMD` trong Dockerfile mình viết đúng rồi mà —

```dockerfile
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

Có `sh -c` nên `${PORT:-8000}` chắc chắn được khai triển. Nhưng đối chiếu lại
thông báo lỗi thì lệnh đang chạy lại là `--port $PORT`, không phải
`--port ${PORT:-8000}`. Hai lệnh khác nhau → lệnh đang chạy **không phải** CMD
của Dockerfile. Mở `railway.toml` thì thấy thủ phạm:

```toml
[deploy]
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
```

Hai điều cộng lại thành lỗi: (1) `startCommand` trong `railway.toml` **ghi đè**
`CMD` của image, nên `CMD` mình viết cẩn thận không hề được dùng; (2) Railway
chạy `startCommand` theo dạng exec, **không qua shell**, mà khai triển biến
`$PORT` vốn là việc của shell — không có shell thì `$PORT` chỉ là văn bản
thường được truyền thẳng làm tham số.

**Sửa.** Tự gọi shell trong chính `startCommand`, và giữ giá trị dự phòng để
lệnh vẫn chạy được cả khi platform chưa gán `PORT`:

```toml
# trước — hỏng
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT"

# sau — chạy được
startCommand = "sh -c 'uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}'"
```

Deploy lại, service lên `● Online` và health check qua ngay:

```
GET /health → HTTP/2 200  {"status":"ok","service":"day12-agent","version":"1.0.0"}
GET /ready  → HTTP/2 200  {"status":"ready","redis":true}
```

**Hai điều rút ra.**

Thứ nhất, *"chạy được ở máy"* và *"chạy được trên cloud"* có thể hỏng ở đúng
chỗ mình tưởng là an toàn nhất. `docker compose up` ở máy chạy `CMD` của
Dockerfile nên không bao giờ lộ lỗi này; chỉ trên Railway — nơi có
`startCommand` đè lên — nó mới xuất hiện. Cấu hình riêng của từng platform là
một bề mặt lỗi mà test ở máy không chạm tới được.

Thứ hai, "health check timeout" gần như không bao giờ là lỗi của health check.
Nó chỉ nói *"không ai trả lời cổng đó"*, còn lý do thật nằm trong log runtime.
Nếu lúc đó mình đi tăng `healthcheckTimeout` từ 30s lên 120s cho "chắc" thì chỉ
đổi được thời gian chờ trước khi nhận cùng một thất bại. Thứ tự đọc log —
build trước, runtime sau — là thứ cắt được nửa số khả năng ngay từ bước đầu.

Một điểm nữa mình sửa cùng lúc: project khi đó chưa có Redis và service chưa
được set biến môi trường nào. Đã tạo Redis bằng `railway add --database redis`,
trỏ `REDIS_URL` sang tham chiếu `${{Redis.REDIS_URL}}` thay vì dán URL cứng (để
Railway đổi endpoint thì mình không phải sửa lại), và set `AGENT_API_KEY` bằng
`railway variables --set-from-stdin` để giá trị không đi qua tham số dòng lệnh
— tham số dòng lệnh bị lưu vào shell history và hiện ra trong `ps`.
