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


class DIDModel(BaseModel):
    def __init__(self, parent=None):
        """初始化 DID 模型，准备响应树、原始显示文本及当前 ECU 状态。"""
        super().__init__(parent)
        self.response_tree: List[DIDBitRow] = []
        self.raw_data: str = ""
        self.current_ecu: Optional[str] = None
        self.ecu_items: List[str] = []
        self._pending_tx: Optional[str] = None
        self._last_rx: Optional[str] = None
        self.dpt_file_path: Optional[str] = None
        self._refresh_raw_text()

    def _refresh_raw_text(self) -> None:
        """根据最��一次 TX/RX 缓存刷新 raw_data 文本，供视图展示。"""
        tx_line = f"TX: {self._pending_tx or '-'}"
        rx_line = f"RX: {self._last_rx or '-'}"
        self.raw_data = f"{tx_line}\n{rx_line}"

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
            self._pending_tx = tx or "-"
        if rx is not None:
            self._last_rx = rx or "-"
        self._refresh_raw_text()
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
