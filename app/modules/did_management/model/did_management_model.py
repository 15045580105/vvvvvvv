from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

from app.core.base_model import BaseModel


_UNSET = object()


@dataclass
class DIDBitRow:
    """单行 DID 解析结果，用于界面四列表格显示。"""

    bit: str
    function: str
    binary_value: str
    status: str


@dataclass
class DIDTableRow:
    description: str
    did: str
    data_format: str = "STR"
    follow_dpt: bool = False
    diagnostic_session: str = "Default"
    security_access: str = "Locked"
    value: str = ""
    selected: bool = True
    value_color: Optional[str] = None


class DIDModel(BaseModel):
    def __init__(self, parent=None):
        """初始化 DID 模型：准备响应树、原始文本、ECU 列表等状态。

        属性：
        - response_tree: DPT 解析后的位域行列表
        - raw_data: 用于展示的 TX/RX 原始文本
        - raw_log: 原始行日志缓存
        - current_ecu: 当前选择的 ECU 标识（可选）
        - ecu_items: ECU 下拉项缓存
        - did_rows: 表格中显示的 DID 行列表
        - data_format_options/session_options/security_options: 下拉选项
        """
        super().__init__(parent)
        self.response_tree: List[DIDBitRow] = []
        self.raw_data: str = ""
        self.raw_log: List[str] = []
        self.current_ecu: Optional[str] = None
        self.ecu_items: List[str] = []
        self.dpt_file_path: Optional[str] = None
        self.reset_raw_log()
        self.max_selection: int = 1
        self.did_rows: List[DIDTableRow] = []
        self.data_format_options = ["STR", "HEX"]
        self.session_options = ["Default (0x01)", "Programming (0x02)", "Extended (0x03)"]
        self.security_options = [
            "Locked",
            "Level1 [0x01]",
            "Level2 [0x03]",
            "Level3 [0x21]",
            "Level Flash [0x11]",
        ]

    def reset_raw_log(self) -> None:
        """清空原始数据日志并重置展示文本。"""
        self.raw_log.clear()
        self.raw_data = ""

    def _append_raw_line(self, prefix: str, payload: Optional[str]) -> None:
        """向原始日志追加一行并更新 raw_data。"""
        text = payload.strip() if isinstance(payload, str) else payload
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        log_entry = f"[{timestamp}] {prefix}: {text or '-'}"
        self.raw_log.append(log_entry)
        self.raw_data = "\n".join(self.raw_log)

        try:
            from app.common.log.operation_log_manager import OperationLogManager
            OperationLogManager.instance().append_log("DID数据管理", f"{prefix}: {text or '-'}")
        except Exception:
            pass

    def apply_update(
        self,
        *,
        tx: Optional[str] = None,
        rx: Optional[str] = None,
        rows: Optional[List[DIDBitRow]] = None,
        dpt_path=_UNSET,
    ) -> None:
        """批量应用由控制器传入的更新（TX/RX/解析行/DPT 路径），并通知视图刷新。"""
        if tx is not None:
            self._append_raw_line("TX", tx)
        if rx is not None:
            self._append_raw_line("RX", rx)
        if rows is not None:
            self.response_tree = rows
        if dpt_path is not _UNSET:
            self.dpt_file_path = dpt_path or None
        self.dataChanged.emit()

    def set_current_ecu(self, ecu: Optional[str]) -> None:
        """设置当前 ECU（供过滤或请求使用）。"""
        self.current_ecu = ecu

    def set_ecu_items(self, items: List[str]) -> None:
        """更新 ECU 下拉项并通知视图刷新。"""
        self.ecu_items = items
        self.dataChanged.emit()

    def set_did_rows(self, rows: List[DIDTableRow]) -> None:
        """替换表格数据行并发出变更事件。"""
        self.did_rows = rows
        self.dataChanged.emit()

    def update_row(self, index: int, **updates) -> None:
        """按索引更新单行属性并通知视图。"""
        if index < 0 or index >= len(self.did_rows):
            return
        row = self.did_rows[index]
        for key, value in updates.items():
            if hasattr(row, key):
                setattr(row, key, value)
        self.dataChanged.emit()

    def clear_all_values(self) -> None:
        """Clear values of all rows."""
        for row in self.did_rows:
            row.value = ""
            row.value_color = None
        self.dataChanged.emit()
