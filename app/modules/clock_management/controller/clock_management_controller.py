from PyQt5.QtCore import pyqtSignal, QTimer
from datetime import datetime
from app.core.base_controller import BaseController
from app.modules.clock_management.view.clock_management_view import ClockManagementWidget
from app.services.device_manage.device_service import DeviceService
from app.core.dependency_injection import di_container
from app.common.utils.worker import Worker


# Define task outside of class to avoid closure issues and ensure clean state
def fetch_time_task(device_service):
    """独立的 SSH 任务函数，运行在 Worker 线程中"""
    ssh_client = device_service.get_ssh_client() if device_service else None
    if not ssh_client:
        return None
    try:
        # 1. Date
        date_out = ssh_client.execute_command("date '+%Y-%m-%d %H:%M:%S'")
        # 2. Timezone
        tz_out = ssh_client.execute_command("date +%z")
        # 3. Uptime
        uptime_out = ssh_client.execute_command("cat /proc/uptime")

        return {
            "date_full": date_out.strip() if date_out else "",
            "timezone": tz_out.strip() if tz_out else "",
            "uptime_full": uptime_out.strip() if uptime_out else ""
        }
    except Exception as e:
        print(f"Fetch VM1 Time Error: {str(e)}")
        return None


class ClockManagementController(BaseController):
    """时钟管理模块控制器：封装 ClockManagementWidget 以适配主界面架构。"""

    # 定义信号，用于更新View
    # 参数1: clock_id (str), 参数2: data (dict)
    update_clock_signal = pyqtSignal(str, dict)

    def __init__(self, parent=None):
        self.view = ClockManagementWidget(parent)
        # 时钟页面目前没有独立的模型，直接传 None
        super().__init__(model=None, view=self.view, parent=parent)

        self.device_service = di_container.resolve(DeviceService)

        # 连接信号到 View 的更新槽函数
        # 注意：ClockManagementWidget 只是容器，实际更新是在 SystemTimeInfoWidget
        # 我们需要在 view 中暴露 system_time_widget 的接口，或者直接连接
        self.update_clock_signal.connect(self.view.system_time_widget.update_clock_data)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._fetch_all_clocks)
        self._refresh_timer.start(1000)  # Check every 1 seconds

        # 存储 worker 引用，key为 clock_id
        self._workers = {}

    def _get_active_device_service(self):
        service = di_container.resolve(DeviceService)
        if service:
            self.device_service = service
        return self.device_service

    def _fetch_all_clocks(self):
        """同时获取所有需要的时钟数据"""
        # 安全检查
        service = self._get_active_device_service()
        if not self.view or not service:
            self._refresh_timer.stop()
            return

        ssh_client = service.get_ssh_client()
        if not ssh_client or not ssh_client.is_connected():
            return

        # 获取 VM1 时间
        self._start_fetch_worker(service, "vm1")
        # 如果需要获取 RT1, RT2，可以在这里继续添加调用
        # self._start_fetch_worker(ssh_client, "rt1")
        # self._start_fetch_worker(ssh_client, "rt2")

    def _start_fetch_worker(self, device_service, clock_id):
        """启动特定 ID 的获取任务"""
        # 检查是否已有任务在运行
        if clock_id in self._workers and self._workers[clock_id].isRunning():
            return

        # 创建 Worker
        worker = Worker(lambda: fetch_time_task(device_service))

        # 使用 lambda 绑定 clock_id
        worker.result_signal.connect(lambda res: self._on_time_fetched(clock_id, res))

        # 存储引用并启动
        self._workers[clock_id] = worker
        worker.start()

    def _on_time_fetched(self, clock_id, result):
        if not result:
            return

        # 防御性编程：在更新 UI 前捕获可能的 RuntimeError (Wrapped C++ object deleted)
        try:
            date_full = result.get("date_full", "")
            tz_out = result.get("timezone", "")
            uptime_full = result.get("uptime_full", "")

            time_str = "--:--:--"
            date_str = "----年--月--日"

            try:
                dt = datetime.strptime(date_full, "%Y-%m-%d %H:%M:%S")
                time_str = dt.strftime("%H:%M:%S")
                date_str = dt.strftime("%Y年%m月%d日")
                weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
                date_str += " " + weekdays[dt.weekday()]
            except:
                # 尝试其他格式或保持原样
                try:
                    # 有些系统 date 命令可能返回 "Tue Feb 4 14:00:00 UTC 2026"
                    # 这里保留简单回退逻辑
                    pass
                except:
                    pass
                time_str = date_full
                date_str = date_full

            uptime_val = "--秒"
            if uptime_full:
                parts = uptime_full.split()
                if parts:
                    uptime_val = f"{parts[0]}秒"

            tz_val = tz_out if tz_out else "--"

            # 构造 View 需要的纯数据格式
            data = {
                "time": time_str,
                "date": date_str,
                "timezone": tz_val,
                "uptime": uptime_val
            }

            # 发送信号更新 UI
            self.update_clock_signal.emit(clock_id, data)

        except RuntimeError:
            self._refresh_timer.stop()
        except Exception as e:
            # print(f"Error updating {clock_id} time UI: {e}")
            pass

    def get_view(self):
        """供 MainController / Tab 构建使用，返回视图对象。"""
        return self.view
