from typing import List, Dict, Any, Callable
from PyQt5.QtCore import QObject, pyqtSignal
from app.services.file_manage.file_transfer_service import FileTransferService
from app.services.file_manage.utils.filename_parser import parse_filename_metadata

class DownloadManager(QObject):
    """
    业务逻辑层：日志下载管理器
    负责处理与日志相关的业务规则，如：
    - 知道日志存储在哪些目录
    - 知道如何从文件名解析元数据（APPID, 时间等）
    - 协调底层的 FileTransferService 进行传输
    """
    log_signal = pyqtSignal(str)

    # 定义需要扫描的日志目录
    LOG_ROOT = "/log"
    BUS_ROOT = "/bigdatadb/eth"

    def __init__(self):
        """初始化下载管理器，实例化底层传输服务。"""
        # 1. 创建文件传输服务实例
        super().__init__()
        self.service = FileTransferService()

    def connect(self, host: str, user: str, pass_: str) -> bool:
        """连接设备，建立会话。"""
        # 1. 检查当前连接状态
        if self.service.is_connected():
            # 2. 如果已连接则直接返回成功
            return True
        # 3. 未连接则发起连接请求
        return self.service.connect_device(host, 22, user, pass_)

    def is_connected(self) -> bool:
        """检查设备是否已连接。"""
        # 1. 返回底层服务的连接状态
        return self.service.is_connected()

    def fetch_log_list(self, custom_path: str = None) -> List[Dict[str, Any]]:
        """获取所有日志文件的完整列表（经过业务处理）。"""
        # 1. 初始化回调函数
        _log = self.log_signal.emit

        # 2. 确定要扫描的目录列表
        dirs_to_scan = self._resolve_scan_dirs(
            root_path=self.LOG_ROOT,
            custom_path=custom_path
        )

        # 3. 扫描目录并提取文件，同时解析业务元数据
        return self._scan_dirs_and_fetch_files(dirs_to_scan, lambda f, rd: self._process_log_file(f))

    def _resolve_scan_dirs(self, root_path: str, custom_path: str) -> List[str]:
        """确定要扫描的目录列表。"""
        _log = self.log_signal.emit
        chosen_dirs = []

        if custom_path:
            # 1. 如果用户手动指定了路径，则只扫描该路径
            _log(f"使用用户指定路径进行扫描: {custom_path}")
            chosen_dirs = [custom_path]
        else:
            # 2. 否则进行动态发现
            _log(f"未指定具体路径，正在动态扫描 {root_path} 下的所有目录...")

            # 使用公共方法获取选项 (它也会调用 log_callback)
            options = self.fetch_remote_path_options(root_path)

            if options:
                # 提取 path 字段
                chosen_dirs = [opt["path"] for opt in options]
                _log(f"发现 {len(chosen_dirs)} 个动态目录")
            else:
                _log("未能自动发现任何目录，尝试兜底扫描 AppLog...")
                if "dynamics" not in root_path: # Prevent recursion loop if root is already base
                     chosen_dirs = [f"{root_path}/AppLog"]
                # log_callback(f"动态目录发现失败: {e}")

        return chosen_dirs

    def _scan_dirs_and_fetch_files(self, dirs: List[str], processor: Callable[[Dict, str], Dict]) -> List[Dict[str, Any]]:
        """遍历目录列表，获取文件信息并解析业务元数据。"""
        _log = self.log_signal.emit
        all_logs = []

        for remote_dir in dirs:
            # 1. 记录日志
            _log(f"正在扫描目录: {remote_dir} ...")

            try:
                # 2. 获取原始文件列表 (ls -l 风格)
                files = self.service.list_remote_files(remote_dir)
                _log(f"目录 {remote_dir} 扫描完成，发现 {len(files)} 个文件")

                # 3. 处理每个文件
                for f in files:
                    # 将业务无关的 FileInfo 转换为业务相关的 LogInfo
                    # processor 负责解析文件名中的 APPID, DATE 等
                    processed_log = processor(f, remote_dir)
                    if processed_log:
                        all_logs.append(processed_log)

            except Exception as e:
                # 4. 容错处理：单个目录失败不影响其他目录
                _log(f"扫描目录 {remote_dir} 失败: {str(e)}")

        return all_logs

    def download_file(self, remote_path: str, local_path: str, progress_callback=None):
        """下载单个文件到本地。"""
        # 1. 委托给底层服务执行下载
        return self.service.download_file(remote_path, local_path, progress_callback)

    def _process_log_file(self, raw_file: Dict[str, Any]) -> Dict[str, Any]:
        """核心业务逻辑：将原始文件信息转换为业务对象。"""
        # 1. 获取文件名
        filename = raw_file.get("name", "")
        # 2. 解析文件名元数据 (APPID, 时间)
        meta = self._parse_filename_metadata(filename)

        # 3. 确定显示时间：优先用文件名时间，其次用修改时间
        display_time = meta["create_time"] if meta["create_time"] else raw_file.get("mtime", "")

        # 4. 构建并返回统一格式的文件记录
        return self._build_file_record(
            filename=filename,
            path=raw_file.get("path", ""),
            raw_file=raw_file,
            appid=meta["appid"],
            create_time=display_time
        )

    def _build_file_record(self, filename: str, path: str, raw_file: Dict[str, Any], appid: str, create_time: str) -> Dict[str, Any]:
        """构建标准的文件业务对象字典。"""
        # 1. 组装文件基本信息字典
        return {
            "filename": filename,
            "path": path,
            "appid": appid,
            "size_kb": raw_file.get("size_kb", ""),
            "create_time": create_time,
            "modified_time": raw_file.get("mtime", ""),
            # 2. 设置初始下载状态
            "progress": 0,
            "status": "未下载",
            # 3. 保留原始字节大小
            "raw_size": raw_file.get("size", 0)
        }

    def _parse_filename_metadata(self, filename: str) -> Dict[str, str]:
        """解析文件名中的元数据（委托给集中于 helper 的解析器）。"""
        # 1. 调用外部工具解析
        parsed = parse_filename_metadata(filename)
        # 2. 转换为本类兼容的格式
        return {
            "appid": parsed.get("appid") or "",
            "create_time": parsed.get("create_time") or "",
        }

    def fetch_remote_path_options(self, base_path: str) -> List[Dict[str, Any]]:
        """
        获取远程目录下的子目录列表，用于填充下拉框或自动扫描。
        通常用于 /log 或 /bigdatadb/eth
        """
        _log = self.log_signal.emit
        options = []

        # 1. 连接检查
        if not self.service.is_connected():
            _log("设备未连接，无法获取路径选项")
            return []

        try:
            # 2. 执行 ls 命令获取子目录
            # ls -F: 目录后加 /
            cmd = f"ls -F {base_path}"
            _log(f"探测子目录: {cmd}")

            # 使用 service 内部的 execute_command (需要 service 暴露这个能力)
            # FileTransferService 本身没有 execute_command，它封装了 ssh_client
            # 我们需要访问底层的 ssh_client

            if hasattr(self.service, "ssh_client") and self.service.ssh_client:
                 # Check simple usage or if ssh_client is None
                 pass

            # 由于 FileTransferService 封装比较深，这里假设它应该提供能力
            # 或者我们直接利用 list_remote_files ? list_remote_files 返回的是文件属性
            # 如果是目录，size 4096 etc.

            # 既然 FileTransferService 是 DownloadManager 的成员，我们看看它是否有能力
            # 假设 DownloadManager 的 service 属性是 FileTransferService 实例
            # 我们可以通过 service.client (SSHClient) 来执行

            if hasattr(self.service, "ssh_client") and self.service.ssh_client:
                stdout = self.service.ssh_client.execute_command(cmd)

                if stdout:
                    for line in stdout.splitlines():
                        line = line.strip()
                        if not line: continue

                        # 3. 过滤出目录 (以 / 结尾)
                        if line.endswith("/"):
                            dir_name = line[:-1] # 去掉 /
                            full_path = f"{base_path}/{dir_name}"

                            # 构造选项
                            options.append({
                                "name": dir_name,
                                "path": full_path,
                                "type": "dir"
                            })

                    _log(f"路径探测完成，找到 {len(options)} 个子目录")
                else:
                    _log(f"路径探测无返回或为空: {base_path}")
            else:
                 _log("底层 SSH 客户端不可用")

        except Exception as e:
            _log(f"无法扫描路径 {base_path}: {e}")

        return options

    def fetch_bus_tabs(self) -> List[Dict[str, Any]]:
        """获取总线数据的一级目录，用于生成 Tabs"""
        return self.fetch_remote_path_options("/bigdatadb/eth")

    def fetch_bus_file_list(self, tab_path: str = None) -> List[Dict[str, Any]]:
        """获取总线文件列表 (类似 Log，但可能没有复杂的解析)"""
        _log = self.log_signal.emit

        # 如果没有选 Tab，默认扫描根
        scan_path = tab_path if tab_path else "/bigdatadb/eth"

        # 1. 扫描
        raw_files = []
        try:
            _log(f"正在扫描总线目录: {scan_path} ...")
            raw_files = self.service.list_remote_files(scan_path)
            _log(f"发现 {len(raw_files)} 个总线文件")
        except Exception as e:
            _log(f"扫描异常: {e}")
            return []

        # 2. 简单转换
        result_list = []
        for f in raw_files:
            # 过滤掉子目录本身
            if f.get("permissions", "").startswith("d"):
                continue

            entry = {
                "name": f.get("filename"),
                "size": f.get("size_str"), # 假设 service 已经格式化了
                "date": f.get("mtime_str"), # 假设 service 已经格式化了
                "path": f"{scan_path}/{f.get('filename')}",
                "raw_size": f.get("size")
            }
            result_list.append(entry)

        return result_list
