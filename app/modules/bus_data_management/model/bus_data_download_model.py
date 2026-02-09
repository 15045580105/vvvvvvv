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

# UI 适配模型，Qt表格数据展示
class BusDataTableModel(QAbstractTableModel):
    """自定义表格模型"""
    def __init__(self, rows=None, parent=None):
        """初始化表格数据模型。"""
        # 1. 调用父类初始化
        super().__init__(parent)
        # 2. 初始化行数据和表头
        self._rows = rows if rows is not None else []
        self._headers = ["", "序号", "FileName", "Path", "Type", "Size(KB)", "CreateTime", "ModifiedTime", "下载进度", "状态", "操作"]
        # 3. 初始化勾选状态字典
        self._checks = {}

    def set_rows(self, rows):
        """重置表格数据。"""
        # 1. 开始重置模型事务
        self.beginResetModel()
        # 2. 更新数据行
        self._rows = rows
        # 3. 清空勾选状态
        self._checks = {}
        # 4. 结束模型重置事务
        self.endResetModel()


    def rowCount(self, parent=None):
        """获取行数。"""
        # 1. 返回行列表长度
        return len(self._rows)

    def columnCount(self, parent=None):
        """获取列数。"""
        # 1. 返回表头长度
        return len(self._headers)

    def data(self, index, role=Qt.DisplayRole):
        """
        核心数据接口：根据索引(行,列)和角色(Display/Check/Align)返回对应的数据。
        Qt View 在绘制每个单元格时都会频繁调用此函数。
        """
        # 1. 检查索引有效性
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        item = self._rows[row]

        # 2. DisplayRole: 返回单元格显示的文本内容
        if role == Qt.DisplayRole:
            if col == 1: return str(item.get("_seq_idx", row + 1))
            if col == 2: return item.get("filename", "")
            if col == 3: return item.get("path", "")
            if col == 4: return item.get("appid", "")
            if col == 5: return item.get("size_kb", "")
            if col == 6: return item.get("create_time", "")
            if col == 7: return item.get("modified_time", "")
            if col == 8:  # 进度列：显示 "50% (1.2MB/s)" 或 "100%"
                pct = item.get("progress", 0)
                speed = item.get("transfer_rate", "")
                status = item.get("status", "")
                if status == "下载中" and speed:
                    return f"{pct}% ({speed})"
                return f"{pct}%"
            if col == 9: return item.get("status", "")
            return ""

        # 3. CheckStateRole: 控制第0列复选框的选中状态
        if role == Qt.CheckStateRole and col == 0:
            return Qt.Checked if self._checks.get(row, False) else Qt.Unchecked

        # 4. TextAlignmentRole: 控制文本的对齐方式
        if role == Qt.TextAlignmentRole:
            # 居中对齐的列
            if col in [0, 1, 4, 5, 6, 7, 8, 9, 10]:
                return Qt.AlignCenter
            # 靠左对齐的列
            return Qt.AlignLeft | Qt.AlignVCenter

        return None

    def setData(self, index, value, role=Qt.EditRole):
        """处理用户编辑（主要是复选框勾选）。"""
        # 1. 仅响应第0列的 CheckStateRole 编辑
        if role == Qt.CheckStateRole and index.column() == 0:
            # 2. 更新内部状态字典
            self._checks[index.row()] = (value == Qt.Checked)
            # 3. 发射数据变更信号通知视图刷新
            self.dataChanged.emit(index, index, [role])
            return True
        return False

    def select_all(self, checked: bool):
        """批量更新所有行的选择状态。"""
        # 1. 开始重置模型事务（批量操作建议直接重置）
        self.beginResetModel()
        # 2. 更新所有行的状态
        if checked:
            self._checks = {i: True for i in range(len(self._rows))}
        else:
            self._checks = {}
        # 3. 结束模型重置事务
        self.endResetModel()

    def get_checked_rows(self) -> List[Dict[str, Any]]:
        """获取所有被选中的行数据对象。"""
        # 1. 遍历所有选中的行索引
        selected = []
        for idx in sorted(self._checks.keys()):
            # 2. 确保索引有效
            if self._checks[idx] and 0 <= idx < len(self._rows):
                selected.append(self._rows[idx])
        return selected

    def flags(self, index):
        """设置单元格的交互属性（启用、可选、可勾选）。"""
        # 1. 基础属性：启用、可选
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        # 2. 第0列允许用户交互勾选
        if index.column() == 0:
            f |= Qt.ItemIsUserCheckable
        return f

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        """获取表头显示文本。"""
        # 1. 水平表头显示列名
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            if section == 0:
                return ""  # 序号0是复选框列，表头留空由 Delegate 绘制全选框
            return self._headers[section]
        return None

    def update_row_progress(self, row_idx, status, progress, speed):
        """单行更新状态和进度，避免全表刷新。"""
        # 1. 检查行索引有效性
        if 0 <= row_idx < len(self._rows):
            # 2. 更新数据源
            item = self._rows[row_idx]
            item["status"] = status
            item["progress"] = progress
            item["transfer_rate"] = speed
            # 3. 计算需要刷新的列范围（进度列和状态列）
            # Refresh columns 8 (Progress) and 9 (Status)
            tl = self.index(row_idx, 8)
            br = self.index(row_idx, 9)
            # 4. 发射局部变更信号
            self.dataChanged.emit(tl, br, [Qt.DisplayRole])


class BusDataDownloadModel(BaseModel):
    """总线数据下载模型，支持简单过滤和分页。"""

    dataChanged = pyqtSignal()
    # Path, Status, Progress, Speed
    progressChanged = pyqtSignal(str, str, int, str)

    def __init__(self, parent=None):
        """初始化业务模型。"""
        # 1. 调用父类初始化
        super().__init__(parent)
        # 2. 初始化数据容器
        self._all_rows: List[Dict[str, Any]] = []
        self._filtered_rows: List[Dict[str, Any]] = []
        # 3. 初始化分页参数
        self.page = 1
        self.page_size = 1000

        # 4. 初始化排序状态
        self.sort_column_idx = -1
        self.sort_order = 0 # 0: Asc, 1: Desc (Qt values)

        # 5. 初始化缓存和索引
        # 缓存 Type 列表
        self.unique_types: List[str] = []
        # 路径索引用于快速查找 O(1)
        self._file_map: Dict[str, Dict[str, Any]] = {}

        # 6. 初始化过滤条件
        self._filter: Dict[str, Any] = {
            "tab_kw": "",
            "type_kw": "",
            "name_kw": "",
            "status": "全部",
            "date_from": None,
            "date_to": None,
        }

    # ---- 对外 API ----
    def set_file_list(self, files: List[Dict[str, Any]]):
        """设置全量文件列表数据。"""
        # 1. 重置内部存储
        self._all_rows = []
        self._file_map = {}
        unique_types = set()

        # 2. 遍历输入文件列表进行标准化处理
        for item in files:
            # 兼容处理状态
            status = item.get("status", "未下载")
            appid = item.get("appid", "")
            if appid:
                unique_types.add(appid)

            # 格式化时间：create_time 缺省秒补00，modified_time 缺省秒补59
            c_time = self._format_date_str(item.get("create_time"), default_ss="00")
            m_time = self._format_date_str(item.get("modified_time"), default_ss="59")

            path_val = item.get("path", "")
            # 3. 构建统一的行数据字典
            row_data = {
                "filename": item.get("filename", ""),
                "path": path_val,
                "appid": appid,
                "size_kb": item.get("size_kb", ""),
                "create_time": c_time,
                "modified_time": m_time,
                "progress": item.get("progress", 0),
                "status": status,
                "raw_size": item.get("raw_size", 0),
            }
            self._all_rows.append(row_data)
            # 4. 建立路径索引
            if path_val:
                self._file_map[path_val] = row_data

        # 5. 更新元数据缓存
        self.unique_types = sorted(list(unique_types))
        # 6. 应用当前过滤并通知更新
        self.apply_filter()
        self.dataChanged.emit()

    def _format_date_str(self, raw_val, default_ss="00") -> str:
        """
        格式化时间字符串为 yyyyMMdd_HHmmss。
        1. 尝试解析 float 时间戳
        2. 尝试解析英文月份格式 (Jun 13 00:39)
        3. 提取所有数字处理 yyyyMMddHHmm (12位) 和 yyyyMMddHHmmss (14位+)
        """
        # 1. 基础清理
        s = str(raw_val).strip() if raw_val is not None else ""
        if not s:
            return ""

        # 2. 尝试纯数字时间戳 (包括浮点数字符串)
        try:
            # 简单判断: 如果能转 float 且值在合理时间戳范围 (2001-2096年)
            val = float(s)
            if 1000000000 <= val <= 4000000000:
                dt = datetime.datetime.fromtimestamp(val)
                return dt.strftime("%Y%m%d_%H%M%S")
        except ValueError:
            pass

        # 3. 尝试解析特殊格式: "Jun 13 00:39" (ls -l 风格)
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

        # 4. 提取数字 (解决各种分隔符 - / : . T space _ 等)
        digits = "".join(filter(lambda c: c.isdigit(), s))

        # 情况: yyyyMMddHHmm (12位) -> 补秒
        if len(digits) == 12:
            return f"{digits[:8]}_{digits[8:12]}{default_ss}"

        # 情况: yyyyMMddHHmmss... (14位及以上，含毫秒) -> 截取前14位
        if len(digits) >= 14:
            return f"{digits[:8]}_{digits[8:14]}"

        return s


    def set_filter(self, criteria: Dict[str, Any]):
        """更新过滤条件并重置分页。"""
        # 1. 更新条件字典
        self._filter.update(criteria or {})
        # 2. 重置到第一页
        self.page = 1
        # 3. 执行过滤
        self.apply_filter()

    def set_page(self, page: int):
        """设置当前页码。"""
        # 1. 更新页码（最小值1）
        self.page = max(1, int(page or 1))
        # 2. 发送变更信号通知视图刷新
        self.dataChanged.emit()

    def set_page_size(self, page_size: int):
        """设置每页大小。"""
        # 1. 更新每页大小（最小值500，与View一致）
        # 与 View 的分页候选项一致；兜底也用 500，避免解析失败回到 10
        self.page_size = max(1, int(page_size or 500))
        # 2. 重置到第一页
        self.page = 1
        # 3. 发送变更信号通知视图刷新
        self.dataChanged.emit()

    def set_sort(self, column_idx: int, order: int):
        """设置排序并应用。"""
        # 1. 记录排序参数
        self.sort_column_idx = column_idx
        self.sort_order = order
        # 2. 执行排序
        self.apply_sort()
        # 3. 发送变更信号
        self.dataChanged.emit()

    def apply_sort(self):
        """对 _filtered_rows 进行排序的具体实现。"""
        # 1. 如果未指定排序列，直接返回
        if self.sort_column_idx < 0:
            return

        # 2. 定义列索引映射到字段名
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

        # 3. 定义排序 key 函数和方向
        reverse = (self.sort_order == 1) # 1 is Descending in Qt (Qt.DescendingOrder = 1)

        def sort_key(item):
            val = item.get(key)
            if val is None:
                return ""
            return val

        # 4. 执行排序
        self._filtered_rows.sort(key=sort_key, reverse=reverse)

    def get_page(self) -> PageResult:
        """根据当前分页参数，返回一页数据结果对象。"""
        total = len(self._filtered_rows)
        # 1. 处理空数据情况
        if total == 0:
            return PageResult(page=1, page_size=self.page_size, page_count=1, total=0, rows=[])

        # 2. 计算分页范围
        page_size = self.page_size
        page_count = (total + page_size - 1) // page_size
        page = min(max(1, self.page), page_count)

        start = (page - 1) * page_size
        end = min(start + page_size, total)
        # 3. 切片获取当前页行数据
        rows = self._filtered_rows[start:end]
        # 4. 返回分页对象
        return PageResult(page=page, page_size=page_size, page_count=page_count, total=total, rows=rows)

    def get_unique_types(self) -> List[str]:
        """获取所有已知的类型列表（AppID/Protocols）。"""
        # 1. 返回缓存的类型列表
        return self.unique_types


    def get_file_by_path(self, path: str) -> Dict[str, Any] | None:
        """Get file object by path. Support exact match and filename suffix match for robustness.
        通过路径查找文件对象。支持精确匹配和后缀容错匹配。
        """
        # 1. 判空
        if not path:
            return None
        # 2. 尝试 O(1) 精确匹配
        # 1) exact match with map
        if path in self._file_map:
            return self._file_map[path]

        # 3. 尝试后缀匹配（应对路径格式细微差异）
        # 2) try suffix match (in case one side stores full path and other stores relative)
        basename = str(path).rstrip("/").split("/")[-1]
        for row in self._all_rows:
            rpath = row.get("path") or ""
            if rpath.endswith(f"/{basename}") or rpath == basename:
                return row
        return None

    def get_row_index_by_path(self, path: str) -> int:
        """获取某路径在当前过滤页中的行索引（用于局部刷新）。支持容错匹配。"""
        # 1. 判空
        if not path:
            return -1
        # 2. 获取当前页数据
        pr = self.get_page()
        # 3. 遍历查找
        basename = str(path).rstrip("/").split("/")[-1]
        for i, row in enumerate(pr.rows):
            rpath = row.get("path") or ""
            if rpath == path or rpath.endswith(f"/{basename}") or rpath == basename:
                return i
        return -1

    def update_file_status(self, path: str, status: str, progress: int = 0, speed: str = ""):
        """更新单个文件状态，并发出信号。"""
        # 1. 判空
        if not path:
            return

        found = False
        # 2. 尝试快速查找并更新
        row = self._file_map.get(path)
        if row:
            row["status"] = status
            row["progress"] = progress
            row["transfer_rate"] = speed
            found = True
        else:
            # 3. 兜底遍历查找（容错匹配）
            # 2. 兜底找不到（可能是路径格式差异），退化为遍历查找
            basename = str(path).rstrip("/").split("/")[-1]
            for r in self._all_rows:
                rpath = r.get("path") or ""
                # 如果 map 没找到，说明精确匹配失败，尝试模糊匹配
                if rpath.endswith(f"/{basename}") or rpath == basename:
                    r["status"] = status
                    r["progress"] = progress
                    r["transfer_rate"] = speed
                    found = True
                    # 缓存此次匹配结果，下次 O(1)
                    self._file_map[path] = r
                    break

        # 4. 如果找到，发出进度信号
        if found:
            # 只有当状态发生质变（如完成、失败）或者被明确要求时，才触发全量 dataChanged?
            self.progressChanged.emit(path, status, progress, speed)


    # ---- 内部工具 ----
    def apply_filter(self):
        """应用所有过滤条件并更新 _filtered_rows。"""
        # 1. 获取过滤参数
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
            # yyyyMMdd_HHmmss 格式比较字符串即可
            if date_from_qt:
                s_from = date_from_qt.toString("yyyyMMdd_HHmmss")
            if date_to_qt:
                s_to = date_to_qt.toString("yyyyMMdd_HHmmss")

        # 2. 定义匹配函数
        def match(row: Dict[str, Any]) -> bool:
            # 路径匹配
            if tab_kw and tab_kw not in str(row.get("path", "")).lower():
                return False
            # Type (AppID) 匹配（全等）
            if type_kw and type_kw != str(row.get("appid", "")):
                return False
            # 文件名关键字匹配
            if name_kw and name_kw not in str(row.get("filename", "")).lower():
                return False
            # 状态匹配
            if status != "全部" and str(row.get("status", "")).strip() != status:
                return False

            # 时间范围匹配
            if time_filter_enabled:
                # 优化：row["create_time"] 已在 set_file_list 中标准化，无需重复 format
                ct_norm = str(row.get("create_time", "")).strip()
                if not ct_norm:
                    return False

                if s_from and ct_norm < s_from:
                    return False
                if s_to and ct_norm > s_to:
                    return False

            return True

        # 3. 执行筛选
        self._filtered_rows = [r for r in self._all_rows if match(r)]
        # 4. 执行排序
        self.apply_sort()
        # 5. 可选：通知外部（通常由调用者 set_filter 负责 emit，此处仅为内部逻辑，
        #    但原代码可能这里直接 emit，保持兼容则不 emit 或由 setter 调用）
        #    self.dataChanged.emit()  <-- 此处不 emit，由 setter 控制流程
