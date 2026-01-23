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

    def get_modules(self):
        """获取所有模块名称(动态获取)"""
        return sorted(list(self._logs.keys()))

    def get_logs(self, module_name: str):
        """获取指定模块的日志列表"""
        return self._logs.get(module_name, [])

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
            # 如果是导出所有，我们只导出实际有日志的模块
            targets = self.get_modules()
        else:
            targets = [module_name]

        for target in targets:
            logs = self.get_logs(target)

            # 如果是指定导出某个模块，即使为空也生成一个文件，给用户反馈
            # 如果是批量导出所有，跳过空的
            if not logs and is_export_all:
                continue

            # 简单的文件名清理，防止非法字符
            safe_name = "".join([c for c in target if c.isalnum() or c in (' ', '_', '-')]).strip()
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

