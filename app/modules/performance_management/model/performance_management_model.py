import time
from dataclasses import dataclass, field
from typing import List, Optional

from app.core.base_model import BaseModel


@dataclass
class ProcessInfo:
    """单个进程信息模型。"""
    user: str
    pid: int
    cpu_percent: float
    mem_percent: float
    virt: int  # KB
    res: int   # KB
    command: str
    group_name: Optional[str] = None


@dataclass
class ProcessGroupStat:
    """进程分组统计信息。"""
    name: str
    total_cpu_percent: float = 0.0
    total_mem_percent: float = 0.0
    process_count: int = 0


class PerformanceModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        # 历史采样数据列表: (timestamp, cpu, mem, mem_bw)
        self.samples: list[tuple[float, float, float, float]] = []
        self.max_points: int = 120
        self.last_error: str | None = None

        # 进程/分组相关数据
        self.process_list: List[ProcessInfo] = []
        self.group_stats: List[ProcessGroupStat] = []
        self.selected_group_name: Optional[str] = None
        self.search_text: str = ""

        # 兼容旧接口的简单进程列表
        self.processes = []
        self.update_processes()

    # ============ 性能曲线相关 ============
    def append_sample(self, cpu: float, mem: float, mem_bw: float, ts: float | None = None):
        """追加一个性能采样点，并裁剪到 max_points。"""
        ts = ts or time.time()
        self.samples.append((ts, cpu, mem, mem_bw))
        if len(self.samples) > self.max_points:
            self.samples = self.samples[-self.max_points:]
        self.dataChanged.emit()

    def clear_samples(self):
        """清空所有采样点。"""
        self.samples.clear()
        self.dataChanged.emit()

    def set_error(self, msg: str | None):
        """记录最近错误信息，用于 UI 状态显示。"""
        self.last_error = msg
        self.dataChanged.emit()

    # ============ 进程 / 分组相关 ============
    def set_process_list(self, processes: List[ProcessInfo]):
        """设置最新的进程列表并根据当前分组规则统计。"""
        self.process_list = processes
        self._recalculate_group_stats()
        self.dataChanged.emit()

    def _recalculate_group_stats(self):
        """根据当前 process_list 重新汇总 group_stats。

        目前简单按 group_name 聚合；后续可接入自定义分组规则。
        """
        stats_map: dict[str, ProcessGroupStat] = {}
        for p in self.process_list:
            group = p.group_name or "Others"
            if group not in stats_map:
                stats_map[group] = ProcessGroupStat(name=group)
            gs = stats_map[group]
            gs.total_cpu_percent += p.cpu_percent
            gs.total_mem_percent += p.mem_percent
            gs.process_count += 1

        self.group_stats = list(stats_map.values())

    def set_selected_group(self, name: Optional[str]):
        self.selected_group_name = name
        self.dataChanged.emit()

    def set_search_text(self, text: str):
        self.search_text = text or ""
        self.dataChanged.emit()

    def get_filtered_processes(self) -> List[ProcessInfo]:
        """根据选中分组和搜索条件返回过滤后的进程列表。"""
        result = self.process_list

        if self.selected_group_name:
            result = [p for p in result if (p.group_name or "Others") == self.selected_group_name]

        text = self.search_text.strip()
        if text:
            lt = text.lower()
            filtered: List[ProcessInfo] = []
            for p in result:
                if (
                    lt in p.user.lower()
                    or lt in str(p.pid)
                    or lt in p.command.lower()
                    or (p.group_name and lt in p.group_name.lower())
                ):
                    filtered.append(p)
            result = filtered

        return result

    def update_processes(self):
        """示例进程数据，后续可接入真实后台。

        仅用于兼容旧的 populate 接口，不再在新 UI 中使用。
        """
        self.processes = [
            ["diagnostic_service", "1254", "12.5", "128", "root"],
            ["memory_manager", "892", "8.3", "96", "system"],
        ]
        self.dataChanged.emit()
