"""
进度工具模块（用于传输协调器与 UI 控制器）

本模块包含一个轻量的有状态类 `ProgressReporter`，用于把底层的字节数
更新（transferred/total）转换为 UI 友好的三元组：(percent, speed_str, emit)，
其中 `emit` 表示是否应该触发一次 UI 更新（用于节流）。

同时提供 `make_scp_progress_adapter`，用于把 scp 风格的回调签名
(filename, size, sent) 转换为统一的 (transferred, total) 形式。

设计要点：将节流与速度计算与传输实现解耦，便于单元测试与复用。
"""

from typing import Callable, Tuple
import time


class ProgressReporter:
    """带时间节流的进度汇报器。

    使用示例：
        p = ProgressReporter(interval_seconds=0.5)
        percent, speed_str, emit = p.update(transferred, total)
        if emit:
            # 将进度发送到 UI

    行为要点：
    - 记录上次发射时间与字节数，用于计算瞬时速度和节流判断。
    - 仅在首次、距离上次 >= interval，或 percent 达到 100 时返回 emit=True。
    - 速度字符串使用简单单位（B/s, KB/s, MB/s）。
    """

    def __init__(self, interval_seconds: float = 0.5):
        # 节流间隔（秒）
        self.interval = float(interval_seconds)
        # 上次发射时间（时间戳），初始为 0 表示尚未发射过
        self.last_time = 0.0
        # 上次记录的已传输字节数
        self.last_bytes = 0
        # 可扩展的完成标志（当前未强制使用）
        self.finished = False

    def update(self, transferred: int, total: int) -> Tuple[int, str, bool]:
        """更新内部计数并决定是否触发一次 UI 更新。

        参数：
            transferred: 已传输字节数
            total: 总字节数（当总字节数未知时，可能为 0）

        返回： (percent:int, speed_str:str, emit:bool)
        - percent: 进度百分比（0-100）。注意：当 total 为 0（未知）时，返回 0 而不是 100，
                   以避免误判为已完成。
        - speed_str: 人类可读的速度字符串
        - emit: 是否应该发射一次更新（基于节流策略）
        """
        now = time.time()
        # 保护性转型，确保为非负整数
        transferred = int(max(0, transferred))
        total = int(max(0, total)) if total is not None else 0

        # 修正逻辑：若 total == 0（未知总量），不要把 percent 视为 100（已完成），而应视为未知并返回 0。
        if total > 0:
            percent = int(transferred * 100 / total)
        else:
            percent = 0

        # 计算瞬时速度（基于上次采样）
        dt = now - self.last_time if self.last_time else None
        speed_str = "0 B/s"
        emit = False

        if self.last_time and dt and dt > 0:
            delta_bytes = transferred - self.last_bytes
            if delta_bytes < 0:
                delta_bytes = 0
            speed = delta_bytes / dt
            # 格式化为合适单位
            if speed < 1024:
                speed_str = f"{int(speed)} B/s"
            elif speed < 1024 * 1024:
                speed_str = f"{speed/1024:.1f} KB/s"
            else:
                speed_str = f"{speed/1024/1024:.1f} MB/s"

        # 节流判断：首次发射、或超过间隔、或进度达到 100 时发射
        if self.last_time == 0 or (now - self.last_time) >= self.interval or percent == 100:
            emit = True
            self.last_time = now
            self.last_bytes = transferred

        return percent, speed_str, emit


def make_scp_progress_adapter(cb: Callable[[int, int], None]) -> Callable[[str, int, int], None]:
    """把 scp 风格的回调 (filename, size, sent) 适配为 cb(transferred, total)。

    说明：
    - scp 库通常调用回调签名为 (filename, size, sent)，这里忽略 filename，
      将 sent/size 转为 int 并调用 cb(sent, size)。
    - 为避免破坏底层 scp 的内部行为，若回调抛异常则吞掉异常。
    """

    def adapter(filename: str, size: int, sent: int):
        try:
            cb(int(sent), int(size))
        except Exception:
            # 吞掉回调中的异常，避免影响 scp 内部逻辑
            return

    return adapter
