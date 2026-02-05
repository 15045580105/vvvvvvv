import re
from typing import List, Dict, Any, Callable
from app.services.file_manage.file_transfer_service import FileTransferService
from app.services.file_manage.utils.filename_parser import parse_filename_metadata

class DownloadManager:
    """
    业务逻辑层：日志下载管理器
    负责处理与日志相关的业务规则，如：
    - 知道日志存储在哪些目录
    - 知道如何从文件名解析元数据（APPID, 时间等）
    - 协调底层的 FileTransferService 进行传输
    """

    # 定义需要扫描的日志目录
    LOG_ROOT = "/log"
    BUS_ROOT = "/bigdatadb/eth"

    def __init__(self):
        """初始化下载管理器，实例化底层传输服务。"""
        # 1. 创建文件传输服务实例
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

    def fetch_log_list(self, log_callback: Callable[[str], None] = None, custom_path: str = None) -> List[Dict[str, Any]]:
        """获取所有日志文件的完整列表（经过业务处理）。"""
        # 1. 初始化回调函数
        if not log_callback:
            log_callback = lambda msg: None

        # 2. 确定要扫描的目录列表
        dirs_to_scan = self._resolve_scan_dirs(
            root_path=self.LOG_ROOT,
            custom_path=custom_path,
            log_callback=log_callback
        )

        # 3. 定义针对日志文件的处理回调
        def log_processor(raw_file, dir_path):
            return self._process_log_file(raw_file)

        # 4. 执行目录扫描并获取文件列表
        return self._scan_dirs_and_fetch_files(dirs_to_scan, log_processor, log_callback)

    def _resolve_scan_dirs(self, root_path: str, custom_path: str, log_callback: Callable) -> List[str]:
        """辅助方法：确定需要扫描的目录列表。"""
        # 1. 如果指定了有效自定义路径，直接返回该路径
        if custom_path and custom_path.strip() and custom_path != root_path:
            return [custom_path]

        # 2. 否则动态扫描根目录下的所有子目录
        log_callback(f"未指定具体路径，正在动态扫描 {root_path} 下的所有目录...")
        try:
            # 3. 获取远程路径选项
            options = self.fetch_remote_path_options(root_path, log_callback)
            # 4. 提取有效路径值（排除根目录自身）
            return [
                opt["value"] for opt in options
                if opt["value"] != root_path
            ]
        except Exception as e:
            # 5. 异常处理
            log_callback(f"动态目录发现失败: {e}")
            return []

    def _scan_dirs_and_fetch_files(self, dirs: List[str], processor: Callable[[Dict, str], Dict], log_callback: Callable) -> List[Dict[str, Any]]:
        """通用模版方法：遍历目录 -> 下载列表 -> 处理文件 -> 排序。"""
        # 1. 检查目录列表是否为空
        if not dirs:
            return []

        all_processed_files = []
        # 2. 遍历每个目录
        for remote_dir in dirs:
            log_callback(f"正在扫描目录: {remote_dir} ...")
            try:
                # 3. 获取该目录下的原始文件列表
                raw_files = self.service.get_remote_file_list(remote_dir)
            except Exception as e:
                log_callback(f"扫描目录 {remote_dir} 失败: {str(e)}")
                continue

            # 4. 遍历并处理每个文件
            for raw_file in raw_files:
                if raw_file.get("is_dir"):
                    continue

                # 5. 调用传入的处理器进行格式化
                processed = processor(raw_file, remote_dir)
                if processed:
                    all_processed_files.append(processed)

        # 6. 按创建时间倒序排列结果
        all_processed_files.sort(key=lambda x: x.get("create_time", ""), reverse=True)
        return all_processed_files

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

    def fetch_remote_path_options(self, base_path: str, log_callback: Callable[[str], None] = None) -> List[Dict[str, Any]]:
        """
        获取远程目录的下拉选项（递归查找所有叶子目录）。
        """
        # 1. 初始化回调
        if not log_callback:
            log_callback = lambda msg: None

        # 2. 检查连接状态
        if not self.is_connected():
            return []

        tabs = []

        # 3. 添加默认的“全部”选项
        tabs.append({
            "label": base_path,
            "value": base_path,
            "name": "ALL",
            "protocol": "ALL"
        })

        try:
            # 4. 扫描根路径获取第一层目录（用于 Protocol/Group 分组）
            groups = self.service.get_remote_file_list(base_path)
        except Exception as e:
            log_callback(f"无法扫描路径 {base_path}: {e}")
            return []

        if not groups:
             return tabs

        # 5. 遍历第一层目录
        for g in groups:
            # 忽略文件，只处理文件夹
            if not g.get("is_dir"):
                continue

            g_name = g.get("name")
            g_path = g.get("path")

            # 6. 从该层开始递归寻找所有叶子目录
            leaves = self._find_leaf_dirs_recursive(g_path)

            # 7. 将找到的叶子目录加入选项列表
            if leaves:
                for leaf_path in leaves:
                    tabs.append({
                        "label": leaf_path,
                        "value": leaf_path,
                        "name": leaf_path,
                        "protocol": g_name # 保持所属的第一层分组名
                    })
            else:
                # 8. 兜底处理
                tabs.append({
                    "label": g_path,
                    "value": g_path,
                    "name": g_name,
                    "protocol": g_name
                })

        # 9. 按路径名称排序
        tabs.sort(key=lambda x: x["label"])
        return tabs

    def _find_leaf_dirs_recursive(self, current_path: str, current_depth: int = 0, max_depth: int = 5) -> List[str]:
        """递归查找包含文件的有效数据目录（叶子节点或中间有效节点）。"""
        # 1. 检查递归深度限制
        if current_depth > max_depth:
            return [current_path]

        try:
            # 2. 获取当前目录内容
            entries = self.service.get_remote_file_list(current_path)
        except Exception:
            return [current_path]

        # 3. 分离文件和子目录
        sub_dirs = []
        files = []
        for e in entries:
            if e.get("is_dir"):
                sub_dirs.append(e)
            else:
                files.append(e)

        results = []

        # 4. 如果包含文件，当前目录视为有效数据源
        if files:
            results.append(current_path)

        # 5. 如果是空目录（无文件且无子目录），也包含进去
        if not sub_dirs and not files:
            results.append(current_path)

        # 6. 递归处理子目录
        for d in sub_dirs:
            # 递归结果合并
            children_result = self._find_leaf_dirs_recursive(d.get("path"), current_depth + 1, max_depth)
            results.extend(children_result)

        return results

    def fetch_bus_tabs(self, log_callback: Callable[[str], None] = None) -> List[Dict[str, Any]]:
        """获取总线数据的 Tab 选项列表（兼容旧接口）。"""
        # 1. 调用通用方法获取总线根目录下的选项
        return self.fetch_remote_path_options("/bigdatadb/eth", log_callback)

    def fetch_bus_file_list(self, log_callback: Callable[[str], None] = None, tab_path: str | None = None) -> List[Dict[str, Any]]:
        """获取总线数据文件列表。"""
        # 1. 初始化回调
        if not log_callback:
            log_callback = lambda msg: None

        # 2. 检查连接状态
        if not self.is_connected():
            log_callback("⚠️ 设备未连接，无法获取总线数据列表。")
            return []

        # 3. 确定扫描目录
        dirs_to_scan = self._resolve_scan_dirs(
            root_path=self.BUS_ROOT,
            custom_path=tab_path,
            log_callback=log_callback
        )

        # 4. 定义 Bus 文件处理器
        def bus_processor(raw_file, dir_path):
            # 推断 protocol
            # 路径: /bigdatadb/eth/GROUP/SESSION/file -> proto=GROUP
            parts = dir_path.strip("/").split("/")
            proto = "Unknown"
            if len(parts) >= 3 and parts[1] == "eth":
                proto = parts[2]
            return self._process_bus_file(proto, dir_path, raw_file)

        # 5. 执行扫描
        return self._scan_dirs_and_fetch_files(dirs_to_scan, bus_processor, log_callback)

    def _process_bus_file(self, proto: str, tab_path: str, raw_file: Dict[str, Any]) -> Dict[str, Any]:
        """处理总线文件，构造业务对象。"""
        # 1. 获取基本信息和元数据
        filename = raw_file.get("name", "")
        meta = self._parse_filename_metadata(filename)

        # 2. 确定 APPID/Proto
        appid = meta["appid"]
        if not appid:
            appid = proto

        # 3. 确定创建时间
        create_time = meta["create_time"]
        if not create_time:
            old_meta = self._parse_bus_filename(filename)
            create_time = old_meta["create_time"] or raw_file.get("mtime", "")

        # 4. 构建业务对象
        return self._build_file_record(
            filename=filename,
            path=f"{tab_path}/{filename}",
            raw_file=raw_file,
            appid=appid,
            create_time=create_time
        )

    def _parse_bus_filename(self, filename: str) -> Dict[str, str]:
        """解析旧版总线文件名中的时间信息。"""
        meta = {"create_time": ""}
        # 1. 正则匹配时间戳 (YYYYMMDD_HHMMSS)
        m = re.search(r"_(\d{8}_\d{6})(?:\.[^.]+)?$", filename)
        if m:
            meta["create_time"] = m.group(1)
        return meta

