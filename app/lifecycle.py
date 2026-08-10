"""CP4 — Graceful shutdown.

Khi bạn deploy phiên bản mới, orchestrator (Docker, Railway, Cloud Run, K8s)
gửi **SIGTERM** rồi đợi vài chục giây trước khi SIGKILL. Nếu app bỏ qua tín
hiệu đó, mọi request đang xử lý dở bị cắt giữa chừng — user thấy lỗi 502 mỗi
lần bạn deploy.

Ứng xử đúng: nhận SIGTERM → báo "tôi sắp tắt" qua health check để load
balancer ngừng đẩy traffic mới vào → xử lý nốt request đang chạy → thoát.
"""

from __future__ import annotations

import signal


class Lifecycle:
    """Giữ trạng thái vòng đời của process."""

    def __init__(self) -> None:
        self.shutting_down = False
        # Handler đã được đăng ký trước ta (của uvicorn) — xem install()
        self._previous: dict = {}

    def request_shutdown(self, signum=None, frame=None) -> None:
        """Signal handler: đánh dấu process đang tắt dần.

        Chữ ký ``(signum, frame)`` là bắt buộc vì Python gọi handler với 2
        tham số này. Không làm gì nặng ở đây (không gọi mạng, không ghi file)
        — handler chạy xen giữa bytecode.
        """
        # Chỉ bật cờ. /health thấy cờ này sẽ trả 503 → load balancer rút
        # instance ra khỏi vòng xoay → uvicorn xử lý nốt request đang chạy.
        self.shutting_down = True

        # Nhường lại cho handler cũ — quan trọng hơn vẻ ngoài của nó. Mỗi tín
        # hiệu chỉ có MỘT handler: đăng ký handler của mình là ghi đè handler
        # của uvicorn, thứ chịu trách nhiệm thật sự cho việc dừng server.
        # Quên gọi lại thì app bật cờ "đang tắt" rồi chạy tiếp mãi mãi, cho
        # tới khi orchestrator hết kiên nhẫn và SIGKILL.
        previous = self._previous.get(signum)
        if callable(previous):
            previous(signum, frame)

    def install(self) -> None:
        """Đăng ký handler cho SIGTERM và SIGINT, nhớ lại handler cũ.

        SIGTERM: orchestrator yêu cầu tắt. SIGINT: bạn bấm Ctrl+C.
        """
        for sig in (signal.SIGTERM, signal.SIGINT):
            self._previous[sig] = signal.getsignal(sig)  # nhớ handler cũ
            signal.signal(sig, self.request_shutdown)  # rồi mới ghi đè


# Một instance dùng chung cho cả app
lifecycle = Lifecycle()
