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
    LOG_DIRS = ["/log/CCUA/app", "/log/CCUA/core"]
    BUS_BASE_DIRS = [
        {"path": "/bigdatadb/eth/SOMEIP", "protocol": "SOMEIP"},
        {"path": "/bigdatadb/eth/CAN", "protocol": "CAN"},
        # 默认扫描 /bigdatadb/eth
    ]

    def __init__(self):
        self.service = FileTransferService()

    def connect(self, host: str, user: str, pass_: str) -> bool:
        """连接设备"""
        if self.service.is_connected():
            # 已经连接则直接返回成功
            return True
        # 进行连接
        return self.service.connect_device(host, 22, user, pass_)

    def is_connected(self) -> bool:
        return self.service.is_connected()

    def fetch_log_list(self, log_callback: Callable[[str], None] = None, custom_path: str = None) -> List[Dict[str, Any]]:
        """
        获取所有日志文件的完整列表（经过业务处理）。
        如果指定了 custom_path，则仅扫描该目录；否则扫描默认的 LOG_DIRS。
        """
        if not log_callback:
            log_callback = lambda msg: None

        all_processed_files = []

        # 确定要扫描的目录列表
        if custom_path:
            dirs_to_scan = [custom_path]
        else:
            dirs_to_scan = self.LOG_DIRS

        for remote_dir in dirs_to_scan:
            log_callback(f"正在扫描目录: {remote_dir} ...")

            # 1. 调用底层服务获取原始文件列表
            try:
                raw_files = self.service.get_remote_file_list(remote_dir)
            except Exception as e:
                log_callback(f"扫描目录 {remote_dir} 失败: {str(e)}")
                continue

            # 2. 应用业务规则：过滤和解析
            for raw_file in raw_files:
                # 过滤掉文件夹，只看文件
                if raw_file.get("is_dir"):
                    continue

                # 解析元数据
                processed = self._process_log_file(raw_file)
                all_processed_files.append(processed)

        # 3. 按时间倒序排列（最近的日志在前）
        all_processed_files.sort(key=lambda x: x["create_time"], reverse=True)

        return all_processed_files

    def download_file(self, remote_path: str, local_path: str, progress_callback=None):
        """下载单个文件"""
        return self.service.download_file(remote_path, local_path, progress_callback)

    def _process_log_file(self, raw_file: Dict[str, Any]) -> Dict[str, Any]:
        """
        核心业务逻辑：将原始文件信息转换为业务对象
        """
        filename = raw_file.get("name", "")
        # 解析文件名中的元数据
        meta = self._parse_filename_metadata(filename)

        # 优先使用文件名里的时间，如果没有则使用文件系统修改时间
        display_time = meta["create_time"] if meta["create_time"] else raw_file.get("mtime", "")

        return {
            "filename": filename,
            "path": raw_file.get("path", ""),
            "appid": meta["appid"],
            "size_kb": raw_file.get("size_kb", ""),
            "create_time": display_time,
            "modified_time": raw_file.get("mtime", ""),
            # 初始状态
            "progress": 0,
            "status": "未下载",
            # 保留原始大小用于计算
            "raw_size": raw_file.get("size", 0)
        }

    def _parse_filename_metadata(self, filename: str) -> Dict[str, str]:
        """Delegate filename parsing to the centralized helper.

        Returns a minimal dict compatible with the previous internal shape
        (keys: 'appid', 'create_time' both strings). The centralized parser may
        return additional fields; we discard them to keep this method's contract
        unchanged.
        """
        parsed = parse_filename_metadata(filename)
        return {
            "appid": parsed.get("appid") or "",
            "create_time": parsed.get("create_time") or "",
        }

    def fetch_bus_tabs(self, log_callback: Callable[[str], None] = None) -> List[Dict[str, Any]]:
        """
        获取总线数据的 Tab 选项列表（下拉框内容来源）。

        逻辑解释：
        此函数并不返回文件，而是返回“去哪里找文件”的目录列表。
        它扫描 /bigdatadb/eth 目录：
        1. 如果一级目录（如 SOMEIP）下还有子目录（如 Session_1），则生成选项 "SOMEIP/Session_1"，这种情况下数据在子目录里。
        2. 如果一级目录（如 CAN）下没有子目录（只有文件），则生成选项 "CAN"，这种情况下数据就在一级目录里。
        """
        if not log_callback:
            log_callback = lambda msg: None

        if not self.is_connected():
            return []

        tabs = []
        base_eth = "/bigdatadb/eth"

        # Add the root "All" option requested by user
        tabs.append({
            "label": base_eth,
            "value": base_eth,
            "name": "ALL",
            "protocol": "ALL"
        })

        try:
            # 1. 第一步：扫描根路径 /bigdatadb/eth 获取所有协议组 (Group) 目录
            # 例如获取到: [{"name": "CAN", ...}, {"name": "SOMEIP", ...}]
            groups = self.service.get_remote_file_list(base_eth)
        except Exception as e:
            log_callback(f"无法根据 {base_eth} 获取协议列表: {e}")
            return []

        for g in groups:
            # 忽略文件，只处理文件夹
            if not g.get("is_dir"):
                continue

            g_name = g.get("name") # 例如 "SOMEIP"
            g_path = g.get("path") # 例如 "/bigdatadb/eth/SOMEIP"

            # 2. 第二步：深入扫描该协议目录下是否有子目录（Session目录）
            try:
                children = self.service.get_remote_file_list(g_path)
                # 过滤出里面的所有文件夹
                sub_dirs = [c for c in children if c.get("is_dir")]
            except Exception:
                sub_dirs = []

            # 3. 根据是否存在子目录来决定下拉选项的结构
            if sub_dirs:
                # 情况A：存在子目录 (复杂结构) -> 每个子目录作为一个独立的 Tab 选项
                # 修改：展示绝对路径 (e.g. "/bigdatadb/eth/SOMEIP/Session_1")
                for s in sub_dirs:
                    s_name = s.get("name")
                    s_path = s.get("path")
                    label = s_path # 使用绝对路径作为标签
                    tabs.append({
                        "label": label,    # 界面显示的文字
                        "value": s_path,   # 选中后去这个路径查文件
                        "name": label,
                        "protocol": g_name
                    })
            else:
                # 情况B：不存在子目录 (简单结构) -> 协议本身作为一个 Tab 选项
                # 修改：展示绝对路径 (e.g. "/bigdatadb/eth/CAN")
                label = g_path # 使用绝对路径作为标签
                tabs.append({
                    "label": label,  # 界面显示的文字
                    "value": g_path,
                    "name": g_name,
                    "protocol": g_name
                })

        # 按 label 字母顺序排序，方便用户查找
        tabs.sort(key=lambda x: x["label"])
        return tabs

    def fetch_bus_file_list(self, log_callback: Callable[[str], None] = None, tab_path: str | None = None) -> List[Dict[str, Any]]:
        """获取总线数据文件列表"""
        if not log_callback:
            log_callback = lambda msg: None

        if not self.is_connected():
            log_callback("⚠️ 设备未连接，无法获取总线数据列表。")
            return []

        files: List[Dict[str, Any]] = []

        # 确定需要扫描文件的目录列表
        dirs_to_scan = []

        if tab_path and tab_path != "/bigdatadb/eth":
            # 如果指定了 tab_path 且不是根目录，直接扫描该目录
            # tab_path 是由 fetch_bus_tabs 获取的 value，指向具体含有文件的目录
            dirs_to_scan.append(tab_path)
        else:
            # 如果未指定或指定为根目录，则执行自动发现逻辑 (与 fetch_bus_tabs 类似，但直接收集文件)
            base_eth = "/bigdatadb/eth"
            try:
                groups = self.service.get_remote_file_list(base_eth)
                for g in groups:
                    if not g.get("is_dir"): continue
                    g_path = g.get("path")

                    # 扫描组内容
                    try:
                        children = self.service.get_remote_file_list(g_path)
                        has_subdirs = False
                        for c in children:
                            if c.get("is_dir"):
                                has_subdirs = True
                                dirs_to_scan.append(c.get("path"))

                        # 如果没有子文件夹，或为了覆盖根目录文件?
                        # 假设如果作为 Group 存在，可能直接包含文件
                        # 简单策略：总是把 Group 本身也加入扫描?
                        # 或者仅当没有子文件夹时?
                        # 对应 fetch_bus_tabs 的逻辑：
                        if not has_subdirs:
                            dirs_to_scan.append(g_path)
                        # 注意：如果目录既有文件又有子文件夹，这里可能漏掉文件。
                        # 如果需要非常全面，应该始终扫描 dirs_to_scan.append(g_path)
                        # 但这可能导致重复或混乱（如果 g_path 很大）。
                        # 鉴于 fetch_bus_tabs 只在 !has_subdirs 时提供 TAB，保持一致。

                    except Exception:
                        pass
            except Exception:
                pass

        for d_path in dirs_to_scan:
            log_callback(f"正在扫描: {d_path} ...")
            try:
                entries = self.service.get_remote_file_list(d_path)
            except Exception as e:
                log_callback(f"扫描 {d_path} 失败: {e}")
                continue

            # 推断 protocol / appid
            # 路径: /bigdatadb/eth/GROUP/SESSION/file  -> APPID = GROUP
            # 路径: /bigdatadb/eth/GROUP/file          -> APPID = GROUP
            parts = d_path.strip("/").split("/")
            # parts 可能是 ['bigdatadb', 'eth', 'SOMEIP', 'Session1'] -> protocol=SOMEIP
            # parts 可能是 ['bigdatadb', 'eth', 'Other'] -> protocol=Other
            proto = "Unknown"
            if len(parts) >= 3 and parts[1] == "eth":
                proto = parts[2]

            for ent in entries:
                if ent.get("is_dir"):
                    continue
                processed = self._process_bus_file(proto, d_path, ent)
                files.append(processed)

        # 按时间倒序
        files.sort(key=lambda x: x.get("create_time", ""), reverse=True)
        return files

    def _process_bus_file(self, proto: str, tab_path: str, raw_file: Dict[str, Any]) -> Dict[str, Any]:
        filename = raw_file.get("name", "")
        # 复用日志的元数据解析逻辑（解析 APPID 和 CreateTime）
        meta = self._parse_filename_metadata(filename)

        # Type 字段使用解析出的 APPID，如果解析失败才使用 proto 作为兜底
        appid = meta["appid"]
        if not appid:
            appid = proto

        # 时间
        create_time = meta["create_time"]
        if not create_time:
            # 尝试旧的 bus filename 解析逻辑或者直接用 mtime
            old_meta = self._parse_bus_filename(filename)
            create_time = old_meta["create_time"] or raw_file.get("mtime", "")

        return {
            "filename": filename,
            "path": f"{tab_path}/{filename}",
            "appid": appid,
            "size_kb": raw_file.get("size_kb", ""),
            "create_time": create_time,
            "modified_time": raw_file.get("mtime", ""),
            "progress": 0,
            "status": "未下载",
            "raw_size": raw_file.get("size", 0),
        }

    def _parse_bus_filename(self, filename: str) -> Dict[str, str]:
        meta = {"create_time": ""}
        # 提取 20250612_145433 这种时间片段
        m = re.search(r"_(\d{8}_\d{6})(?:\.[^.]+)?$", filename)
        if m:
            meta["create_time"] = m.group(1)
        return meta

