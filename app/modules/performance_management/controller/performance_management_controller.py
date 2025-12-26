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
                    # Emit tuple: (request_time, command, response_time, metrics)
                    # Assuming command is static or fetched from somewhere, else we need to pass it here
                    command = "fetch_metrics"  # Placeholder, update logic if command varies
                    request_time = datetime.datetime.now()
                    response_time = request_time  # Placeholder, update if actual response time is available

                    # Emit the tuple
                    self.data_collected.emit((request_time, command, response_time, metrics))
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
        self.log_dir = "logs/performance"
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
            self.writer.writerow(['Request Time', 'Command', 'Response Time', 'CPU (%)', 'Memory (%)', 'Disk Usage (%)', 'Disk Read (KB)', 'Disk Write (KB)'])

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
                    # Unpack tuple (req_time, cmd, resp_time, metrics)
                    if isinstance(item, tuple) and len(item) == 4:
                        req_time, cmd, resp_time, metrics = item

                        req_time_str = req_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        resp_time_str = resp_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

                        self.writer.writerow([
                            req_time_str,
                            cmd,
                            resp_time_str,
                            metrics.cpu,
                            metrics.mem,
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
                    command = "ps -eo user,pid,%cpu,%mem,vsz,rss,tty,stat,start,time,command --sort=-%cpu" # Approximate command used in service

                    # 2. 请求数据
                    processes = self.service.fetch_processes()

                    # 3. 记录响应时间
                    response_time = datetime.datetime.now()

                    # 4. 发送数据到主线程/其他线程 (Tuple)
                    self.data_collected.emit((request_time, command, response_time, processes))
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
                "Request Time", "Command", "Response Time", "TYPE", "USER", "PID", "CPU%", "MEM%", "VSZ", "RSS", "TTY", "STAT", "START", "TIME", "CONTAINER", "PROCESS_NAME"
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
        while self._running:
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
                    if isinstance(item, tuple) and len(item) == 4:
                        req_time, cmd, resp_time, processes = item

                        # Format times
                        req_time_str = req_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        resp_time_str = resp_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

                        for p in processes:
                            self.writer.writerow([
                                req_time_str,
                                cmd,
                                resp_time_str,
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
        filename = f"performance_data_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        abs_path = os.path.abspath(filename)

        try:
            import openpyxl
            wb = openpyxl.Workbook()

            # Remove default sheet
            if "Sheet" in wb.sheetnames:
                wb.remove(wb["Sheet"])

            if metrics_only or (not process_only):
                ws_metrics = wb.create_sheet("Metrics")
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

            if process_only or (not metrics_only):
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
            link = f'<a href="file:///{abs_path}">{abs_path}</a>'

            if metrics_only:
                self.view.set_metrics_status(f"数据已导出到: {link}", "info")
            elif process_only:
                self.view.set_process_status(f"数据已导出到: {link}", "info")
            else:
                # Fallback if both
                self.view.set_metrics_status(f"数据已导出到: {link}", "info")
                self.view.set_process_status(f"数据已导出到: {link}", "info")

        except ImportError:
            msg = "导出失败: 未安装 openpyxl 库"
            if metrics_only: self.view.set_metrics_status(msg, "error")
            elif process_only: self.view.set_process_status(msg, "error")
        except Exception as e:
            msg = f"导出失败: {str(e)}"
            if metrics_only: self.view.set_metrics_status(msg, "error")
            elif process_only: self.view.set_process_status(msg, "error")


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
        # data is now a tuple: (request_time, command, response_time, metrics)

        # 放入写入队列
        self.data_queue.put(data)

        elapsed = time.time() - self._start_time
        self._iteration_count += 1

        # Unpack tuple
        if isinstance(data, tuple) and len(data) == 4:
            _, _, _, metrics = data
        else:
            # Fallback for safety
            metrics = data

        # Print to console
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Metrics - CPU: {metrics.cpu:.1f}%, Mem: {metrics.mem:.1f}%")

        self.model.set_error(None)
        self.model.append_sample(metrics.cpu, metrics.mem, metrics.disk_usage, metrics.disk_read_kb, metrics.disk_write_kb)

        # Update chart with new data
        # Pass elapsed time as x_value. The view will handle the scrolling window.
        self.view.update_chart(elapsed, metrics.cpu, metrics.mem, metrics.disk_usage, metrics.disk_read_kb, metrics.disk_write_kb, self.model.max_points)

    def _on_process_data_collected(self, data):
        """处理采集到的进程数据 (在主线程中执行)"""
        # data is now a tuple: (request_time, command, response_time, processes)

        # 1. Send full tuple to writer thread
        self.process_data_queue.put(data)

        # 2. Extract processes list and send to UI thread
        if isinstance(data, tuple) and len(data) == 4:
            _, _, _, processes = data
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
