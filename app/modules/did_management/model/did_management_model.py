from dataclasses import dataclass
from typing import List, Optional

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
    diagnostic_session: str = "Default"
    security_access: str = "Locked"
    value: str = ""
    selected: bool = True
    value_color: Optional[str] = None


class DIDModel(BaseModel):
    def __init__(self, parent=None):
        """初始化 DID 模型，准备响应树、原始显示文本及当前 ECU 状态。"""
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
        self.session_options = ["Default", "Programming", "Extended"]
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
        """在原始数据日志中追加一行。"""
        text = payload.strip() if isinstance(payload, str) else payload
        self.raw_log.append(f"{prefix}: {text or '-'}")
        self.raw_data = "\n".join(self.raw_log)

    def apply_update(
        self,
        *,
        tx: Optional[str] = None,
        rx: Optional[str] = None,
        rows: Optional[List[DIDBitRow]] = None,
        dpt_path=_UNSET,
    ) -> None:
        """批量应用控制器传入的 TX/RX/解析行/DPT 路径更新并触发界面刷新。"""
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
        """记录当前选中的 ECU，供后续过滤/请求发送使用。"""
        self.current_ecu = ecu

    def set_ecu_items(self, items: List[str]) -> None:
        """更新 ECU 列表缓存，并通知界面重绘。"""
        self.ecu_items = items
        self.dataChanged.emit()

    def set_did_rows(self, rows: List[DIDTableRow]) -> None:
        self.did_rows = rows
        self.dataChanged.emit()

    def update_row(self, index: int, **updates) -> None:
        if index < 0 or index >= len(self.did_rows):
            return
        row = self.did_rows[index]
        for key, value in updates.items():
            if hasattr(row, key):
                setattr(row, key, value)
        self.dataChanged.emit()
