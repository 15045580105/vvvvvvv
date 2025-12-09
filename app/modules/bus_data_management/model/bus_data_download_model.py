"""
@FileName：bus_data_download_model.py
@Description：总线数据下载模型
@Author：QinHao
@Time：2025/12/9 14:58
@Department：PTV_AT
"""
from dataclasses import dataclass
from typing import List, Dict, Any

from PyQt5.QtCore import pyqtSignal

from app.core.base_model import BaseModel


@dataclass
class PageResult:
    page: int
    page_size: int
    page_count: int
    total: int
    rows: List[Dict[str, Any]]


class BusDataDownloadModel(BaseModel):
    """总线数据下载模型，支持简单过滤和分页。"""

    dataChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_rows: List[Dict[str, Any]] = []
        self._filtered_rows: List[Dict[str, Any]] = []
        self.page = 1
        self.page_size = 10
        # 过滤条件
        self._filter: Dict[str, Any] = {
            "tab_kw": "",
            "type_kw": "",
            "name_kw": "",
            "status": "全部",
            "date_from": None,
            "date_to": None,
        }
        # 初始化一些模拟数据
        self.load_mock()

    # ---- 对外 API ----
    def load_mock(self):
        """加载一些模拟数据。后续可替换为真实查询。"""
        self._all_rows = []
        for i in range(1, 51):
            self._all_rows.append({
                "filename": f"bus_data_{i:03d}.blf",
                "path": f"/capture/session_{(i - 1)//10 + 1}",
                "appid": f"TAB{i%4}",   # 这里沿用 appid 字段名，视图只负责展示
                "size_kb": 128 + i * 5,
                "create_time": f"2025-12-09 10:{i:02d}:00",
                "modified_time": f"2025-12-09 11:{i:02d}:00",
                "progress": 0,
                "status": "等待",
            })
        self.apply_filter()

    def set_filter(self, criteria: Dict[str, Any]):
        self._filter.update(criteria or {})
        self.page = 1
        self.apply_filter()

    def set_page(self, page: int):
        self.page = max(1, int(page or 1))
        self.dataChanged.emit()

    def set_page_size(self, page_size: int):
        self.page_size = max(1, int(page_size or 10))
        self.page = 1
        self.dataChanged.emit()

    def get_page(self) -> PageResult:
        total = len(self._filtered_rows)
        if total == 0:
            return PageResult(page=1, page_size=self.page_size, page_count=1, total=0, rows=[])

        page_size = self.page_size
        page_count = (total + page_size - 1) // page_size
        page = min(max(1, self.page), page_count)

        start = (page - 1) * page_size
        end = min(start + page_size, total)
        rows = self._filtered_rows[start:end]
        return PageResult(page=page, page_size=page_size, page_count=page_count, total=total, rows=rows)

    # ---- 内部工具 ----
    def apply_filter(self):
        tab_kw = (self._filter.get("tab_kw") or "").strip().lower()
        type_kw = (self._filter.get("type_kw") or "").strip().lower()
        name_kw = (self._filter.get("name_kw") or "").strip().lower()
        status = self._filter.get("status") or "全部"

        def match(row: Dict[str, Any]) -> bool:
            if tab_kw and tab_kw not in str(row.get("path", "")).lower():
                return False
            if type_kw and type_kw not in str(row.get("appid", "")).lower():
                return False
            if name_kw and name_kw not in str(row.get("filename", "")).lower():
                return False
            if status != "全部" and str(row.get("status", "")).strip() != status:
                return False
            # 简化：时间区间不做严格判断，可按需要扩展
            return True

        self._filtered_rows = [r for r in self._all_rows if match(r)]
        self.dataChanged.emit()
