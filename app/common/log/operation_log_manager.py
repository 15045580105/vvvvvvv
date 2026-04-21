import os
import datetime
from threading import Lock

class OperationLogManager:
    """
    操作日志管理器 (Singleton)
    用于收集各模块/页面的用户操作日志，并提供导出功能。
    """
    _instance = None
    _lock = Lock()

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._logs = {}  # {module_name: [log_entry_string, ...]}
        self._registered_modules = {
            "DID数据管理",
            "DTC故障诊断",
            "UDS指令编排",
            "日志配置",
            "脚本执行",
            "设备升级",
            "设备拓扑",
            "设备管理",
            "文件传输",
            "通用配置",
        }
        self._initialized = True

    @classmethod
    def instance(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = cls()
        return cls._instance

    def append_log(self, module_name: str, message: str):
        """
        记录一条操作日志

        Args:
            module_name (str): 模块名称，如 "设备管理"
            message (str): 日志内容
        """
        self.register_module(module_name)

        if module_name not in self._logs:
            self._logs[module_name] = []

        # 通常 message 已经在 UI 上显示时带有了时间戳，或者没有。
        # 为了统一，这里我们重新加一个或者假设 message 是纯文本。
        # 如果 message 已经包含时间，这可能会重复，但为了保险起见，我们还是加上系统时间。
        # 不过为了避免 UI 和 导出不一致，最好能保持原样。
        # 这里我们假设 message 是纯文本操作描述。

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self._logs[module_name].append(log_entry)

    def register_module(self, module_name: str):
        """注册可导出的日志模块名称。"""
        if not module_name:
            return
        self._registered_modules.add(str(module_name).strip())

    def register_modules(self, module_names):
        """批量注册可导出的日志模块名称。"""
        if not module_names:
            return
        for module_name in module_names:
            self.register_module(module_name)

    def get_registered_modules(self):
        """获取所有已注册的模块名称。"""
        modules = {name for name in self._registered_modules if name}
        modules.update(self._logs.keys())
        return sorted(modules)

    def get_modules(self):
        """获取所有可导出的模块名称。"""
        return self.get_registered_modules()

    def get_logs(self, module_name: str):
        """获取指定模块的日志列表"""
        return self._logs.get(module_name, [])

    def _parse_log_time(self, log_entry: str):
        """从标准日志前缀中解析时间。"""
        if not log_entry or not log_entry.startswith("["):
            return None

        right_bracket = log_entry.find("]")
        if right_bracket <= 1:
            return None

        timestamp_text = log_entry[1:right_bracket].strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                return datetime.datetime.strptime(timestamp_text, fmt)
            except ValueError:
                continue
        return None

    def _filter_logs_by_time(self, logs, start_time=None, end_time=None):
        """按时间范围过滤日志。无法解析时间的日志默认保留。"""
        if not logs:
            return []

        if start_time is None and end_time is None:
            return list(logs)

        filtered_logs = []
        for log_entry in logs:
            log_time = self._parse_log_time(log_entry)
            if log_time is None:
                filtered_logs.append(log_entry)
                continue

            if start_time is not None and log_time < start_time:
                continue
            if end_time is not None and log_time > end_time:
                continue
            filtered_logs.append(log_entry)

        return filtered_logs

    def export_logs(self, module_name: str, export_path: str, start_time=None, end_time=None):
        """
        导出日志到文件

        Args:
            module_name (str): "所有模块" 或 具体模块名
            export_path (str): 导出目录路径
            start_time (datetime): (可选) 筛选开始时间
            end_time (datetime): (可选) 筛选结束时间

        Returns:
            list: 导出的文件路径列表
        """
        if not os.path.exists(export_path):
            try:
                os.makedirs(export_path, exist_ok=True)
            except Exception as e:
                print(f"Error creating directory {export_path}: {e}")
                return []

        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        exported_files = []

        targets = []
        is_export_all = (not module_name or module_name == "所有模块")

        if is_export_all:
            # 导出所有已注册模块，未产生日志的模块也会生成提示文件
            targets = self.get_registered_modules()
        else:
            self.register_module(module_name)
            targets = [module_name]

        for target in targets:
            logs = self._filter_logs_by_time(self.get_logs(target), start_time, end_time)

            # 简单的文件名清理，防止非法字符
            safe_name = "".join([c for c in target if c.isalnum() or c in (' ', '_', '-')]).strip()
            if not safe_name:
                safe_name = "UnknownModule"
            # 文件名：OperationLog_设备管理_20260116_120000.txt
            filename = f"OperationLog_{safe_name}_{timestamp_str}.txt"
            full_path = os.path.join(export_path, filename)

            try:
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(f"=== {target} 操作日志 ===\n")
                    f.write(f"导出时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("-" * 50 + "\n")

                    if logs:
                        for line in logs:
                            f.write(line + "\n")
                    else:
                        f.write("(该时间段内无操作日志)\n")

                exported_files.append(full_path)
            except Exception as e:
                print(f"Failed to export log for {target}: {e}")

        return exported_files

