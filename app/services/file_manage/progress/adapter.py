from PyQt5.QtCore import QObject, pyqtSignal
import threading
from typing import Callable

from app.services.file_manage.progress.progress import ProgressReporter, make_scp_progress_adapter


class ProgressAdapter(QObject):
    """
    说明：
    - 目的：统一处理底层传输库（SFTP / SCP 等）的进度回调，将高频的低级回调
      转换为节流后的、适合 UI 更新的事件（百分比和速度），并通过 Qt 信号
      安全地从工作线程传回主线程执行 Model/View 更新。
    - 线程模型：进度回调通常发生在后台线程（或由底层库的 IO 线程触发），
      因此 adapter.progress 必须线程安全。这里使用 `threading.Lock` 保护
      对 `ProgressReporter` 状态的访问（reporter 内部维护 last_time/last_bytes）。
    - 导出方法：
        - progress(transferred:int, total:int)：供后台线程频繁调用。
        - make_scp_callback() -> Callable[[str,int,int], None]：返回一个可直接传给
          scp.SCPClient(progress=...) 的回调，内部使用已有的 `make_scp_progress_adapter`。
        - cancel()：可选地标记该 adapter 已取消，停止后续信号发射。
    - 信号：
        - progress_sig(path:str, status:str, percent:int, speed:str)
          信号在主线程执行槽（queued connection），建议将其连接到
          model.update_file_status 之类的线程安全槽。

    使用示例：
        adapter = ProgressAdapter(path)
        adapter.progress_sig.connect(model.update_file_status)
        # 对于 SFTP：直接把 adapter.progress 作为 callback
        sftp.get(remote, local, callback=adapter.progress)
        # 对于 SCP：使用 adapter.make_scp_callback() 作为 scp 库的 progress 参数
        scp_client = SCPClient(transport, progress=adapter.make_scp_callback())

    注意事项：
    - 必须保证 adapter 在传输会话整个生命周期内保持引用，避免被 GC。
    - adapter 发射的信号应尽量包含最小必要数据，避免在主线程做大量计算。
    """

    progress_sig = pyqtSignal(str, str, int, str)

    def __init__(self, path: str, parent=None, interval_seconds: float = 0.5):
        super().__init__(parent)
        self.path = path
        self.reporter = ProgressReporter(interval_seconds=interval_seconds)
        self.lock = threading.Lock()
        self._cancelled = False

    def progress(self, transferred: int, total: int):
        """
        该方法可能被后台线程频繁调用。它只做最小工作：在锁内调用 reporter.update，
        然后在需要时通过 signal 把数据发回主线程。
        """
        try:
            with self.lock:
                pct, speed, emit = self.reporter.update(int(transferred or 0), int(total or 0))
            if emit and not self._cancelled:
                # 仅发回最小信息，交给主线程的槽执行具体的 model 更新
                try:
                    # 使用 getattr 动态调用 emit，避免某些静态分析器对 pyqtSignal.emit 的误报
                    getattr(self.progress_sig, 'emit')(self.path, "下载中", int(pct), speed)
                except Exception:
                    # 吞掉槽触发的异常，避免影响传输回调
                    pass
        except Exception:
            # 忽略回调内部异常，确保不会中断底层传输库
            return

    def make_scp_callback(self) -> Callable[[str, int, int], None]:
        """为 SCP 库返回一个适配回调 (filename, size, sent) -> calls progress(sent, size).

        该函数基于项目已有的 `make_scp_progress_adapter`，保持异常吞掉��行为以
        兼容底层 scp 实现。
        """
        return make_scp_progress_adapter(self.progress)

    def cancel(self):
        """标记为已取消，后续进度更新不会发射信号（仅停止 UI 更新）"""
        self._cancelled = True

    def make_unified_callback(self) -> Callable:
        """返回一个统一的回调函数，能兼容两种常见回调签名：

        - SFTP: callback(transferred: int, total: int)
        - SCP: callback(filename: str, size: int, sent: int)

        这个 wrapper 会根据参数数量分发到 adapter.progress，确保 controller 只需
        传入这个 callback 到 service（service 会把它传给 SFTP 或 SCP）。
        """

        def _unified(*args):
            try:
                # SFTP 回调： (transferred, total)
                if len(args) == 2:
                    transferred, total = args
                    self.progress(int(transferred or 0), int(total or 0))
                # SCP 回调： (filename, size, sent)
                elif len(args) >= 3:
                    # 支持 bytes 或 str 的 filename
                    sent = args[2]
                    size = args[1]
                    self.progress(int(sent or 0), int(size or 0))
                else:
                    # 不认识的签名，忽略
                    return
            except Exception:
                # 吞掉所有异常，兼容底层库的回调契约
                return

        return _unified
