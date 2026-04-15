from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from app.core.base_controller import BaseController
from app.common.utils.packet_parser_utils import PacketParserUtils
from app.modules.someip_signboard.model.someip_signboard_model import PacketParserModel
from app.modules.someip_signboard.view.someip_signboard_view import SomeIpSignboardView


class PacketImportWorker(QThread):
    progress_changed = pyqtSignal(int, str)
    import_completed = pyqtSignal(str, list)
    import_failed = pyqtSignal(str)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path

    def run(self):
        try:
            packets = PacketParserUtils.load_packets(self.file_path, progress_callback=self._handle_progress)
            self.import_completed.emit(self.file_path, packets)
        except Exception as exc:
            self.import_failed.emit(str(exc))

    def _handle_progress(self, value: int, message: str):
        self.progress_changed.emit(value, message)


class PacketParserController(BaseController):
    """报文解析页面控制器。"""

    def __init__(self, parent=None):
        self.model = PacketParserModel(parent)
        self.view = SomeIpSignboardView(parent)
        self._import_worker = None
        self._import_worker_finished = False
        self._last_progress_message = ""
        super().__init__(self.model, self.view, parent)

        self.view.import_requested.connect(self.on_import_requested)
        self.view.refresh_requested.connect(self.on_refresh_requested)
        self.view.search_changed.connect(self.on_search_changed)
        self.view.file_dropped.connect(self.on_file_dropped)
        self.view.packet_selected.connect(self.on_packet_selected)
        self.view.tree_node_selected.connect(self.on_tree_node_selected)
        self.model.selectionChanged.connect(self._refresh_selection)

        self._refresh_view()

    def on_import_requested(self):
        file_path = self.view.browse_for_file()
        if file_path:
            self._start_import(file_path)

    def on_refresh_requested(self):
        if self.model.file_path:
            self._start_import(self.model.file_path)

    def on_search_changed(self, text: str):
        self.model.set_search_query(text)

    def on_file_dropped(self, file_path: str):
        if file_path:
            self._start_import(file_path)

    def on_packet_selected(self, row: int):
        self.model.set_selected_packet(row)

    def on_tree_node_selected(self, node):
        self.model.set_selected_node(node)

    def on_model_changed(self):
        self._refresh_view()

    def _start_import(self, file_path: str):
        if self._import_worker and self._import_worker.isRunning():
            return

        self._import_worker_finished = False
        self._last_progress_message = "准备导入文件..."
        self.model.begin_load(file_path)
        self.view.set_import_in_progress(True)
        self.view.update_import_progress(0, "准备导入文件...")
        self.view.begin_packet_stream()
        self.view.set_tree_nodes([])
        self.view.set_data_text("导入完成后请选择报文进行解析")

        self._import_worker = PacketImportWorker(file_path, self)
        self._import_worker.progress_changed.connect(self._on_import_progress)
        self._import_worker.import_completed.connect(self._on_import_completed)
        self._import_worker.import_failed.connect(self._on_import_failed)
        self._import_worker.finished.connect(self._on_import_finished)
        self._import_worker.start()

    def _on_import_progress(self, value: int, message: str):
        self._last_progress_message = message or self._last_progress_message
        if value >= 100 and self.model.is_loading:
            self.view.update_import_progress(99, "正在整理导入结果...")
            return
        self.view.update_import_progress(value, message)

    def _on_import_completed(self, file_path: str, packets: list):
        self.model.apply_loaded_packets(file_path, packets)
        self.view.update_import_progress(100, f"导入完成，已加载 {len(packets)} 条报文")
        self._maybe_finalize_import_ui()

    def _on_import_failed(self, message: str):
        self.model.apply_load_error(message)
        self._maybe_finalize_import_ui()

    def _on_import_finished(self):
        self._import_worker_finished = True
        self._maybe_finalize_import_ui()

    def _refresh_view(self):
        self.view.set_file_path(self.model.file_path)

        if self.model.last_error:
            self.view.set_status_text(f"解析失败：{self.model.last_error}")
            self.view.set_packets([], -1)
            self.view.set_tree_nodes([])
            self.view.set_data_text(self.model.last_error)
            return

        if self.model.is_loading:
            self.view.set_status_text("正在导入文件，请稍候...")
            return

        self.view.set_status_text(self.model.get_summary_text())
        self.view.set_packets(self.model.filtered_packets, self.model.selected_filtered_index)
        self._refresh_selection()

    def _maybe_finalize_import_ui(self):
        if not self._import_worker_finished:
            return
        if self.model.is_loading:
            return
        self.view.set_import_in_progress(False)
        self._import_worker = None

    def _refresh_selection(self):
        if self.model.last_error:
            return
        if self.model.is_loading:
            return
        selected_index = self.model.selected_filtered_index
        tree_nodes = self.model.get_selected_tree_nodes()
        data_text = self.model.get_data_text()
        if selected_index >= 0:
            self.view.refresh_packet_row(selected_index)
        self.view.set_tree_nodes(tree_nodes)
        self.view.set_data_text(data_text)

