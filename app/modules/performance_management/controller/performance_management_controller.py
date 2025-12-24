from app.core.base_controller import BaseController
from app.modules.performance_management.model.performance_management_model import (
    PerformanceModel,
    ProcessInfo,
)
from app.modules.performance_management.view.performance_management_view import PerformanceView
from app.services.device_manage.performance_service import PerformanceService, PerformanceFetchError
from app.core.dependency_injection import di_container
from app.services.device_manage.device_service import DeviceService

from PyQt5 import QtCore
import time
import csv
import datetime
import os


class PerformanceController(BaseController):
    def __init__(self, parent=None):
        self.model = PerformanceModel(parent)
        # 不把 Qt parent 传给 view，避免作为主窗口子窗口叠在布局外
        self.view = PerformanceView(self.model)

        # 获取 DeviceService 实例
        self._device_service = di_container.resolve(DeviceService)
        if not self._device_service:
            # 如果容器中没有，尝试创建一个新的（虽然通常应该有）
            self._device_service = DeviceService()
            di_container.register_singleton(DeviceService, self._device_service)

        # 初始化 PerformanceService
        self._ssh_perf = PerformanceService(device_service=self._device_service)

        # 定时器按下拉周期采集数据 (Metrics)
        self._timer = QtCore.QTimer(self.view)
        self._timer.timeout.connect(self._on_timer_tick)

        # 独立的进程采集定时器
        self._process_timer = QtCore.QTimer(self.view)
        self._process_timer.timeout.connect(self._on_process_timer_tick)

        self._start_time = 0
        self._iteration_count = 0

        super().__init__(self.model, self.view, parent)
        self._bind_view_signals()
        self.on_model_changed()

    def _bind_view_signals(self):
        self.view.start_btn.clicked.connect(self._on_start_clicked)
        self.view.pause_btn.clicked.connect(self._on_pause_clicked)
        self.view.reset_btn.clicked.connect(self._on_reset_clicked)
        self.view.export_btn.clicked.connect(self._on_export_clicked)
        self.view.cycle_combo.currentTextChanged.connect(self._on_cycle_changed)

        # 进程查询相关交互
        self.view.search_edit.textChanged.connect(self._on_search_text_changed)
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

    def _current_process_interval_ms(self) -> int:
        # text = self.view.process_cycle_combo.currentText()
        # if text.endswith("s"):
        #     try:
        #         sec = int(text[:-1])
        #         return max(1, sec) * 1000
        #     except ValueError:
        #         pass
        return 5000  # 默认 5s

    def _on_start_clicked(self):
        # 检查是否有已连接的 SSH 设备
        ssh_client = self._device_service.get_ssh_client()
        #如果ssh_client等于None， 提示未连接
        if ssh_client is None or not ssh_client.is_connected():
            self.view.set_status("未检测到已连接的 SSH 设备，请先在设备管理中连接设备。", "error")
            return

        # 启动 Metrics 定时器
        interval = self._current_interval_ms()
        self._timer.setInterval(interval)
        self._timer.start()

        # 启动 Process 定时器
        proc_interval = self._current_process_interval_ms()
        self._process_timer.setInterval(proc_interval)
        self._process_timer.start()

        self._start_time = time.time()
        self._iteration_count = 0

        self.view.set_status(f"监控已启动", "info")
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 监控已启动")

        # Update button states
        self.view.start_btn.setEnabled(False)
        self.view.pause_btn.setEnabled(True)
        self.view.reset_btn.setEnabled(True)
        self.view.cycle_combo.setEnabled(False)
        # self.view.process_cycle_combo.setEnabled(False)

    def _on_pause_clicked(self):
        self._timer.stop()
        self._process_timer.stop()
        self.view.set_status("监控已暂停", "warn")
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 监控已暂停")

        # Update button states
        self.view.start_btn.setEnabled(True)
        self.view.pause_btn.setEnabled(False)
        self.view.reset_btn.setEnabled(True)
        self.view.cycle_combo.setEnabled(True)
        # self.view.process_cycle_combo.setEnabled(True)

    def _on_reset_clicked(self):
        self._timer.stop()
        self._process_timer.stop()
        self.model.clear_samples()
        self.model.set_error(None)
        self.view.reset_chart()
        self.view.set_status("已重置", "info")
        self._iteration_count = 0
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 监控已重置")

        # Update button states
        self.view.start_btn.setEnabled(True)
        self.view.pause_btn.setEnabled(False)
        self.view.reset_btn.setEnabled(True) # Reset can be enabled or disabled, usually enabled to clear again
        self.view.cycle_combo.setEnabled(True)
        # self.view.process_cycle_combo.setEnabled(True)

    def _on_export_clicked(self):
        """导出性能数据到 Excel 文件，包含 Metrics 和 Processes 两个 Sheet。"""
        if not self.model.samples and not self.model.process_list:
            self.view.set_status("没有数据可导出", "warn")
            return

        filename = f"performance_data_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        abs_path = os.path.abspath(filename)

        try:
            import openpyxl
            wb = openpyxl.Workbook()

            # Sheet 1: Metrics
            ws_metrics = wb.active
            ws_metrics.title = "Metrics"
            ws_metrics.append(['Timestamp', 'CPU (%)', 'Memory (%)', 'Disk Usage (%)', 'Disk Read (KB)', 'Disk Write (KB)'])

            for sample in self.model.samples:
                if len(sample) == 6:
                    ts, cpu, mem, disk_usage, disk_read, disk_write = sample
                else:
                    ts = sample[0]
                    cpu = sample[1] if len(sample) > 1 else 0.0
                    mem = sample[2] if len(sample) > 2 else 0.0
                    disk_usage = sample[3] if len(sample) > 3 else 0.0
                    disk_read = sample[4] if len(sample) > 4 else 0.0
                    disk_write = sample[5] if len(sample) > 5 else 0.0

                time_str = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                ws_metrics.append([time_str, cpu, mem, disk_usage, disk_read, disk_write])

            # Sheet 2: Processes (Current Snapshot)
            ws_processes = wb.create_sheet("Processes")
            ws_processes.append([
                "TYPE", "USER", "PID", "CPU%", "MEM%", "VSZ", "RSS", "TTY", "STAT", "START", "TIME", "CONTAINER", "PROCESS_NAME"
            ])

            for p in self.model.process_list:
                ws_processes.append([
                    p.type, p.user, p.pid, p.cpu_percent, p.mem_percent, p.vsz_kb, p.rss_kb,
                    p.tty, p.stat, p.start_time, p.cpu_time, p.container, p.process_name
                ])

            wb.save(filename)

            # Create a clickable link
            link = f'<a href="file:///{abs_path}">{abs_path}</a>'
            self.view.set_status(f"数据已导出到: {link}", "info")
        except ImportError:
             self.view.set_status("导出失败: 未安装 openpyxl 库", "error")
        except Exception as e:
            self.view.set_status(f"导出失败: {str(e)}", "error")

    def _on_cycle_changed(self, _text: str):
        if self._timer.isActive():
            self._timer.setInterval(self._current_interval_ms())

    # def _on_process_cycle_changed(self, _text: str):
    #     if self._process_timer.isActive():
    #         self._process_timer.setInterval(self._current_process_interval_ms())

    def _on_sort_changed(self, _text: str):
        """排序方式改变，立即刷新当前表格视图。"""
        self._refresh_process_view()

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
        """仅采集性能指标 (Metrics)。"""
        elapsed = time.time() - self._start_time
        if elapsed >= 60:
            self._on_pause_clicked()
            self.view.set_status("监控结束 (60s)", "info")
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 监控结束: 已达到60秒限制")
            return

        self._iteration_count += 1

        try:
            metrics = self._ssh_perf.fetch_metrics()
            # Print to console
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Metrics - CPU: {metrics.cpu:.1f}%, Mem: {metrics.mem:.1f}%")

        except PerformanceFetchError as exc:
            self.model.set_error(str(exc))
            self.view.set_status(str(exc), "error")
            return

        self.model.set_error(None)
        self.model.append_sample(metrics.cpu, metrics.mem, metrics.disk_usage, metrics.disk_read_kb, metrics.disk_write_kb)

        # Pass elapsed time as x_value
        self.view.update_chart(elapsed, metrics.cpu, metrics.mem, metrics.disk_usage, metrics.disk_read_kb, metrics.disk_write_kb, self.model.max_points)

    def _on_process_timer_tick(self):
        """仅采集进程列表。"""
        elapsed = time.time() - self._start_time
        if elapsed >= 60:
            self._on_pause_clicked()
            self.view.set_status("监控结束 (60s)", "info")
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 监控结束: 已达到60秒限制")
            return

        try:
            # 获取所有进程，不限制数量，因为 ps aux 返回全部
            processes = self._ssh_perf.fetch_processes()
        except PerformanceFetchError as exc:
            print(f"进程采集失败: {exc}")
            return

        # 将 ProcessSample 转为模型所需的 ProcessInfo
        process_infos = [
            ProcessInfo(
                type=p.type,
                user=p.user,
                pid=p.pid,
                cpu_percent=p.cpu_percent,
                mem_percent=p.mem_percent,
                vsz_kb=p.vsz_kb,
                rss_kb=p.rss_kb,
                tty=p.tty,
                stat=p.stat,
                start_time=p.start_time,
                cpu_time=p.cpu_time,
                container=p.container,
                process_name=p.process_name,
                full_command=p.full_command,
                group_name=p.group_name,
            )
            for p in processes
        ]
        self.model.set_process_list(process_infos)
        self._refresh_process_view()


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
