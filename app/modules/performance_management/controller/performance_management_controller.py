import datetime
import logging
import queue
import time

from app.core.base_controller import BaseController
from app.core.dependency_injection import di_container
from app.modules.performance_management.controller.performance_workers import (
    DataCollectorThread,
    DataWriterThread,
    ProcessCollectorThread,
    ProcessWriterThread,
    ProcessUIUpdateThread,
    ExportWorker
)
from app.modules.performance_management.model.performance_management_model import (
    PerformanceModel,
)
from app.modules.performance_management.view.performance_management_view import PerformanceView
from app.services.device_manage.device_service import DeviceService
from app.services.device_manage.performance_service import PerformanceService

logger = logging.getLogger(__name__)


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

        # 数据队列，用于线程间通信
        self.data_queue = queue.Queue()
        self.process_data_queue = queue.Queue()
        self.process_file_queue = queue.Queue()
        self.process_ui_queue = queue.Queue()

        # 初始化线程
        self.collector_thread = None
        self.writer_thread = None
        self.process_collector_thread = None
        self.process_writer_thread = None
        self.process_ui_update_thread = None

        self._start_time = 0
        self._iteration_count = 0

        super().__init__(self.model, self.view, parent)
        self._bind_view_signals()
        self.on_model_changed()

    def _bind_view_signals(self):
        # Metrics Tab Signals
        self.view.metrics_start_btn.clicked.connect(self._on_metrics_start_clicked)
        self.view.metrics_stop_btn.clicked.connect(self._on_metrics_stop_clicked)
        self.view.metrics_export_btn.clicked.connect(self._on_metrics_export_clicked)
        self.view.metrics_cycle_combo.currentTextChanged.connect(self._on_metrics_cycle_changed)

        # Process Tab Signals
        self.view.process_start_btn.clicked.connect(self._on_process_start_clicked)
        self.view.process_stop_btn.clicked.connect(self._on_process_stop_clicked)
        self.view.process_export_btn.clicked.connect(self._on_process_export_clicked)
        self.view.process_cycle_combo.currentTextChanged.connect(self._on_process_cycle_changed)

        # Process Search & Group
        self.view.search_edit.textChanged.connect(self._on_search_text_changed)
        # self.view.set_group_btn.clicked.connect(self._on_set_group_clicked)

    def _current_metrics_interval_ms(self) -> int:
        text = self.view.metrics_cycle_combo.currentText()
        if text.endswith("s"):
            try:
                sec = int(text[:-1])
                return max(1, sec) * 1000
            except ValueError:
                pass
        return 2000

    def _current_process_interval_ms(self) -> int:
        text = self.view.process_cycle_combo.currentText()
        if text.endswith("s"):
            try:
                sec = int(text[:-1])
                return max(1, sec) * 1000
            except ValueError:
                pass
        return 5000

    # --- Metrics Handlers ---
    def _on_metrics_start_clicked(self):
        ssh_client = self._device_service.get_ssh_client()
        if ssh_client is None or not ssh_client.is_connected():
            self.view.set_metrics_status("未检测到已连接的 SSH 设备", "error")
            return

        # Clear chart before starting
        self.model.clear_samples()
        self.view.reset_chart()

        interval = self._current_metrics_interval_ms()

        if not self.collector_thread:
            self.collector_thread = DataCollectorThread(self._ssh_perf, interval)
            self.collector_thread.data_collected.connect(self._on_data_collected)
            self.collector_thread.error_occurred.connect(self._on_metrics_error)
            self.collector_thread.start()
        else:
            self.collector_thread.set_interval(interval)
            self.collector_thread.resume()

        if not self.writer_thread:
            self.writer_thread = DataWriterThread(self.data_queue)
            self.writer_thread.start()

        self._start_time = time.time()
        self._iteration_count = 0

        self.view.set_metrics_status("性能监控已启动", "info")
        self.view.metrics_start_btn.setEnabled(False)
        self.view.metrics_stop_btn.setEnabled(True)
        self.view.metrics_cycle_combo.setEnabled(False)

    def _on_metrics_stop_clicked(self):
        if self.collector_thread:
            self.collector_thread.pause()

        self.view.set_metrics_status("性能监控已结束", "warn")
        self.view.metrics_start_btn.setEnabled(True)
        self.view.metrics_stop_btn.setEnabled(False)
        self.view.metrics_cycle_combo.setEnabled(True)

    def _on_metrics_export_clicked(self):
        if not self.model.samples:
            self.view.set_metrics_status("没有性能数据可导出", "warn")
            return
        self._export_data(metrics_only=True)

    def _on_metrics_cycle_changed(self, _text: str):
        if self.collector_thread:
            self.collector_thread.set_interval(self._current_metrics_interval_ms())

    # --- Process Handlers ---
    def _on_process_start_clicked(self):
        ssh_client = self._device_service.get_ssh_client()
        if ssh_client is None or not ssh_client.is_connected():
            self.view.set_process_status("未检测到已连接的 SSH 设备", "error")
            return

        interval = self._current_process_interval_ms()

        if not self.process_collector_thread:
            self.process_collector_thread = ProcessCollectorThread(self._ssh_perf, interval)
            self.process_collector_thread.data_collected.connect(self._on_process_data_collected)
            self.process_collector_thread.error_occurred.connect(self._on_process_error)
            self.process_collector_thread.start()
        else:
            self.process_collector_thread.set_interval(interval)
            self.process_collector_thread.resume()

        if not self.process_writer_thread:
            self.process_writer_thread = ProcessWriterThread(self.process_data_queue)
            self.process_writer_thread.start()

        if not self.process_ui_update_thread:
            self.process_ui_update_thread = ProcessUIUpdateThread(self.process_ui_queue)
            self.process_ui_update_thread.data_processed.connect(self._update_process_view)
            self.process_ui_update_thread.start()

        self.view.set_process_status("进程监控已启动", "info")
        self.view.process_start_btn.setEnabled(False)
        self.view.process_stop_btn.setEnabled(True)
        self.view.process_cycle_combo.setEnabled(False)

    def _on_process_stop_clicked(self):
        if self.process_collector_thread:
            self.process_collector_thread.pause()

        self.view.set_process_status("进程监控已结束", "warn")
        self.view.process_start_btn.setEnabled(True)
        self.view.process_stop_btn.setEnabled(False)
        self.view.process_cycle_combo.setEnabled(True)

    def _on_process_cycle_changed(self, _text: str):
        if self.process_collector_thread:
            self.process_collector_thread.set_interval(self._current_process_interval_ms())

    def _on_process_export_clicked(self):
        if not self.model.process_list:
            self.view.set_process_status("没有进程数据可导出", "warn")
            return
        self._export_data(process_only=True)

    def _export_data(self, metrics_only=False, process_only=False):
        """
        启动导出线程。
        """
        worker = ExportWorker(metrics_only, process_only, metrics_count=len(self.model.samples), process_count=len(self.model.process_list))
        worker.status_updated.connect(self._on_export_status_updated)
        # Keep a reference to prevent GC
        self._export_worker = worker
        worker.finished.connect(lambda: setattr(self, '_export_worker', None))

        if metrics_only:
            self.view.set_metrics_status("正在导出性能数据...", "warn")
        elif process_only:
            self.view.set_process_status("正在导出进程数据...", "warn")

        worker.start()

    def _on_export_status_updated(self, type_, message, level):
        if type_ == "metrics":
            self.view.set_metrics_status(message, level)
        elif type_ == "process":
            self.view.set_process_status(message, level)

    def _on_search_text_changed(self, text: str):
        """搜索框变化时更新模型并刷新表格。"""
        self.model.set_search_text(text)
        self._refresh_process_view()


    def _on_data_collected(self, data):
        """处理采集到的数据 (在主线程中执行)"""
        # data is now a tuple: (request_time, metrics)

        # 放入写入队列
        self.data_queue.put(data)

        elapsed = time.time() - self._start_time
        self._iteration_count += 1

        # Unpack tuple
        if isinstance(data, tuple) and len(data) == 2:
            _, metrics = data
        else:
            # Fallback for safety
            metrics = data

        # Print to console (formatted like sshmonitor)
        current_time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"\n第 {self._iteration_count} 次监控 - {current_time_str}")
        logger.info("-" * 50)

        mem_used_mb = metrics.mem_used_kb / 1024
        mem_total_gb = metrics.mem_total_kb / (1024 * 1024)
        mem_avail_gb = metrics.mem_available_kb / (1024 * 1024)

        logger.info(f"内存使用率: {metrics.mem:.1f}%")
        logger.info(f"内存使用: {mem_used_mb:.2f} MB / {mem_total_gb:.2f} GB")
        logger.info(f"可用内存: {mem_avail_gb:.2f} GB")
        logger.info(f"磁盘读取: {metrics.disk_read_kb:.1f} KB")
        logger.info(f"磁盘写入: {metrics.disk_write_kb:.1f} KB")
        logger.info(f"磁盘使用率: {metrics.disk_usage:.1f}%")
        logger.info(f"CPU使用率: {metrics.cpu:.1f}%")

        self.model.set_error(None)
        self.model.append_sample(
            metrics.cpu,
            metrics.mem,
            metrics.mem_used_kb,
            metrics.mem_total_kb,
            metrics.mem_available_kb,
            metrics.disk_usage,
            metrics.disk_read_kb,
            metrics.disk_write_kb
        )

        self.view.update_chart(
            elapsed,
            metrics.cpu,
            metrics.mem,
            metrics.mem_used_kb,
            metrics.mem_total_kb,
            metrics.mem_available_kb,
            metrics.disk_usage,
            metrics.disk_read_kb,
            metrics.disk_write_kb,
            self.model.max_points
        )

    def _on_process_data_collected(self, data):
        """处理采集到的进程数据 (在主线程中执行)"""
        # data is now a tuple: (request_time, processes)

        # 1. Send full tuple to writer thread
        self.process_data_queue.put(data)

        # 2. Extract processes list and send to UI thread
        if isinstance(data, tuple) and len(data) == 2:
            _, processes = data

            # 增加打印逻辑
            self._process_iteration_count = getattr(self, '_process_iteration_count', 0) + 1
            print(f"\n{'='*20} 第 {self._process_iteration_count} 次采集 {'='*20}")
            print("找到的进程信息：")
            header = f"{'TYPE':<6} {'USER':<10} {'PID':<8} {'CPU%':<6} {'MEM%':<6} {'VSZ':<10} {'RSS':<10} {'TTY':<8} {'STAT':<5} {'START':<8} {'TIME':<10} {'CONTAINER':<15} {'PROCESS_NAME':<20}"
            print(header)
            print("=" * 140)

            type1_count = 0
            type2_count = 0

            for p in processes:
                # ProcessInfo object to dict-like access or attribute access
                print(f"{p.type:<6} {p.user:<10} {p.pid:<8} "
                      f"{p.cpu_percent:<6.1f} {p.mem_percent:<6.1f} "
                      f"{p.vsz_kb:<10} {p.rss_kb:<10} {p.tty:<8} "
                      f"{p.stat:<5} {p.start_time:<8} {p.cpu_time:<10} "
                      f"{p.container:<15} {p.process_name:<20}")

                if p.type == 'type1':
                    type1_count += 1
                elif p.type == 'type2':
                    type2_count += 1

            print(f"\n统计信息：")
            print(f"第一类进程（路径以/containers/开头）: {type1_count} 个")
            print(f"第二类进程（特定命令格式）: {type2_count} 个")
            print(f"总计: {len(processes)} 个")

            self.process_ui_queue.put(processes)
        else:
            # Fallback if something went wrong (shouldn't happen with updated collector)
            self.process_ui_queue.put(data)

    def _on_metrics_error(self, error_msg):
        self.model.set_error(error_msg)
        self.view.set_metrics_status(error_msg, "error")

    def _on_process_error(self, error_msg):
        self.model.set_error(error_msg)
        self.view.set_process_status(error_msg, "error")

    def _on_error_occurred(self, error_msg):
        # Deprecated, kept for safety if needed, but should not be called
        self.model.set_error(error_msg)
        self.view.set_status(error_msg, "error")

    # Remove _on_timer_tick as it is replaced by threads
    # def _on_timer_tick(self):
    #    ...

    def _refresh_process_view(self):
        """根据模型当前状态刷新 Group Info 图表和进程表格。"""
        # 更新分组统计到 Group Info 区域
        # self.view.update_group_chart(self.model.group_stats)
        # 更新进程表格（包含搜索/分组过滤结果）
        filtered = self.model.get_filtered_processes()
        self.view.update_process_table(filtered)

    def on_model_changed(self):
        """模型变更时刷新进程视图。

        旧的简单表格填充接口保留为兼容，但现在主要通过 update_group_chart/update_process_table 更新。
        """
        self._refresh_process_view()

    def _update_process_view(self, process_infos):
        """更新进程视图（在主线程中调用）"""
        # process_infos 已经是 ProcessInfo 对象列表，由 ProcessUIUpdateThread 转换
        self.model.set_process_list(process_infos)
        self._refresh_process_view()






