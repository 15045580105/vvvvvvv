from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt5.QtCore import pyqtSignal

from app.common.utils.packet_parser_utils import PacketParserUtils
from app.core.base_model import BaseModel


class PacketParserModel(BaseModel):
    """报文解析页面数据模型。"""

    selectionChanged = pyqtSignal()
    packetsAppended = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_path = ""
        self.search_query = ""
        self.packets: List[Dict[str, Any]] = []
        self.filtered_packets: List[Dict[str, Any]] = []
        self.selected_filtered_index = -1
        self.selected_node: Optional[Dict[str, Any]] = None
        self.last_error = ""
        self.is_loading = False

    def load_packets(self, file_path: str):
        self.begin_load(file_path)
        try:
            packets = PacketParserUtils.load_packets(self.file_path) if self.file_path else []
        except Exception as exc:
            self.apply_load_error(str(exc))
            return
        self.apply_loaded_packets(self.file_path, packets)

    def reload(self):
        if self.file_path:
            self.load_packets(self.file_path)

    def begin_load(self, file_path: str):
        self.file_path = file_path or self.file_path
        self.last_error = ""
        self.packets = []
        self.filtered_packets = []
        self.selected_filtered_index = -1
        self.selected_node = None
        self.is_loading = True
        self.dataChanged.emit()

    def append_loaded_packets(self, packets: List[Dict[str, Any]]):
        if not packets:
            return
        self.packets.extend(packets)
        appended_filtered = self._append_filtered_packets(packets)
        self.packetsAppended.emit(appended_filtered)
        self.dataChanged.emit()

    def finish_load(self, file_path: str):
        self.file_path = file_path or self.file_path
        self.last_error = ""
        self.is_loading = False
        self.dataChanged.emit()

    def apply_loaded_packets(self, file_path: str, packets: List[Dict[str, Any]]):
        self.file_path = file_path or self.file_path
        self.last_error = ""
        self.packets = packets or []
        self.is_loading = False
        self._apply_filter(reset_selection=True)
        self.dataChanged.emit()

    def apply_load_error(self, message: str):
        self.packets = []
        self.filtered_packets = []
        self.selected_filtered_index = -1
        self.last_error = message
        self.is_loading = False
        self.dataChanged.emit()

    def set_search_query(self, query: str):
        self.search_query = (query or "").strip()
        self._apply_filter(reset_selection=False)
        self.dataChanged.emit()

    def set_selected_packet(self, index: int):
        if 0 <= index < len(self.filtered_packets):
            self.selected_filtered_index = index
        else:
            self.selected_filtered_index = -1
        self.selected_node = None
        self.selectionChanged.emit()

    def set_selected_node(self, node: Optional[Dict[str, Any]]):
        self.selected_node = node
        self.selectionChanged.emit()

    def get_selected_packet(self) -> Optional[Dict[str, Any]]:
        if 0 <= self.selected_filtered_index < len(self.filtered_packets):
            return self.filtered_packets[self.selected_filtered_index]
        return None

    def get_selected_tree_nodes(self) -> List[Dict[str, Any]]:
        packet = self.get_selected_packet()
        if not packet:
            return []
        return PacketParserUtils.build_tree_nodes(packet)

    def get_data_text(self) -> str:
        if self.selected_node:
            return PacketParserUtils.node_data_text(self.selected_node)
        packet = self.get_selected_packet()
        if not packet:
            return "请选择上方报文"
        return PacketParserUtils.packet_data_text(packet)

    def get_summary_text(self) -> str:
        total = len(self.packets)
        shown = len(self.filtered_packets)
        if total == 0:
            return "未加载报文文件"
        if self.search_query:
            return f"共 {total} 条报文，当前筛选后显示 {shown} 条"
        return f"共加载 {total} 条报文"

    def _apply_filter(self, reset_selection: bool):
        previous_packet = None if reset_selection else self.get_selected_packet()

        if not self.search_query:
            self.filtered_packets = list(self.packets)
        else:
            from app.common.utils.search_utils import SearchQueryEvaluator
            search_evaluator = SearchQueryEvaluator(self.search_query)

            self.filtered_packets = [
                packet for packet in self.packets
                if self._packet_matches(packet, search_evaluator)
            ]

        self.selected_node = None
        if not self.filtered_packets:
            self.selected_filtered_index = -1
            return

        if previous_packet and previous_packet in self.filtered_packets:
            self.selected_filtered_index = self.filtered_packets.index(previous_packet)
        else:
            self.selected_filtered_index = -1

    def _append_filtered_packets(self, packets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        self.selected_node = None

        if not self.search_query:
            self.filtered_packets.extend(packets)
            return packets

        from app.common.utils.search_utils import SearchQueryEvaluator
        search_evaluator = SearchQueryEvaluator(self.search_query)

        appended_filtered = [
            packet for packet in packets
            if self._packet_matches(packet, search_evaluator)
        ]
        if appended_filtered:
            self.filtered_packets.extend(appended_filtered)

        if not self.filtered_packets:
            self.selected_filtered_index = -1
        elif self.selected_filtered_index >= len(self.filtered_packets):
            self.selected_filtered_index = -1
        return appended_filtered

    @staticmethod
    def _packet_matches(packet: Dict[str, Any], search_evaluator: 'SearchQueryEvaluator') -> bool:
        summary = str(packet.get("summary", ""))

        # Remove spaces after colons in summary to support queries like "Length:17" matching "Length: 17"
        import re
        summary_normalized = re.sub(r':\s+', ':', summary)

        text = " ".join([
            str(packet.get("no", "")),
            str(packet.get("timestamp", "")),
            str(packet.get("source", "")),
            str(packet.get("destination", "")),
            str(packet.get("protocol", "")),
            summary_normalized,
        ]).lower()

        # Also allow matching Chinese colons by replacing them with english colons in the text
        text = text.replace("：", ":")

        return search_evaluator.evaluate(text)
