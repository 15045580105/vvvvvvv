import os
import time
import datetime
import csv
import queue
from PyQt5 import QtCore
from app.modules.performance_management.model.performance_management_model import ProcessInfo
from app.common.utils.path_utils import get_performance_export_path

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


class ExportWorker(QtCore.QThread):
    """数据导出线程"""
    # type (metrics/process), message, level
    status_updated = QtCore.pyqtSignal(str, str, str) # type, message, level
    finished = QtCore.pyqtSignal()

    def __init__(self, metrics_only=False, process_only=False, metrics_count=0, process_count=0):
        super().__init__()
        self.metrics_only = metrics_only
        self.process_only = process_only
        self.metrics_count = metrics_count
        self.process_count = process_count

    def run(self):
        # Use new performance export path
        base_dir = get_performance_export_path()

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
                perf_filename = os.path.join(base_dir, "Performance_Metrics_Data.xlsx")
                wb_perf = openpyxl.Workbook()
                if "Sheet" in wb_perf.sheetnames:
                    del wb_perf["Sheet"]
                ws_metrics = wb_perf.create_sheet("Metrics")

                # 写入表头
                headers = [
                    'Request Time', 'CPU (%)', 'Memory (%)', 'Mem Used (KB)', 'Mem Total (KB)', 'Mem Available (KB)',
                    'Disk Usage (%)', 'Disk Read (KB)', 'Disk Write (KB)'
                ]
                ws_metrics.append(headers)

                # 读取 logs/performance metrics/ 下的所有 CSV
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

                # Keep link format but use new path
                link = f'<a href="file:///{perf_filename.replace(os.sep, "/")}">{perf_filename}</a>'
                self.status_updated.emit("metrics", f"性能数据已导出(最近{self.metrics_count}条): {link}", "info")

            # --- 导出进程数据 ---
            if self.process_only or (not self.metrics_only):
                proc_filename = os.path.join(base_dir, "Process_Data.xlsx")
                wb_proc = openpyxl.Workbook()
                if "Sheet" in wb_proc.sheetnames:
                    del wb_proc["Sheet"]
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

                    link = f'<a href="file:///{proc_filename.replace(os.sep, "/")}">{proc_filename}</a>'
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

