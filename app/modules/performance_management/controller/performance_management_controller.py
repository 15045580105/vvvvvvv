from app.core.base_controller import BaseController
from app.modules.performance_management.model.performance_management_model import (
    PerformanceModel,
    ProcessInfo,
)
from app.modules.performance_management.view.performance_management_view import PerformanceView
from app.services.device_manage.performance_service import PerformanceService
from app.core.dependency_injection import di_container
from app.services.device_manage.device_service import DeviceService

from PyQt5 import QtCore
import time
import csv
import datetime
import os
import queue


class DataCollectorThread(QtCore.QThread):
    """数据采集线程"""
    data_collected = QtCore.pyqtSignal(object)
    error_occurred = QtCore.pyqtSignal(str)

    def __init__(self, service, interval_ms):
        super().__init__()
        self.service = service
        self.interval_ms = interval_ms
        self._running = True
        self._paused = False

    def run(self):
        while self._running:
            if not self._paused:
                try:
                    metrics = self.service.fetch_metrics()
                    request_time = datetime.datetime.now()
                    # Emit the tuple
                    self.data_collected.emit((request_time, metrics))
                except Exception as e:
                    self.error_occurred.emit(str(e))

            # Sleep for interval
            time.sleep(self.interval_ms / 1000.0)

    def stop(self):
        self._running = False
        self.wait()

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def set_interval(self, interval_ms):
        self.interval_ms = interval_ms


class DataWriterThread(QtCore.QThread):
    """数据写入文件线程，支持7天数据轮转"""
    def __init__(self, data_queue):
        super().__init__()
        self.data_queue = data_queue
        self._running = True
        self.log_dir = "logs/performance metrics"
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        self.current_date = datetime.date.today()
        self.file_handle = None
        self.writer = None
        self._open_file()

    def _open_file(self):
        if self.file_handle:
            self.file_handle.close()

        filename = f"performance_{self.current_date.strftime('%Y%m%d')}.csv"
        filepath = os.path.join(self.log_dir, filename)

        # Check if file exists to write header
        file_exists = os.path.exists(filepath)

        self.file_handle = open(filepath, 'a', newline='')
        self.writer = csv.writer(self.file_handle)

        if not file_exists:
            self.writer.writerow([
                'Request Time','CPU (%)', 'Memory (%)', 'Mem Used (KB)', 'Mem Total (KB)', 'Mem Available (KB)',
                'Disk Usage (%)', 'Disk Read (KB)', 'Disk Write (KB)'
            ])

        self._cleanup_old_files()

    def _cleanup_old_files(self):
        """保留最近7天的文件"""
        try:
            files = sorted([f for f in os.listdir(self.log_dir) if f.startswith("performance_") and f.endswith(".csv")])
            while len(files) > 7:
                os.remove(os.path.join(self.log_dir, files[0]))
                files.pop(0)
        except Exception as e:
            print(f"Cleanup failed: {e}")

    def run(self):
        while self._running or not self.data_queue.empty():
            try:
                item = self.data_queue.get(timeout=1)

                # Check for date change
                if datetime.date.today() != self.current_date:
                    self.current_date = datetime.date.today()
                    self._open_file()

                if self.writer:
                    # Unpack tuple (req_time, metrics)
                    if isinstance(item, tuple) and len(item) == 2:
                        req_time, metrics = item

                        req_time_str = req_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

                        self.writer.writerow([
                            req_time_str,
                            metrics.cpu,
                            metrics.mem,
                            metrics.mem_used_kb,
                            metrics.mem_total_kb,
                            metrics.mem_available_kb,
                            metrics.disk_usage,
                            metrics.disk_read_kb,
                            metrics.disk_write_kb
                        ])
                        self.file_handle.flush() # Ensure data is written
                    else:
                        # Fallback for old format (just metrics object)
                        # But we should update collector to send tuple
                        pass

                self.data_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error writing to file: {e}")

    def stop(self):
        self._running = False
        self.wait()
        if self.file_handle:
            self.file_handle.close()


class ProcessCollectorThread(QtCore.QThread):
    """进程数据采集线程"""
    data_collected = QtCore.pyqtSignal(object) # Changed to object to support tuple
    error_occurred = QtCore.pyqtSignal(str)

    def __init__(self, service, interval_ms):
        super().__init__()
        self.service = service
        self.interval_ms = interval_ms
        self._running = True
        self._paused = False

    def run(self):
        while self._running:
            if not self._paused:
                try:
                    # 1. 记录请求时间
                    request_time = datetime.datetime.now()

                    # 2. 请求数据
                    processes = self.service.fetch_processes()

                    # 3. 发送数据到主线程/其他线程 (Tuple)
                    self.data_collected.emit((request_time, processes))
                except Exception as e:
                    self.error_occurred.emit(str(e))

            # Sleep for interval
            time.sleep(self.interval_ms / 1000.0)

    def stop(self):
        self._running = False
        self.wait()

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def set_interval(self, interval_ms):
        self.interval_ms = interval_ms


class ProcessWriterThread(QtCore.QThread):
    """进程数据写入文件线程"""
    def __init__(self, data_queue):
        super().__init__()
        self.data_queue = data_queue
        self._running = True
        self.log_dir = "logs/process"
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        self.current_date = datetime.date.today()
        self.file_handle = None
        self.writer = None
        self._open_file()

    def _open_file(self):
        if self.file_handle:
            self.file_handle.close()

        filename = f"process_{self.current_date.strftime('%Y%m%d')}.csv"
        filepath = os.path.join(self.log_dir, filename)

        # Check if file exists to write header
        file_exists = os.path.exists(filepath)

        self.file_handle = open(filepath, 'a', newline='', encoding='utf-8')
        self.writer = csv.writer(self.file_handle)

        if not file_exists:
            self.writer.writerow([
                "Request Time", "TYPE", "USER", "PID", "CPU%", "MEM%", "VSZ", "RSS", "TTY", "STAT", "START", "TIME", "CONTAINER", "PROCESS_NAME"
            ])

        self._cleanup_old_files()

    def _cleanup_old_files(self):
        """保留最近7天的文件"""
        try:
            files = sorted([f for f in os.listdir(self.log_dir) if f.startswith("process_") and f.endswith(".csv")])
            while len(files) > 7:
                os.remove(os.path.join(self.log_dir, files[0]))
                files.pop(0)
        except Exception as e:
            print(f"Cleanup failed: {e}")

    def run(self):
        while self._running or not self.data_queue.empty():
            try:
                # 从队列获取数据，设置超时避免死锁
                # data_queue now expects a tuple: (request_time, command, response_time, processes)
                item = self.data_queue.get(timeout=1)

                # Check for date change
                if datetime.date.today() != self.current_date:
                    self.current_date = datetime.date.today()
                    self._open_file()

                if self.writer:
                    # Unpack the tuple
                    if isinstance(item, tuple) and len(item) == 2:
                        req_time, processes = item

                        # Format times
                        req_time_str = req_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

                        for p in processes:
                            self.writer.writerow([
                                req_time_str,
                                p.type, p.user, p.pid, p.cpu_percent, p.mem_percent, p.vsz_kb, p.rss_kb,
                                p.tty, p.stat, p.start_time, p.cpu_time, p.container, p.process_name
                            ])
                        self.file_handle.flush() # Ensure data is written
                    else:
                        # Fallback for old format if any (just processes list)
                        # But we should ensure collector sends the tuple
                        pass

                self.data_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error writing to file: {e}")

    def stop(self):
        self._running = False
        self.wait()
        if self.file_handle:
            self.file_handle.close()


class ProcessUIUpdateThread(QtCore.QThread):
    """
    进程UI数据处理线程
    从队列拿数据，处理成UI需要的格式，然后通过信号发送给主线程渲染
    虽然可以直接在主线程处理，但为了严格符合"独立线程拿数据渲染"的要求，
    我们在这里做数据转换，减轻主线程负担。
    """
    data_processed = QtCore.pyqtSignal(list)

    def __init__(self, input_queue):
        super().__init__()
        self.input_queue = input_queue
        self._running = True

    def run(self):
        while self._running:
            try:
                processes = self.input_queue.get(timeout=1)

                # 这里进行数据转换，转为 ProcessInfo 对象列表
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

                self.data_processed.emit(process_infos)
                self.input_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error processing UI data: {e}")

    def stop(self):
        self._running = False
        self.wait()


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
        # Export logic for metrics only
        if not self.model.samples:
            self.view.set_metrics_status("没有性能数据可导出", "warn")
            return
        # ... (reuse export logic but only for metrics sheet)
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
        # Prevent multiple exports at the same time if needed, or just let them run
        # For simplicity, we create a new worker each time.
        # Ideally, we should track it to avoid garbage collection issues if it finishes too quickly or not at all.

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

    # def _on_set_group_clicked(self):
    #     """Set Group Name 按钮点击的占位处理。
    #
    #     后续可在此弹出分组规则配置对话框，并根据规则更新各进程的 group_name。
    #     """
    #     # 当前先不实现复杂对话框，仅作为占位，避免界面无响应
    #     self.view.set_status("分组配置对话框暂未实现", "warn")

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
        print(f"\n第 {self._iteration_count} 次监控 - {current_time_str}")
        print("-" * 50)

        mem_used_mb = metrics.mem_used_kb / 1024
        mem_total_gb = metrics.mem_total_kb / (1024 * 1024)
        mem_avail_gb = metrics.mem_available_kb / (1024 * 1024)

        print(f"内存使用率: {metrics.mem:.1f}%")
        print(f"内存使用: {mem_used_mb:.2f} MB / {mem_total_gb:.2f} GB")
        print(f"可用内存: {mem_avail_gb:.2f} GB")
        print(f"磁盘读取: {metrics.disk_read_kb:.1f} KB")
        print(f"磁盘写入: {metrics.disk_write_kb:.1f} KB")
        print(f"磁盘使用率: {metrics.disk_usage:.1f}%")
        print(f"CPU使用率: {metrics.cpu:.1f}%")

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

        # Update chart with new data
        # Pass elapsed time as x_value. The view will handle the scrolling window.
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


class ExportWorker(QtCore.QThread):
    """数据导出线程"""
    # type (metrics/process), message, level
    status_updated = QtCore.pyqtSignal(str, str, str)

    def __init__(self, metrics_only=False, process_only=False, metrics_count=0, process_count=0):
        super().__init__()
        self.metrics_only = metrics_only
        self.process_only = process_only
        self.metrics_count = metrics_count
        self.process_count = process_count

    def run(self):
        base_dir = os.getcwd()

        try:
            import openpyxl
            from openpyxl.styles import PatternFill

            # 定义样式
            fill_odd = PatternFill(start_color="E0F2FE", end_color="E0F2FE", fill_type="solid")   # Light Blue
            fill_even = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")  # Light Yellow

            def apply_metrics_style(ws):
                # Auto-adjust column width & Apply alternating row colors
                for i, row in enumerate(ws.iter_rows(min_row=2)): # Skip header
                    if i % 1000 == 0: time.sleep(0.001) # Prevent UI freeze
                    fill = fill_odd if (i + 2) % 2 != 0 else fill_even
                    for cell in row:
                        cell.fill = fill

                _adjust_column_width(ws)

            def apply_process_style(ws):
                # Apply colors based on Request Time batch
                last_time = None
                use_odd = True # Start with odd (Blue)

                for i, row in enumerate(ws.iter_rows(min_row=2)):
                    if i % 1000 == 0: time.sleep(0.001) # Prevent UI freeze
                    # Assuming first column is Request Time
                    current_time = row[0].value

                    if current_time != last_time:
                        use_odd = not use_odd # Toggle color
                        last_time = current_time

                    fill = fill_odd if use_odd else fill_even
                    for cell in row:
                        cell.fill = fill

                _adjust_column_width(ws)

            def _adjust_column_width(ws):
                for col in ws.columns:
                    max_length = 0
                    column = col[0].column_letter
                    for cell in col:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = (max_length + 2)
                    ws.column_dimensions[column].width = min(adjusted_width, 50) # Limit max width

            # --- 导出性能数据 ---
            if self.metrics_only or (not self.process_only):
                perf_filename = os.path.join(base_dir, "Performance_Metrics_Data_7Days.xlsx")
                wb_perf = openpyxl.Workbook()
                if "Sheet" in wb_perf.sheetnames: wb_perf.remove(wb_perf["Sheet"])
                ws_metrics = wb_perf.create_sheet("Metrics")

                # 写入表头
                headers = [
                    'Request Time', 'CPU (%)', 'Memory (%)', 'Mem Used (KB)', 'Mem Total (KB)', 'Mem Available (KB)',
                    'Disk Usage (%)', 'Disk Read (KB)', 'Disk Write (KB)'
                ]
                ws_metrics.append(headers)

                # 读取 logs/performance/ 下的所有 CSV
                log_dir = "logs/performance metrics"
                if os.path.exists(log_dir):
                    files = sorted([f for f in os.listdir(log_dir) if f.startswith("performance_") and f.endswith(".csv")])
                    for idx, f in enumerate(files):
                        if idx % 5 == 0: time.sleep(0.001) # Yield
                        filepath = os.path.join(log_dir, f)
                        try:
                            with open(filepath, 'r', encoding='utf-8', errors='ignore') as csvfile:
                                reader = csv.reader(csvfile)
                                next(reader, None) # Skip header
                                for row in reader:
                                    # 转换数值类型
                                    new_row = []
                                    for idx, val in enumerate(row):
                                        if idx >= 1: # 数值列
                                            try: new_row.append(float(val))
                                            except: new_row.append(val)
                                        else:
                                            new_row.append(val)
                                    ws_metrics.append(new_row)
                        except Exception as e:
                            print(f"Error reading {f}: {e}")

                apply_metrics_style(ws_metrics)
                wb_perf.save(perf_filename)
                link = f'<a href="file:///{perf_filename}">{perf_filename}</a>'
                self.status_updated.emit("metrics", f"性能数据已导出(最近{self.metrics_count}条): {link}", "info")

            # --- 导出进程数据 ---
            if self.process_only or (not self.metrics_only):
                proc_filename = os.path.join(base_dir, "Process_Data_7Days.xlsx")
                wb_proc = openpyxl.Workbook()
                if "Sheet" in wb_proc.sheetnames: wb_proc.remove(wb_proc["Sheet"])
                ws_proc = wb_proc.create_sheet("Processes")

                headers = [
                    "Request Time", "TYPE", "USER", "PID", "CPU%", "MEM%", "VSZ", "RSS", "TTY", "STAT", "START", "TIME", "CONTAINER", "PROCESS_NAME"
                ]
                ws_proc.append(headers)

                # 读取 logs/process/ 下的所有 CSV
                log_dir = "logs/process"
                max_rows = 500000

                if os.path.exists(log_dir):
                    files = sorted([f for f in os.listdir(log_dir) if f.startswith("process_") and f.endswith(".csv")])

                    # Re-implement with deque for efficiency
                    from collections import deque
                    rows_deque = deque(maxlen=max_rows)

                    for idx, f in enumerate(files): # Chronological order
                        if idx % 5 == 0: time.sleep(0.001) # Yield
                        filepath = os.path.join(log_dir, f)
                        try:
                            with open(filepath, 'r', encoding='utf-8', errors='ignore') as csvfile:
                                reader = csv.reader(csvfile)
                                header = next(reader, None)
                                for row in reader:
                                    # Convert numbers
                                    for idx in [3, 4, 5, 6, 7]:
                                        if idx < len(row):
                                            try: row[idx] = float(row[idx])
                                            except: pass
                                    rows_deque.append(row)
                        except: pass

                    for i, row in enumerate(rows_deque):
                        if i % 1000 == 0: time.sleep(0.001) # Yield
                        ws_proc.append(row)

                    apply_process_style(ws_proc)
                    wb_proc.save(proc_filename)
                    link = f'<a href="file:///{proc_filename}">{proc_filename}</a>'
                    self.status_updated.emit("process", f"进程数据已导出(最近{self.process_count}条): {link}", "info")
                else:
                    self.status_updated.emit("process", "没有找到进程日志目录", "warn")

        except ImportError:
            msg = "导出失败: 未安装 openpyxl 库"
            if self.metrics_only: self.status_updated.emit("metrics", msg, "error")
            elif self.process_only: self.status_updated.emit("process", msg, "error")
        except Exception as e:
            msg = f"导出失败: {str(e)}"
            if self.metrics_only: self.status_updated.emit("metrics", msg, "error")
            elif self.process_only: self.status_updated.emit("process", msg, "error")

