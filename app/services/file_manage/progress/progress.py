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
        """初始化进度汇报器，配置节流参数。"""
        # 1. 设置节流间隔（秒）
        self.interval = float(interval_seconds)
        # 2. 初始化上次发射时间（0 表示从未发射）
        self.last_time = 0.0
        # 3. 初始化上次记录的已传输字节数
        self.last_bytes = 0
        # 4. 可扩展的完成标志
        self.finished = False

    def update(self, transferred: int, total: int) -> Tuple[int, str, bool]:
        """计算进度和速度，根据节流策略决定是否触发更新。"""
        # 1. 获取当前时间
        now = time.time()
        # 2. 保护性转型，确保传输量为非负整数
        transferred = int(max(0, transferred))
        total = int(max(0, total)) if total is not None else 0

        # 3. 计算进度百分比（处理 total=0 的情况）
        if total > 0:
            # 计算百分比
            percent = int(transferred * 100 / total)
        else:
            # 无法计算百分比时，默认为 0
            percent = 0

        # 4. 初始化速度计算变量
        dt = now - self.last_time if self.last_time else None
        speed_str = "0 B/s"
        emit = False

        # 5. 计算瞬时速度（如果非首次调用）
        if self.last_time and dt and dt > 0:
            delta_bytes = transferred - self.last_bytes
            # 避免回退导致负数
            if delta_bytes < 0:
                delta_bytes = 0
            speed = delta_bytes / dt

            # 6. 格式化速度为易读单位
            if speed < 1024:
                speed_str = f"{int(speed)} B/s"
            elif speed < 1024 * 1024:
                speed_str = f"{speed/1024:.1f} KB/s"
            else:
                speed_str = f"{speed/1024/1024:.1f} MB/s"

        # 7. 节流判断：首次、超时或完成时触发
        if self.last_time == 0 or (now - self.last_time) >= self.interval or percent == 100:
            emit = True
            self.last_time = now
            self.last_bytes = transferred
        # 8. 返回计算结果：当前的进度百分比，速度字符串，是否触发更新
        return percent, speed_str, emit


def make_scp_progress_adapter(cb: Callable[[int, int], None]) -> Callable[[str, int, int], None]:
    """创建 SCP 协议的回调适配器，屏蔽参数差异。"""

    def adapter(filename: str, size: int, sent: int):
        # 1. 尝试调用目标回调
        try:
            # 忽略 filename，仅传递已发送量和总量
            cb(int(sent), int(size))
        except Exception:
            # 2. 吞掉异常以保护底层 SCP 流程
            return

    return adapter
