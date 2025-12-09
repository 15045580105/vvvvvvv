import random
from dataclasses import dataclass
from typing import List, Dict, Any

from PyQt5 import QtCore

from app.core.base_model import BaseModel


@dataclass
class PageResult:
    rows: List[Dict[str, Any]]
    page: int
    page_count: int
    total: int
    page_size: int


class LogDownloadModel(BaseModel):
    """日志下载模型

    使用字典结构来描述每条日志文件，字段包括：
    - filename: 文件名
    - path: 路径
    - appid: APPID
    - size_kb: 大小（KB）
    - create_time: 创建时间
    - modified_time: 修改时间
    - progress: 下载进度（0-100）
    - status: 状态（等待/下载中/已完成/失败）
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.files: List[Dict[str, Any]] = []
        self.page: int = 1
        self.page_size: int = 10
        self.filter_criteria: Dict[str, Any] = {}
        self.load_mock()

    # ---- 数据源 ----
    def load_mock(self):
        """加载一些模拟数据，供界面展示。"""
        base_path_app = "/var/logs/app/"
        base_path_err = "/var/logs/error/"

        self.files = [
            {
                "filename": "system.log",
                "path": base_path_app,
                "appid": "APP001",
                "size_kb": 2400,  # 约 2.4 MB
                "create_time": "2024-11-19 10:00:00",
                "modified_time": "2024-11-19 14:30:22",
                "progress": 100,
                "status": "已完成",
            },
            {
                "filename": "diagnostic_trace_001.log",
                "path": base_path_app,
                "appid": "APP001",
                "size_kb": 15800,  # 约 15.8 MB
                "create_time": "2024-11-19 12:00:00",
                "modified_time": "2024-11-19 13:15:10",
                "progress": 60,
                "status": "下载中",
            },
            {
                "filename": "error_dump_20241119.log",
                "path": base_path_err,
                "appid": "APP002",
                "size_kb": 8200,  # 约 8.2 MB
                "create_time": "2024-11-19 11:30:00",
                "modified_time": "2024-11-19 12:45:33",
                "progress": 0,
                "status": "等待",
            },
            {
                "filename": "network_status.log",
                "path": base_path_app,
                "appid": "APP003",
                "size_kb": 1100,
                "create_time": "2024-11-19 09:10:00",
                "modified_time": "2024-11-19 11:20:15",
                "progress": 100,
                "status": "已完成",
            },
            {
                "filename": "app_performance_data.log",
                "path": base_path_app,
                "appid": "APP001",
                "size_kb": 5600,
                "create_time": "2024-11-19 08:30:00",
                "modified_time": "2024-11-19 10:55:42",
                "progress": 25,
                "status": "下载中",
            },
        ]

        # 通知视图刷新
        self.dataChanged.emit()

    def set_files(self, files: List[Dict[str, Any]]):
        """外部设置文件列表（若将来改为真实数据源可复用此接口）。"""
        self.files = [self._normalize(it) for it in files]
        self.page = 1
        self.dataChanged.emit()

    # ---- 过滤与分页 API ----
    def set_filter(self, criteria: Dict[str, Any]):
        """设置过滤条件，不立即分页，分页在 get_page 时进行。"""
        self.filter_criteria = criteria or {}
        # 重置到第一页
        self.page = 1
        self.dataChanged.emit()

    def set_page_size(self, page_size: int):
        self.page_size = max(1, int(page_size) or 1)
        self.page = 1
        self.dataChanged.emit()

    def set_page(self, page: int):
        # 控制在合法范围内，具体合法性在 get_page 里计算
        self.page = max(1, int(page) or 1)
        self.dataChanged.emit()

    def get_page(self, page: int | None = None) -> PageResult:
        """根据当前过滤条件和分页参数返回一页数据。"""
        if page is not None:
            self.page = max(1, int(page) or 1)

        filtered = [
            self._normalize(it)
            for it in self.files
            if self._match_item(it, self.filter_criteria)
        ]

        total = len(filtered)
        page_size = self.page_size
        page_count = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(self.page, page_count))

        start = (page - 1) * page_size
        end = min(start + page_size, total)
        rows = filtered[start:end]

        return PageResult(rows=rows, page=page, page_count=page_count, total=total, page_size=page_size)

    # ---- 内部辅助 ----
    def _normalize(self, it: Dict[str, Any]) -> Dict[str, Any]:
        """将任意来源的数据统一成视图使用的字段结���。"""
        if not isinstance(it, dict):
            try:
                seq = list(it)
            except Exception:
                seq = []
            it = {
                "filename": seq[0] if len(seq) > 0 else "",
                "path": seq[1] if len(seq) > 1 else "",
                "appid": seq[2] if len(seq) > 2 else "",
                "size_kb": seq[3] if len(seq) > 3 else "",
                "create_time": seq[4] if len(seq) > 4 else "",
                "modified_time": seq[5] if len(seq) > 5 else "",
                "progress": seq[6] if len(seq) > 6 else 0,
                "status": seq[7] if len(seq) > 7 else "等待",
            }

        return {
            "filename": it.get("filename") or it.get("name") or "",
            "path": it.get("path", ""),
            "appid": it.get("appid") or it.get("app_id") or "",
            "size_kb": it.get("size_kb") or it.get("size") or it.get("filesize") or "",
            "create_time": it.get("create_time") or it.get("ctime") or it.get("created_at") or "",
            "modified_time": it.get("modified_time") or it.get("mtime") or it.get("time") or "",
            "progress": int(it.get("progress") or 0),
            "status": it.get("status") or "等待",
        }

    def _match_item(self, it: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
        """根据给定 criteria 判断一条记录是否匹配。"""
        crit = criteria or {}
        path_kw = (crit.get("path_kw") or "").strip().lower()
        app_kw = (crit.get("app_kw") or "").strip().lower()
        name_kw = (crit.get("name_kw") or "").strip().lower()
        status_sel = crit.get("status") or "全部"
        date_from = crit.get("date_from")  # 可以是 QDateTime 或 None
        date_to = crit.get("date_to")

        item = self._normalize(it)
        filename = item["filename"]
        path = item["path"]
        appid = item["appid"]
        size_kb = str(item["size_kb"])
        create_time = item["create_time"]
        modified_time = item["modified_time"]
        status = item["status"] or "等待"

        # 时间过滤：仅当传入的是 QDateTime 且有意义时生效
        if isinstance(date_from, QtCore.QDateTime) and isinstance(date_to, QtCore.QDateTime):
            try:
                dt = QtCore.QDateTime.fromString(create_time, "yyyy-MM-dd HH:mm:ss")
                if dt.isValid():
                    if dt < date_from or dt > date_to:
                        return False
            except Exception:
                pass

        # 状态过滤
        if status_sel and status_sel != "全部" and status != status_sel:
            return False

        # 关键字过滤
        if path_kw and path_kw not in path.lower():
            return False
        if app_kw and app_kw not in appid.lower():
            return False
        if name_kw and name_kw not in filename.lower():
            return False

        return True

    def random_speed(self) -> str:
        """保留原来的随机速度方法，后续如要在视图里展示下载速度可以继续使用。"""
        return f"{random.uniform(0.5, 5.0):.1f} MB/s"
