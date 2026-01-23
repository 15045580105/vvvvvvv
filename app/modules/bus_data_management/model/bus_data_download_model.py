"""
@FileName：bus_data_download_model.py
@Description：总线数据下载模型
@Author：QinHao
@Time：2025/12/9 14:58
@Department：PTV_AT
"""
from dataclasses import dataclass
from typing import List, Dict, Any
import datetime

from PyQt5.QtCore import pyqtSignal, QAbstractTableModel, Qt

from app.core.base_model import BaseModel


@dataclass
class PageResult:
    page: int
    page_size: int
    page_count: int
    total: int
    rows: List[Dict[str, Any]]

# Qt表格数据展示
class BusDataTableModel(QAbstractTableModel):
    """自定义表格模型"""
    def __init__(self, rows=None, parent=None):
        super().__init__(parent)
        self._rows = rows if rows is not None else []
        self._headers = ["", "序号", "FileName", "Path", "Type", "Size(KB)", "CreateTime", "ModifiedTime", "下载进度", "状态", "操作"]
        self._checks = {}  # {row_index: bool}

    def set_headers(self, headers: List[str]):
        """Optional: allow the View to override header text (presentation concern)."""
        if not headers:
            return
        self._headers = list(headers)
        # notify header repaint
        self.headerDataChanged.emit(Qt.Horizontal, 0, len(self._headers) - 1)

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        self._checks = {}
        self.endResetModel()

    def get_rows(self):
        return self._rows

    def rowCount(self, parent=None):
        return len(self._rows)

    def columnCount(self, parent=None):
        return len(self._headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        item = self._rows[row]

        if role == Qt.DisplayRole:
            if col == 1: return str(item.get("_seq_idx", row + 1))
            if col == 2: return item.get("filename", "")
            if col == 3: return item.get("path", "")
            if col == 4: return item.get("appid", "")
            if col == 5: return item.get("size_kb", "")
            if col == 6: return item.get("create_time", "")
            if col == 7: return item.get("modified_time", "")
            if col == 8:
                pct = item.get("progress", 0)
                speed = item.get("transfer_rate", "")
                status = item.get("status", "")
                if status == "下载中" and speed:
                    return f"{pct}% ({speed})"
                return f"{pct}%"
            if col == 9: return item.get("status", "")
            return ""

        if role == Qt.CheckStateRole and col == 0:
            return Qt.Checked if self._checks.get(row, False) else Qt.Unchecked

        if role == Qt.TextAlignmentRole:
            # Align center for most columns except filename/path maybe?
            # Original code: 1, 4, 5, 6, 7, 8, 9, 10 aligned center.
            if col in [0, 1, 4, 5, 6, 7, 8, 9, 10]:
                return Qt.AlignCenter
            return Qt.AlignLeft | Qt.AlignVCenter

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.CheckStateRole and index.column() == 0:
            self._checks[index.row()] = (value == Qt.Checked)
            self.dataChanged.emit(index, index, [role])
            return True
        return False

    def select_all(self, checked: bool):
        """Batch update selection state"""
        self.beginResetModel()
        if checked:
            self._checks = {i: True for i in range(len(self._rows))}
        else:
            self._checks = {}
        self.endResetModel()

    # Optional alias for shared header controller
    def set_all_checked(self, checked: bool):
        self.select_all(checked)

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 0:
            f |= Qt.ItemIsUserCheckable
        return f

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            if section == 0:
                return ""
            return self._headers[section]
        return None

    def update_row_progress(self, row_idx, status, progress, speed):
        """单行更新状态"""
        if 0 <= row_idx < len(self._rows):
            item = self._rows[row_idx]
            item["status"] = status
            item["progress"] = progress
            item["transfer_rate"] = speed
            # Refresh columns 8 (Progress) and 9 (Status)
            tl = self.index(row_idx, 8)
            br = self.index(row_idx, 9)
            self.dataChanged.emit(tl, br, [Qt.DisplayRole])

# 总线数据下载业务逻辑
class BusDataDownloadModel(BaseModel):
    """总线数据下载模型，支持简单过滤和分页。"""

    dataChanged = pyqtSignal()
    # Path, Status, Progress, Speed
    progressChanged = pyqtSignal(str, str, int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_rows: List[Dict[str, Any]] = []
        self._filtered_rows: List[Dict[str, Any]] = []
        self.page = 1
        self.page_size = 1000

        # 排序状态
        self.sort_column_idx = -1
        self.sort_order = 0 # 0: Asc, 1: Desc (Qt values)

        # 缓存 Type 列表
        self.unique_types: List[str] = []

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
        # self.load_mock()

    # ---- 对外 API ----
    def set_file_list(self, files: List[Dict[str, Any]]):
        """设置文件列表数据"""
        self._all_rows = []
        unique_types = set()

        for item in files:
            # 兼容处理状态
            status = item.get("status", "未下载")
            appid = item.get("appid", "")
            if appid:
                unique_types.add(appid)

            # 格式化时间：create_time 缺省秒补00，modified_time 缺省秒补59
            c_time = self._format_date_str(item.get("create_time"), default_ss="00")
            m_time = self._format_date_str(item.get("modified_time"), default_ss="59")

            self._all_rows.append({
                "filename": item.get("filename", ""),
                "path": item.get("path", ""),
                "appid": appid,
                "size_kb": item.get("size_kb", ""),
                "create_time": c_time,
                "modified_time": m_time,
                "progress": item.get("progress", 0),
                "status": status,
                "raw_size": item.get("raw_size", 0),
            })

        self.unique_types = sorted(list(unique_types))
        self.apply_filter()
        self.dataChanged.emit()

    def _format_date_str(self, raw_val, default_ss="00") -> str:
        """
        格式化时间字符串为 yyyyMMdd_HHmmss。
        1. 尝试解析 float 时间戳
        2. 尝试解析英文月份格式 (Jun 13 00:39)
        3. 提取所有数字处理 yyyyMMddHHmm (12位) 和 yyyyMMddHHmmss (14位+)
        """
        s = str(raw_val).strip() if raw_val is not None else ""
        if not s:
            return ""

        # 1. 尝试纯数字时间戳 (包括浮点数字符串)
        try:
            # 简单判断: 如果能转 float 且值在合理时间戳范围 (2001-2096年)
            val = float(s)
            if 1000000000 <= val <= 4000000000:
                dt = datetime.datetime.fromtimestamp(val)
                return dt.strftime("%Y%m%d_%H%M%S")
        except ValueError:
            pass

        # 2. 尝试解析特殊格式: "Jun 13 00:39" (ls -l 风格)
        # 这种格式通常缺少年份和秒。
        # 简单的手动解析以避免 locale 问题
        month_map = {
            "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
            "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"
        }

        parts = s.split()
        # 匹配 "Jun 13 00:39" -> ["Jun", "13", "00:39"] len=3
        # 匹配 "Jun 13 2025" -> ["Jun", "13", "2025"] len=3 (如果是旧文件，显示年份)
        if len(parts) >= 3 and parts[0] in month_map:
            try:
                mm = month_map[parts[0]]
                dd = parts[1]

                # 检查第三部分是时间还是年份
                part3 = parts[2]

                # 情况A: "Jun 13 00:39" (今年)
                if ":" in part3:
                    hh, min_ = part3.split(":")
                    # 估算年份
                    now = datetime.datetime.now()
                    current_year = now.year

                    # 构造日期对象进行比较
                    # 注意：这里只是为了算年份，最终字符串拼装不需要 datetime 对象
                    # 如果当前月份是1月，文件月份是12月，说明是去年的
                    if now.month < int(mm):
                         current_year -= 1

                    # 格式化
                    return f"{current_year}{mm}{dd.zfill(2)}_{hh.zfill(2)}{min_.zfill(2)}{default_ss}"

                # 情况B: "Jun 13 2024" (非今年)
                elif len(part3) == 4 and part3.isdigit():
                    yy = part3
                    return f"{yy}{mm}{dd.zfill(2)}_000000" # 如果没有时间，默认为0点？或者保留原样？
                    # ls -l 显示年份时，通常意味着没有具体时间显示（或者需要其他参数）
                    # 这里暂且补 000000
            except:
                pass

        # 3. 提取数字 (解决各种分隔符 - / : . T space _ 等)
        digits = "".join(filter(lambda c: c.isdigit(), s))

        # 情况: yyyyMMddHHmm (12位) -> 补秒
        if len(digits) == 12:
            return f"{digits[:8]}_{digits[8:12]}{default_ss}"

        # 情况: yyyyMMddHHmmss... (14位及以上，含毫秒) -> 截取前14位
        if len(digits) >= 14:
            return f"{digits[:8]}_{digits[8:14]}"

        return s

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
                "status": "未下载",
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
        # 与 View 的分页候选项一致；兜底也用 500，避免解析失败回到 10
        self.page_size = max(1, int(page_size or 500))
        self.page = 1
        self.dataChanged.emit()

    def set_sort(self, column_idx: int, order: int):
        """设置排序并应用"""
        self.sort_column_idx = column_idx
        self.sort_order = order
        self.apply_sort()
        self.dataChanged.emit()

    def apply_sort(self):
        """对 _filtered_rows 进行排序"""
        if self.sort_column_idx < 0:
            return

        # 列索引映射到字段名 (View 中: 0=Chk, 1=Idx, 2=Name, 3=Path, 4=App, 5=Size, 6=CT, 7=MT, 8=Prog, 9=Stat, 10=Op)
        # 仅支持对部分字段排序
        col_map = {
            2: "filename",
            3: "path",
            4: "appid",
            5: "raw_size", # Sort by raw size bytes, not string KB
            6: "create_time",
            7: "modified_time",
            8: "progress",
            9: "status"
        }

        key = col_map.get(self.sort_column_idx)
        if not key:
            return

        reverse = (self.sort_order == 1) # 1 is Descending in Qt (Qt.DescendingOrder = 1)

        def sort_key(item):
            val = item.get(key)
            if val is None:
                return ""
            return val

        self._filtered_rows.sort(key=sort_key, reverse=reverse)

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

    def get_unique_types(self) -> List[str]:
        return self.unique_types

    def get_file_by_row(self, row_index: int) -> Dict[str, Any] | None:
        """Get file object by current page row index"""
        page_result = self.get_page()
        if 0 <= row_index < len(page_result.rows):
            return page_result.rows[row_index]
        return None

    def get_file_by_path(self, path: str) -> Dict[str, Any] | None:
        """Get file object by path"""
        for row in self._all_rows:
            if row.get("path") == path:
                return row
        return None

    def get_row_index_by_path(self, path: str) -> int:
        """获取某路径在当前过滤页中的行索引（用于局部刷新）"""
        pr = self.get_page()
        for i, row in enumerate(pr.rows):
            if row.get("path") == path:
                return i
        return -1

    def update_file_status(self, path: str, status: str, progress: int = 0, speed: str = ""):
        # 因为 _all_rows 是列表，需要遍历查找。
        # 如果数据量大，应该建立 dict 索引。鉴于 context 里 LogDownloadModel 用了 file_map，这里做简单查找
        found = False
        for row in self._all_rows:
            if row.get("path") == path:
                row["status"] = status
                row["progress"] = progress
                row["transfer_rate"] = speed
                found = True
                break

        if found:
            # 只有当状态发生质变（如完成、失败）或者被明确要求时，才触发全量 dataChanged?
            # 不，全量 dataChanged 重绘成本太高。
            # 我们发射专门的信号。
            self.progressChanged.emit(path, status, progress, speed)

            # 如果需要兼容旧逻辑或其他监听者，可能需要评估。
            # 但这里我们明确为了优化性能，避免 dataChanged。
            # 如果是状态变为 "已完成"，可能需要刷新一下以确保排序等正确？
            # 暂时只发 progressChanged，依靠 View 的局部更新。


    # ---- 内部工具 ----
    def apply_filter(self):
        tab_kw = (self._filter.get("tab_kw") or "").strip().lower()
        type_kw = (self._filter.get("type_kw") or "").strip()
        name_kw = (self._filter.get("name_kw") or "").strip().lower()
        status = self._filter.get("status") or "全部"

        date_from_qt = self._filter.get("date_from")
        date_to_qt = self._filter.get("date_to")

        # 是否启用时间过滤：由 date_from/date_to 是否为 None 决定
        time_filter_enabled = bool(date_from_qt) or bool(date_to_qt)

        s_from = ""
        s_to = ""
        if time_filter_enabled:
            if date_from_qt:
                s_from = date_from_qt.toString("yyyyMMdd_HHmmss")
            if date_to_qt:
                s_to = date_to_qt.toString("yyyyMMdd_HHmmss")

        def match(row: Dict[str, Any]) -> bool:
            if tab_kw and tab_kw not in str(row.get("path", "")).lower():
                return False
            if type_kw and type_kw != str(row.get("appid", "")):
                return False
            if name_kw and name_kw not in str(row.get("filename", "")).lower():
                return False
            if status != "全部" and str(row.get("status", "")).strip() != status:
                return False

            if time_filter_enabled:
                ct_raw = str(row.get("create_time", "")).strip()
                if not ct_raw:
                    return False

                ct_norm = self._format_date_str(ct_raw, default_ss="00")
                if not ct_norm:
                    return False

                if s_from and ct_norm < s_from:
                    return False
                if s_to and ct_norm > s_to:
                    return False

            return True

        self._filtered_rows = [r for r in self._all_rows if match(r)]
        self.apply_sort()
        self.dataChanged.emit()
