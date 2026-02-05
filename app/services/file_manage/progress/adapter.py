from PyQt5.QtCore import QObject, pyqtSignal
import threading
from typing import Callable

from app.services.file_manage.progress.progress import ProgressReporter, make_scp_progress_adapter


class ProgressAdapter(QObject):
    '''进度适配器，将底层传输进度转换为 Qt 信号。'''

    progress_sig = pyqtSignal(str, str, int, str)

    def __init__(self, path: str, parent=None, interval_seconds: float = 0.5):
        """初始化进度适配器，设置路径和线程锁。"""
        # 1. 调用父类初始化
        super().__init__(parent)
        self.path = path
        # 2. 创建实际的进度汇报逻辑对象，默认0.5秒更新一次
        self.reporter = ProgressReporter(interval_seconds=interval_seconds)
        # 3. 初始化线程锁，确保并发安全
        self.lock = threading.Lock()
        self._cancelled = False

    def progress(self, transferred: int, total: int):
        """线程安全的核心进度更新方法，由工作线程调用。"""
        try:
            # 1. 加锁更新内部状态
            with self.lock:
                # 计算进度百分比和速度
                pct, speed, emit = self.reporter.update(int(transferred or 0), int(total or 0))

            # 2. 判断是否需要发射信号（节流且未取消）
            if emit and not self._cancelled:
                # 仅发回最小信息，交给主线程的槽执行具体的 model 更新
                try:
                    # 3. 发射信号到主线程
                    # 使用 getattr 动态调用 emit，避免某些静态分析器对 pyqtSignal.emit 的误报
                    getattr(self.progress_sig, 'emit')(self.path, "下载中", int(pct), speed)
                except Exception:
                    # 吞掉槽触发的异常，避免影响传输回调
                    pass
        except Exception:
            # 4. 忽略回调内部异常，确保不会中断底层传输库
            return

    def make_scp_callback(self) -> Callable[[str, int, int], None]:
        """生成适用于 scp 库的回调函数。"""
        # 1. 返回适配后的 scp 回调
        return make_scp_progress_adapter(self.progress)

    def cancel(self):
        """标记该传输已被取消。"""
        # 1. 设置取消标志，停止后续信号发射
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
                # 1. 判断并处理 SFTP 回调：(transferred, total)
                if len(args) == 2:
                    transferred, total = args
                    self.progress(int(transferred or 0), int(total or 0))
                # 2. 判断并处理 SCP 回调：(filename, size, sent)
                elif len(args) >= 3:
                    # 支持 bytes 或 str 的 filename
                    sent = args[2]
                    size = args[1]
                    self.progress(int(sent or 0), int(size or 0))
                else:
                    # 3. 忽略未知签名
                    return
            except Exception:
                # 4. 吞掉异常
                return

        return _unified
