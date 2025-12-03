from typing import List, Optional

from PyQt5 import QtWidgets

from app.common.communication.DataCenter.DataCenter import DataCenter
from app.core.base_controller import BaseController
from app.modules.did_management.model.did_management_model import DIDModel, DIDBitRow
from app.modules.did_management.view.did_management_view import DIDView
from app.services.diagnostic.dpt_service import DPTService


class DIDController(BaseController):
    """DID 控制器：承载 UI 交互、通信监听与 DPT 解析的核心逻辑。"""

    def __init__(self, parent=None, dpt_service: Optional[DPTService] = None):
        self.model = DIDModel(parent)
        self.view = DIDView(parent)
        self._dpt_service = dpt_service or DPTService()
        self._data_center = DataCenter.get_instance()
        self._is_registered = False
        self._rendered_ecus: List[str] = []
        super().__init__(self.model, self.view, parent)

        # 绑定视图信号，仅保留 UI 交互
        self.view.exec_btn.clicked.connect(self.execute)
        self.view.ecu_list.currentTextChanged.connect(self.on_ecu_changed)
        self.view.destroyed.connect(self._on_view_destroyed)
        self.view.dpt_import_requested.connect(self._handle_dpt_import)
        self.view.ecu_map_import_requested.connect(self._handle_ecu_map_import)

        # 初始化 ECU 列表，默认选中第一个（示例数据）
        # TODO: 将 ECU 列表替换为真实数据源
        demo_ecus = ["ECU_A", "ECU_B", "ECU_C"]
        self.model.set_ecu_items(demo_ecus)
        if demo_ecus:
            self.on_ecu_changed(demo_ecus[0])

        # 打开 DID 页面即注册监听报文
        self._register_listener()

    def _register_listener(self) -> None:
        """注册自身为 DataCenter 监听者，保证只注册一次。"""
        if not self._is_registered:
            self._data_center.register_listener(self)
            self._is_registered = True

    def _on_view_destroyed(self) -> None:
        """视图销毁时取消���听，防止悬挂引用。"""
        if self._is_registered:
            self._data_center.unregister_listener(self)
            self._is_registered = False

    def on_ecu_changed(self, ecu_text: Optional[str]):
        """ECU 列表变更时记录当前 ECU，后续发送/解析可根据该值过滤。"""
        self.model.set_current_ecu(ecu_text or None)

    def execute(self):
        """执行指令：收集用户输入、回显 TX 文本并调用通信层发送。"""
        raw = self.view.request_input.text().strip() or "22 F1 90"
        self.model.apply_update(tx=raw)
        # TODO: 在此调用诊断/通信服务发送报文，并在发送成功后进行必要的回调

    def on_eth_message(self, raw_bytes: bytes, parsed):
        """DataCenter 回调入口：实时收到报文后进行 DID 特有处理。"""
        # TODO: 在此实现 DID 特有的筛选、匹配逻辑（例如根据 ECU、DID 号过滤）
        if raw_bytes:
            self.on_response(raw_bytes)

    def on_response(self, payload: bytes):
        """收到响应 payload 时刷新 RX 文本并尝试做 DPT 解析。"""
        rows = None
        if self._dpt_service.is_ready():
            result = self._dpt_service.parse_bytes(payload)
            if result:
                rows = [
                    DIDBitRow(bit=cols[0], function=cols[1], binary_value=cols[2], status=cols[3])
                    for cols in result.to_table_rows()
                ]
        formatted_rx = " ".join(f"{b:02X}" for b in payload)
        self.model.apply_update(rx=formatted_rx, rows=rows)

    def on_dpt_selected(self, file_path: str) -> None:
        """选择 DPT 文件后交由 DPTService 加载并缓存路径。"""
        try:
            self._dpt_service.load_from_file(file_path)
            self.model.apply_update(dpt_path=file_path)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self.view, "DPT 导入失败", str(exc))

    def _handle_dpt_import(self) -> None:
        """处理视图发起的 DPT 导入请求，弹出文件对话框并委托加载。"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.view,
            "选择 DPT 文件",
            "",
            "DPT Files (*.DPT *.dpt);;All Files (*.*)",
        )
        if file_path:
            self.on_dpt_selected(file_path)

    def _handle_ecu_map_import(self) -> None:
        """处理 ECU 目的地址表导入请求（占位，后续替换为真实逻辑）。"""
        # TODO: 加载 ECU 目的地址表，更新 model.set_ecu_items
        QtWidgets.QMessageBox.information(self.view, "提示", "ECU 目的地址表导入逻辑待实现")

    def on_model_changed(self):
        """Model 更新时同步刷新视图表格、原始数据和 ECU 列表。"""
        if self._rendered_ecus != self.model.ecu_items:
            self._rendered_ecus = list(self.model.ecu_items)
            self._rebuild_ecu_list()
        self.view.tree.clear()
        for row in self.model.response_tree:
            item = QtWidgets.QTreeWidgetItem(self.view.tree)
            item.setText(0, str(row.bit))
            item.setText(1, str(row.function))
            item.setText(2, str(row.binary_value))
            item.setText(3, str(row.status))
        self.view.tree.expandAll()
        self.view.raw_text.setText(self.model.raw_data)

    def get_view(self):
        """提供视图给外层容器使用。"""
        return self.view

    def _rebuild_ecu_list(self) -> None:
        """仅在 ECU 列表发生变化时重绘 UI，并尊重当前选择。"""
        block = self.view.ecu_list.blockSignals
        block(True)
        self.view.ecu_list.clear()
        if self.model.ecu_items:
            self.view.ecu_list.addItems(self.model.ecu_items)
            if self.model.current_ecu and self.model.current_ecu in self.model.ecu_items:
                row = self.model.ecu_items.index(self.model.current_ecu)
                self.view.ecu_list.setCurrentRow(row)
            else:
                self.view.ecu_list.clearSelection()
        else:
            self.view.ecu_list.clearSelection()
        block(False)
