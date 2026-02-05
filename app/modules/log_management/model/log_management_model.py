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
    - status: 状态（未下载/下载中/已下载/下载失败/已取消）
    """

    # 新增信号：path, status, progress, speed
    progressChanged = QtCore.pyqtSignal(str, str, int, str)

    def __init__(self, parent=None):
        """初始化日志下载模型，配置默认分页和排序参数。"""
        # 1. 调用父类初始化
        super().__init__(parent)
        # 2. 初始化数据存储
        self.files: List[Dict[str, Any]] = []
        self.file_map: Dict[str, Dict[str, Any]] = {}
        # 3. 初始化缓存过滤后的结果
        # 缓存过滤后的结果，避免每次 get_page 都重新过滤
        self.filtered_files: List[Dict[str, Any]] = []
        # 4. 初始化 APPID 缓存
        # 缓存 APPID 列表
        self.unique_appids: List[str] = []
        # 5. 初始化排序和分页参数
        self.sort_column: str = ""
        self.sort_order = QtCore.Qt.AscendingOrder
        self.page: int = 1
        #默认每页显示 1000 条
        self.page_size: int = 1000
        # 6. 初始化过滤条件
        self.filter_criteria: Dict[str, Any] = {}
        # self.load_mock() # Removed mock loading by default

    def set_file_list(self, new_file_list: List[Dict[str, Any]], notify: bool = True):
        """设置全量文件列表，并进行状态合并。

        参数:
            new_file_list: 来自 Manager 的完整文件列表（每项为 dict）
            notify: 是否在更新完成后发出 self.dataChanged 信号（默认为 True）。
                在某些场景（Controller 同时要更新 filter）可以设置为 False
                以避免产生两次重复的刷新。
        """
        # new_file_list 已经是 Manager 根据业务规则处理好的标准对象列表

        updated_map = {}
        unique_appids = set()

        # 1. 遍历新列表，合并旧状态并构建映射
        for item in new_file_list:
            path = item.get("path")
            if not path:
                continue

            # Check if exists to preserve status
            existing = self.file_map.get(path)
            if existing:
                item["status"] = existing.get("status", "未下载")
                item["progress"] = existing.get("progress", 0)
                # Keep speed if downloading
                if item["status"] == "下载中":
                    item["speed"] = existing.get("speed", "")

            updated_map[path] = item

            # 收集 APPID
            aid = item.get("appid")
            if aid:
                unique_appids.add(str(aid))

        # 2. 更新内部存储
        self.file_map = updated_map
        self.files = list(self.file_map.values())
        self.unique_appids = sorted(list(unique_appids))

        # 3. 立即应用过滤以更新缓存
        # Apply filter immediately to update cache
        self._apply_filter()

        # 4. 发送数据变更信号
        if notify:
            self.dataChanged.emit()

    def update_file_status(self, path: str, status: str, progress: int = 0, speed: str = ""):
        """更新单个文件的下载状态和进度。"""
        # 1. 检查文件是否存在
        if path in self.file_map:
            # 2. 更新状态和进度信息
            self.file_map[path]["status"] = status
            self.file_map[path]["progress"] = progress
            if speed:
                self.file_map[path]["speed"] = speed
            elif status in ["已下载", "下载失败", "已取消"]:
                # 完成态清空速度
                self.file_map[path]["speed"] = ""
            # 3. 改为发射进度信号，避免触发全量刷新导致 View 勾选丢失
            self.progressChanged.emit(path, status, progress, speed)

    def get_unique_appids(self) -> List[str]:
        """获取所有文件中不重复的 APPID 列表。"""
        # 1. 返回缓存的 APPID 列表
        return self.unique_appids

    def get_file_by_row(self, row_index: int) -> Dict[str, Any] | None:
        """根据当前页的行索引获取对应的文件对象。"""
        """Get file object by current page row index"""
        # use cached filtered result
        # 1. 计算全局索引
        start = (self.page - 1) * self.page_size
        actual_index = start + row_index
        # 2. 检查索引越界并返回数据
        if 0 <= actual_index < len(self.filtered_files):
            return self.filtered_files[actual_index]
        return None

    def get_file_by_path(self, path: str) -> Dict[str, Any] | None:
        """根据文件路径（唯一标识符）获取文件对象。"""
        """Get file object by path (stable identifier)"""
        # 1. 从映射表中查找并返回
        return self.file_map.get(path)

    # ---- 数据源 ----
    def load_mock(self):
        """加载一些模拟数据，供界面展示。"""
        # ... (mock data logic if needed, but we assume empty init usually)
        pass

    def set_files(self, files: List[Dict[str, Any]]):
        """外部设置文件列表（若将来改为真实数据源可复用此接口）。"""
        # 1. 委托给 set_file_list 处理
        self.set_file_list(files)

    # ---- 过滤与分页 API ----
    def set_filter(self, criteria: Dict[str, Any]):
        """设置过滤条件，并触发数据刷新。"""
        # 1. 更新过滤条件字典
        self.filter_criteria = criteria or {}
        # 2. 重置到第一页
        self.page = 1
        # 3. 执行过滤
        self._apply_filter()
        # 4. 通知视图刷新
        self.dataChanged.emit()

    def set_page_size(self, page_size: int):
        """设置每页显示的条数。"""
        # 1. 设置每页大小（最小为1）
        self.page_size = max(1, int(page_size) or 1)
        # 2. 重置到第一页
        self.page = 1
        # 3. 通知视图刷新
        self.dataChanged.emit()

    def set_page(self, page: int):
        """设置当前页码。"""
        # 1. 设置页码（控制在合法范围内，实际越界检查在 get_page）
        # 控制在合法范围内，具体合法性在 get_page 里计算
        self.page = max(1, int(page) or 1)
        # 2. 通知视图刷新
        self.dataChanged.emit()

    def set_sort(self, column: str, order: QtCore.Qt.SortOrder):
        """设置排序字段和顺序。"""
        # 1. 更新排序参数
        self.sort_column = column
        self.sort_order = order
        # 2. 重置到第一页
        # reset page to 1 when sort changes
        self.page = 1
        # 3. 重新应用过滤（排序在过滤后执行）
        self._apply_filter() # Filter applies sort at the end
        # 4. 通知视图刷新
        self.dataChanged.emit()

    def get_page(self, page: int | None = None) -> PageResult:
        """根据当前过滤条件和分页参数返回一页数据。"""
        # 1. 更新页码参数
        if page is not None:
            self.page = max(1, int(page) or 1)

        # 2. 计算分页信息
        total = len(self.filtered_files)
        page_size = self.page_size
        page_count = max(1, (total + page_size - 1) // page_size)

        # 3. 修正当前页码，防止超出范围
        self.page = max(1, min(self.page, page_count))

        # 4. 切片获取当前页数据
        start = (self.page - 1) * page_size
        end = min(start + page_size, total)
        rows = self.filtered_files[start:end]

        # 5. 返回分页结果对象
        return PageResult(rows=rows, page=self.page, page_count=page_count, total=total, page_size=page_size)

    def _apply_filter(self):
        """执行过滤操作，根据 criteria 更新 self.filtered_files。"""
        # 1. 根据条件筛选文件
        criteria = self.filter_criteria

        # 预先解析搜索条件
        path_kw = (criteria.get("path_kw") or "").strip().lower()
        name_kw = (criteria.get("name_kw") or "").strip().lower()
        app_kw = (criteria.get("app_kw") or "").strip()
        status_sel = criteria.get("status") or "全部"
        date_from = criteria.get("date_from")
        date_to = criteria.get("date_to")

        # 转换时间范围为 timestamp 以加速比较
        # 注意: QDateTime.toSecsSinceEpoch() 返回 int, 为了兼容 float timestamp, 我们都视为数字比较
        ts_from = date_from.toSecsSinceEpoch() if isinstance(date_from, QtCore.QDateTime) and date_from.isValid() else None
        ts_to = date_to.toSecsSinceEpoch() if isinstance(date_to, QtCore.QDateTime) and date_to.isValid() else None

        filtered = []
        for item in self.files:
            # 1. Status (Fastest check)
            if status_sel != "全部" and status_sel and item.get("status") != status_sel:
                continue

            # 2. AppID (Exact match)
            if app_kw != "全部" and app_kw and app_kw != str(item.get("appid", "")):
                continue

            # 3. Path/Name (Pre-calc lower check)
            if path_kw and path_kw not in item.get("_search_path", ""):
                continue
            if name_kw and name_kw not in item.get("_search_name", ""):
                continue

            # 4. Time range (Number compare)
            if ts_from is not None and ts_to is not None:
                f_create = item.get("_ts_create")
                f_mod = item.get("_ts_modified")

                # Logic: intersection
                f_start = f_create if f_create is not None else f_mod
                if f_start is None: continue

                f_end = f_mod if f_mod is not None else f_start

                # [f_start, f_end] vs [ts_from, ts_to]
                # intersection exists if not (end < from or start > to)
                if f_end < ts_from or f_start > ts_to:
                    continue

            filtered.append(item)

        # 2. 执行排序
        # Apply Sorting if active
        if self.sort_column:
             reverse = (self.sort_order == QtCore.Qt.DescendingOrder)
             # Map view column index/name to model field key
             key_map = {
                 "filename": lambda x: x["_search_name"], # use lower for case-insensitive sort
                 "path":     lambda x: x["_search_path"],
                 "appid":    lambda x: x["appid"],
                 "size_kb":  lambda x: x["_sort_size"],
                 "create_time": lambda x: x["_ts_create"] or 0,
                 "modified_time": lambda x: x["_ts_modified"] or 0,
             }

             key_func = key_map.get(self.sort_column)
             # 确保 sort stable
             if key_func:
                 filtered.sort(key=key_func, reverse=reverse)

        # 3. 更新过滤结果缓存
        self.filtered_files = filtered


    # ---- 内部辅助 ----
    @staticmethod
    def _parse_time_static(time_str: str) -> float | None:
        """静态解析时间返回时间戳(float)，用于快速过滤。失败返回 None。"""
        # 1. 简单尝试转换为浮点数时间戳
        if not time_str:
            return None
        # 简单尝试转 float
        try:
            return float(time_str)
        except ValueError:
            pass
        return None  # 更复杂的格式比较耗时，这里只处理最简单的 float timestamp

    @staticmethod
    def try_parse_datetime(time_str: str) -> QtCore.QDateTime:
        """尝试多种格式解析时间字符串，返回 QDateTime 对象。"""
        # 1. 判空
        if not time_str:
            return QtCore.QDateTime()

        # 2. 尝试 Compact 格式 (yyyyMMdd_HHmmss)
        # 0. 尝试 Compact 格式 (yyyyMMdd_HHmmss)
        dt = QtCore.QDateTime.fromString(time_str, "yyyyMMdd_HHmmss")
        if dt.isValid(): return dt

        # 3. 尝试标准格式
        # 1. 尝试标准格式
        dt = QtCore.QDateTime.fromString(time_str, "yyyy-MM-dd HH:mm:ss")
        if dt.isValid(): return dt

        # 4. 尝试 Unix 时间戳
        # 2. 尝试 Unix 时间戳
        try:
            ts = float(time_str)
            return QtCore.QDateTime.fromSecsSinceEpoch(int(ts))
        except (ValueError, TypeError):
            pass

        # 5. 尝试 ls -l 格式 (英文月份)
        # 3. 尝试 ls -l 格式 (英文月份，如 "Nov 19 14:30" 或 "Nov 19 2024")
        # 需要 English Locale
        locale = QtCore.QLocale(QtCore.QLocale.English)

        # 3a. MMM d HH:mm 或 MMM dd HH:mm (无年份)
        dt = locale.toDateTime(time_str, "MMM d HH:mm")
        if not dt.isValid():
            dt = locale.toDateTime(time_str, "MMM dd HH:mm")

        if dt.isValid():
            # 补全年份逻辑
            now = QtCore.QDateTime.currentDateTime()
            current_year = now.date().year()
            new_date = dt.date()
            new_date.setDate(current_year, new_date.month(), new_date.day())
            dt.setDate(new_date)
            # 如果得到的时间在未来且偏差较大，则减去一年
            if dt > now.addDays(2):
                new_date.setDate(current_year - 1, new_date.month(), new_date.day())
                dt.setDate(new_date)

            t = dt.time()
            t.setHMS(t.hour(), t.minute(), 59)
            dt.setTime(t)
            return dt

        # 3b. MMM d yyyy 或 MMM dd yyyy
        dt = locale.toDateTime(time_str, "MMM d yyyy")
        if not dt.isValid():
             dt = locale.toDateTime(time_str, "MMM dd yyyy")

        if dt.isValid():
            return dt

        return QtCore.QDateTime()

    @staticmethod
    def static_normalize(it: Any) -> Dict[str, Any]:
        """将任意来源的数据统一成标准结构，并进行格式化预处理。"""
        # 1. 检查是否已经是归一化数据
        if isinstance(it, dict) and it.get("_is_normalized"):
            return it

        # 2. 兼容元组/列表输入
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
                "status": seq[7] if len(seq) > 7 else "未下载",
            }

        # 3. 处理 Size(KB)
        raw_size = it.get("size_kb") or it.get("size") or it.get("filesize") or ""
        final_size_kb = ""
        sort_size = 0 # 用于排序的数值

        if isinstance(raw_size, (int, float)):
             # 假设数值型全是字节，转 KB
             sort_size = int(raw_size)
             final_size_kb = str(int(raw_size / 1024))
        elif isinstance(raw_size, str) and raw_size:
             # 如果包含单位，比如 "1024 KB" 或 "2 MB"
             s = raw_size.upper().replace(",", "")
             # 简单粗暴提取数字
             import re
             m = re.match(r"([\d\.]+)", s)
             if m:
                 val = float(m.group(1))
                 if "GB" in s: val *= 1024 * 1024 * 1024
                 elif "MB" in s: val *= 1024 * 1024
                 elif "KB" in s: val *= 1024
                 else: val /= 1 # 默认直接 parse 出来视为字节? 或者看上面逻辑 val /= 1024 是转KB
                 # 修正逻辑：上面原代码 val 视为字节。
                 # 假设 raw 是 "2048" (无单位)，通常视作字节。
                 # 如果 raw 是 "1 KB", val=1, 那么是 1024 字节
                 if "B" not in s and "KB" not in s and "MB" not in s:
                      # 纯数字字符串，视为字节
                      pass

                 # 统一转为字节存入 sort_size
                 sort_size = int(val)
                 final_size_kb = str(int(sort_size / 1024))
             else:
                 final_size_kb = raw_size

        # 4. 预处理搜索字段
        filename = it.get("filename") or it.get("name") or ""
        path = it.get("path", "")

        # 5. 预处理时间
        create_time_raw = it.get("create_time") or it.get("ctime") or it.get("created_at") or ""
        modified_time_raw = it.get("modified_time") or it.get("mtime") or it.get("time") or ""

        # 使用增强的解析逻辑
        dt_create = LogDownloadModel.try_parse_datetime(str(create_time_raw))
        dt_modified = LogDownloadModel.try_parse_datetime(str(modified_time_raw))

        create_time_str = dt_create.toString("yyyyMMdd_HHmmss") if dt_create.isValid() else str(create_time_raw)
        modified_time_str = dt_modified.toString("yyyyMMdd_HHmmss") if dt_modified.isValid() else str(modified_time_raw)

        # 补充 timestamp 用于排序
        ts_create = dt_create.toSecsSinceEpoch() if dt_create.isValid() else None
        ts_modified = dt_modified.toSecsSinceEpoch() if dt_modified.isValid() else None

        # 6. 返回标准化字典
        return {
            "filename": filename,
            "path": path,
            "appid": it.get("appid") or it.get("app_id") or "",
            "size_kb": final_size_kb,
            "create_time": create_time_str,
            "modified_time": modified_time_str,
            "progress": int(it.get("progress") or 0),
            "status": it.get("status") or "未下载",
            "speed": it.get("speed") or "",
            "_is_normalized": True,
            # 内部加速字段
            "_search_name": str(filename).lower(),
            "_search_path": str(path).lower(),
            "_ts_create": ts_create,
            "_ts_modified": ts_modified,
            "_sort_size": sort_size,
        }

class LogTableModel(QtCore.QAbstractTableModel):
    """专门用于 QTableView 的数据模型"""
    def __init__(self, rows=[], parent=None):
        """初始化表格数据模型。"""
        # 1. 调用父类初始化
        super().__init__(parent)
        self._rows = rows
        self._headers = ["选择", "序号", "FileName", "Path", "APPID", "Size(KB)", "CreateTime", "ModifiedTime", "下载进度", "状态", "操作"]
        # 保存复选框状态 {row_index: bool} - 注意这里 row_index 是针对当前页的
        self._checks = {}

    def set_rows(self, rows):
        """重置表格所有行数据。"""
        # 1. 开始重置模型
        self.beginResetModel()
        # 2. 更新数据行
        self._rows = rows
        # 3. 清空选择状态（换页或搜索时触发）
        self._checks = {} # 换页/刷新清空选择
        # 4. 结束重置模型
        self.endResetModel()

    def get_rows(self):
        """获取所有行数据。"""
        # 1. 返回内部行列表
        return self._rows

    def rowCount(self, parent=QtCore.QModelIndex()):
        """获取行数。"""
        # 1. 返回行列表长度
        return len(self._rows)

    def columnCount(self, parent=QtCore.QModelIndex()):
        """获取列数。"""
        # 1. 返回表头长度
        return len(self._headers)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        """核心数据提供方法，根据索引和 Role 返回对应数据。"""
        # 1. 检查索引有效性
        if not index.isValid(): return None
        row = index.row()
        col = index.column()
        item = self._rows[row]

        # 2. 处理显示数据 (DisplayRole)
        if role == QtCore.Qt.DisplayRole:
            if col == 1: return str(item.get("_seq_idx", row + 1))
            if col == 2: return item.get("filename", "")
            if col == 3: return item.get("path", "")
            if col == 4: return item.get("appid", "")
            if col == 5: return item.get("size_kb", "")
            if col == 6: return item.get("create_time", "")
            if col == 7: return item.get("modified_time", "")
            # col 8 (progress)
            if col == 8:
                pct = int(item.get('progress', 0) or 0)
                speed = (item.get("speed") or "").strip()
                status = (item.get("status") or "").strip()
                if speed and status == "下载中":
                    return f"{pct}% - {speed}"
                return f"{pct}%"
            if col == 9: return item.get("status", "")
            return ""

        # 3. 处理复选框状态 (CheckStateRole)
        if role == QtCore.Qt.CheckStateRole and col == 0:
            return QtCore.Qt.Checked if self._checks.get(row, False) else QtCore.Qt.Unchecked

        # 4. 处理文本对齐 (TextAlignmentRole)
        if role == QtCore.Qt.TextAlignmentRole:
            if col in [0, 1, 4, 5, 6, 7, 8, 9]:
                return QtCore.Qt.AlignCenter
            return QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter

        return None

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        """设置数据（主要处理复选框勾选）。"""
        # 1. 处理复选框状态变更
        if role == QtCore.Qt.CheckStateRole and index.column() == 0:
            self._checks[index.row()] = (value == QtCore.Qt.Checked)
            self.dataChanged.emit(index, index, [role])
            return True
        return False

    def flags(self, index):
        """返回单元格的属性标志（是否可选、是否启用、是否可勾选）。"""
        # 1. 基础标志
        f = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        # 2. 第0列允许用户交互勾选
        if index.column() == 0:
            f |= QtCore.Qt.ItemIsUserCheckable
        return f

    def headerData(self, section, orientation, role):
        """获取表头显示数据。"""
        # 1. 返回水平表头的标题文本
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self._headers[section]
        return None

    def update_row_progress(self, row_index: int, status: str, progress: int, speed: str):
        """局部更新某行的进度和状态，不重置 Model。"""
        # 1. 校验索引范围
        if row_index < 0 or row_index >= len(self._rows):
            return

        # 2. 更新数据源
        # 更新数据
        self._rows[row_index]["status"] = status
        self._rows[row_index]["progress"] = progress
        self._rows[row_index]["speed"] = speed

        # 3. 发射局部数据变更信号
        # 发射局部数据变更信号
        # 涉及列：8(进度), 9(状态), 10(操作按钮可能根据状态变)
        start_idx = self.index(row_index, 8)
        end_idx = self.index(row_index, 10)
        self.dataChanged.emit(start_idx, end_idx, [QtCore.Qt.DisplayRole])

    def select_all(self, checked: bool):
        """批量设置所有行的选中状态。"""
        # 1. 开启 Model 更新事务
        self.beginResetModel()
        # 2. 更新选中状态字典
        if checked:
            self._checks = {i: True for i in range(len(self._rows))}
        else:
            self._checks = {}
        # 3. 结束 Model 更新事务
        self.endResetModel()
