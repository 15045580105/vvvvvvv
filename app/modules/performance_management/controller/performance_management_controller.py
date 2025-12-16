from app.core.base_controller import BaseController
from app.modules.performance_management.model.performance_management_model import (
    PerformanceModel,
    ProcessInfo,
)
from app.modules.performance_management.view.performance_management_view import PerformanceView
from app.services.device_manage.performance_service import PerformanceService, PerformanceFetchError

from PyQt5 import QtCore


class PerformanceController(BaseController):
    def __init__(self, parent=None):
        self.model = PerformanceModel(parent)
        # 不把 Qt parent 传给 view，避免作为主窗口子窗口叠在布局外
        self.view = PerformanceView(self.model)
        self._ssh_perf = PerformanceService()

        # 定时器按下拉周期采集数据
        self._timer = QtCore.QTimer(self.view)
        self._timer.timeout.connect(self._on_timer_tick)

        super().__init__(self.model, self.view, parent)
        self._bind_view_signals()
        self.on_model_changed()

    def _bind_view_signals(self):
        self.view.start_btn.clicked.connect(self._on_start_clicked)
        self.view.pause_btn.clicked.connect(self._on_pause_clicked)
        self.view.reset_btn.clicked.connect(self._on_reset_clicked)
        self.view.cycle_combo.currentTextChanged.connect(self._on_cycle_changed)

        # 进程查询相关交互
        self.view.search_edit.textChanged.connect(self._on_search_text_changed)
        # Set Group Name 按钮目前仅预留接口
        self.view.set_group_btn.clicked.connect(self._on_set_group_clicked)

    def _current_interval_ms(self) -> int:
        text = self.view.cycle_combo.currentText()
        if text.endswith("秒"):
            try:
                sec = int(text[:-1])
                return max(1, sec) * 1000
            except ValueError:
                pass
        return 2000  # 默认 2s

    def _on_start_clicked(self):
        interval = self._current_interval_ms()
        self._timer.setInterval(interval)
        self._timer.start()
        self.view.set_status("监控已启动", "info")

    def _on_pause_clicked(self):
        self._timer.stop()
        self.view.set_status("监控已暂停", "warn")

    def _on_reset_clicked(self):
        self._timer.stop()
        self.model.clear_samples()
        self.model.set_error(None)
        self.view.reset_chart()
        self.view.set_status("已重置", "info")

    def _on_cycle_changed(self, _text: str):
        if self._timer.isActive():
            self._timer.setInterval(self._current_interval_ms())

    def _on_search_text_changed(self, text: str):
        """搜索框变化时更新模型并刷新表格。"""
        self.model.set_search_text(text)
        self._refresh_process_view()

    def _on_set_group_clicked(self):
        """Set Group Name 按钮点击的占位处理。

        后续可在此弹出分组规则配置对话框，并根据规则更新各进程的 group_name。
        """
        # 当前先不实现复杂对话框，仅作为占位，避免界面无响应
        self.view.set_status("分组配置对话框暂未实现", "warn")

    def _on_timer_tick(self):
        try:
            metrics = self._ssh_perf.fetch_metrics()
            processes = self._ssh_perf.fetch_processes(limit=50)
        except PerformanceFetchError as exc:
            self.model.set_error(str(exc))
            self.view.set_status(str(exc), "error")
            return

        self.model.set_error(None)
        self.model.append_sample(metrics.cpu, metrics.mem, metrics.mem_bw)
        self.view.update_chart(metrics.cpu, metrics.mem, metrics.mem_bw, self.model.max_points)

        # 将 ProcessSample 转为模型所需的 ProcessInfo
        process_infos = [
            ProcessInfo(
                user=p.user,
                pid=p.pid,
                cpu_percent=p.cpu_percent,
                mem_percent=p.mem_percent,
                virt=p.virt,
                res=p.res,
                command=p.command,
                group_name=p.group_name,
            )
            for p in processes
        ]
        self.model.set_process_list(process_infos)
        self._refresh_process_view()

    def configure_ssh_target(self, host: str, port: int, username: str, password: str | None = None, key_file: str | None = None):
        """供外部调用，配置性能服务所使用的 SSH 目标。"""
        self._ssh_perf.configure_target(host, port, username, password=password, key_file=key_file, eager_connect=True)

    def _refresh_process_view(self):
        """根据模型当前状态刷新 Group Info 图表和进程表格。"""
        # 更新分组统计到 Group Info 区域
        self.view.update_group_chart(self.model.group_stats)
        # 更新进程表格（包含搜索/分组过滤结果）
        filtered = self.model.get_filtered_processes()
        self.view.update_process_table(filtered)

    def on_model_changed(self):
        """模型变更时刷新进程视图。

        旧的简单表格填充接口保留为兼容，但现在主要通过 update_group_chart/update_process_table 更新。
        """
        self._refresh_process_view()
