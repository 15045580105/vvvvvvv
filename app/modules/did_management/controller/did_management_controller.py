from typing import Optional

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt

from app.common.communication.DataCenter.DataCenter import DataCenter
from app.core.base_controller import BaseController
from app.modules.did_management.model.did_management_model import (
    DIDModel,
    DIDBitRow,
    DIDTableRow,
)
from app.modules.did_management.view.did_management_view import (
    DIDView,
    FullCellDelegate,
    ComboBoxDelegate,
)
from app.services.diagnostic.dpt_service import DPTService


class DIDController(BaseController):
    """DID 控制器：承载 UI 交互、通信监听与 DPT 解析的核心逻辑。"""

    def __init__(self, parent=None, dpt_service: Optional[DPTService] = None):
        self.model = DIDModel(parent)
        self.view = DIDView(parent)
        self._dpt_service = dpt_service or DPTService()
        self._data_center = DataCenter.get_instance()
        self._is_registered = False
        super().__init__(self.model, self.view, parent)

        table = self.view.table
        # 使用整格无边框编辑器的委托：DID/Value 列
        full_delegate = FullCellDelegate(table)
        table.setItemDelegateForColumn(2, full_delegate)
        table.setItemDelegateForColumn(6, full_delegate)

        # 三个下拉列：常态文本，编辑时整格下拉
        fmt_delegate = ComboBoxDelegate(self._data_format_items, table)
        sess_delegate = ComboBoxDelegate(self._session_items, table)
        sec_delegate = ComboBoxDelegate(self._security_items, table)
        table.setItemDelegateForColumn(3, fmt_delegate)
        table.setItemDelegateForColumn(4, sess_delegate)
        table.setItemDelegateForColumn(5, sec_delegate)

        # 视图信号绑定
        self.view.destroyed.connect(self._on_view_destroyed)
        self.view.dpt_import_requested.connect(self._handle_dpt_import)
        self.view.ecu_map_import_requested.connect(self._handle_ecu_map_import)
        self.view.value_detail_requested.connect(self._on_value_detail_requested)
        self.view.read_requested.connect(self._on_read_clicked)
        self.view.write_requested.connect(self._on_write_clicked)
        self.view.add_row_requested.connect(self._on_add_row)
        self.view.remove_row_requested.connect(self._on_remove_row)
        self.view.move_up_requested.connect(self._on_move_up)
        self.view.move_down_requested.connect(self._on_move_down)
        # 表格交互行为：完全由 controller 控制
        self.view.cell_clicked.connect(self._on_cell_clicked)
        self.view.cell_double_clicked.connect(self._on_cell_double_clicked)

        # 初始化 DID 示例数据（真实场景中应来自 DPT/配置）
        demo_rows = [
            DIDTableRow("GAC ECUHardwareVersion", "F17F"),
            DIDTableRow("ECUBootSoftwareVersion", "F180", data_format="HEX"),
        ]
        self.model.set_did_rows(demo_rows)

        # 打开 DID 页面即注册监听报文
        self._register_listener()

    # ---------- delegate 选项提供 ----------

    def _data_format_items(self, index: QtCore.QModelIndex):
        return self.model.data_format_options

    def _session_items(self, index: QtCore.QModelIndex):
        return self.model.session_options

    def _security_items(self, index: QtCore.QModelIndex):
        return self.model.security_options

    # -------------------- 顶部按钮行为 --------------------

    def _on_read_clicked(self) -> None:
        """点击“读取”：根据勾选行批量构造并发送读 DID 请求（占位骨架）。"""
        selected_rows = [
            (idx, row)
            for idx, row in enumerate(self.model.did_rows)
            if row.selected
        ]
        if not selected_rows:
            QtWidgets.QMessageBox.information(self.view, "提示", "请先勾选需要读取的 DID")
            return

        # TODO: 将下面的 TX 构造和发送替换为真实诊断服务调用
        for _, row in selected_rows:
            did = row.did.strip().replace(" ", "")
            try:
                did_val = int(did, 16)
            except ValueError:
                continue
            hi = (did_val >> 8) & 0xFF
            lo = did_val & 0xFF
            tx_bytes = bytes([0x22, hi, lo])
            tx_text = " ".join(f"{b:02X}" for b in tx_bytes)
            self.model.apply_update(tx=tx_text)

    def _on_write_clicked(self) -> None:
        """点击“写入”：根据勾选行的 Value 批量构造并发送写 DID 请求（占位骨架）。"""
        selected_rows = [
            (idx, row)
            for idx, row in enumerate(self.model.did_rows)
            if row.selected
        ]
        if not selected_rows:
            QtWidgets.QMessageBox.information(self.view, "提示", "请先勾选需要写入的 DID")
            return

        # TODO: 将下面的 TX 构造和发送替换为真实诊断服务调用
        for _, row in selected_rows:
            did = row.did.strip().replace(" ", "")
            value_str = row.value.strip().replace(" ", "")
            if not value_str:
                continue
            try:
                did_val = int(did, 16)
                payload = bytes.fromhex(value_str)
            except ValueError:
                continue
            hi = (did_val >> 8) & 0xFF
            lo = did_val & 0xFF
            tx_bytes = bytes([0x2E, hi, lo]) + payload
            tx_text = " ".join(f"{b:02X}" for b in tx_bytes)
            self.model.apply_update(tx=tx_text)

    # -------------------- DataCenter 回调 --------------------

    def _register_listener(self) -> None:
        """注册自身为 DataCenter 监听者，保证只注册一次。"""
        if not self._is_registered:
            self._data_center.register_listener(self)
            self._is_registered = True

    def _on_view_destroyed(self) -> None:
        """视图销毁时取消监听，防止悬挂引用。"""
        if self._is_registered:
            self._data_center.unregister_listener(self)
            self._is_registered = False

    def on_eth_message(self, raw_bytes: bytes, parsed):
        """DataCenter 回调入口：实时收到报文后进行 DID 特有处理。"""
        if raw_bytes:
            self.on_response(raw_bytes)

    def on_response(self, payload: bytes):
        """收到响应 payload 时刷新 RX 文本并尝试做 DPT 解析。"""
        rows = None
        if self._dpt_service.is_ready():
            result = self._dpt_service.parse_bytes(payload)
            if result:
                rows = [
                    DIDBitRow(
                        bit=cols[0],
                        function=cols[1],
                        binary_value=cols[2],
                        status=cols[3],
                    )
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
        QtWidgets.QMessageBox.information(self.view, "提示", "ECU 目的地址表导入逻辑待实现")

    def on_model_changed(self):
        """Model 更新时同步刷新视图表格和原始数据。"""
        self._rebuild_table()
        self.view.raw_text.setText(self.model.raw_data)

    def get_view(self):
        """提供视图给外层容器使用。"""
        return self.view

    # -------------------- 表格构建与交互 --------------------

    def _rebuild_table(self) -> None:
        table = self.view.table
        rows = self.model.did_rows
        table.blockSignals(True)
        table.setRowCount(len(rows))

        try:
            table.itemChanged.disconnect(self._on_item_changed)
        except TypeError:
            pass

        for r, row in enumerate(rows):
            # 初始化基础单元格
            self.view.build_row_widgets(r)

            # checkbox
            chk_item = table.item(r, 0)
            if chk_item is not None:
                chk_item.setCheckState(
                    Qt.Checked if row.selected else Qt.Unchecked
                )

            # Description
            desc_item = QtWidgets.QTableWidgetItem(row.description)
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 1, desc_item)

            # DID
            did_item = table.item(r, 2)
            if did_item is None:
                did_item = QtWidgets.QTableWidgetItem(row.did)
                table.setItem(r, 2, did_item)
            else:
                did_item.setText(row.did)

            # STR/HEX
            fmt_item = QtWidgets.QTableWidgetItem(row.data_format)
            table.setItem(r, 3, fmt_item)

            # DiagnosticSession
            sess_item = QtWidgets.QTableWidgetItem(row.diagnostic_session)
            table.setItem(r, 4, sess_item)

            # SecurityAccess
            sec_item = QtWidgets.QTableWidgetItem(row.security_access)
            table.setItem(r, 5, sec_item)

            # Value
            val_item = table.item(r, 6)
            if val_item is None:
                val_item = QtWidgets.QTableWidgetItem(row.value)
                table.setItem(r, 6, val_item)
            else:
                val_item.setText(row.value)

            if getattr(row, "value_color", None):
                try:
                    color = QtGui.QColor(row.value_color)
                    val_item.setForeground(QtGui.QBrush(color))
                except Exception:
                    pass

        table.itemChanged.connect(self._on_item_changed)
        table.blockSignals(False)

    def _on_cell_clicked(self, row: int, col: int) -> None:
        """单击行为：DID/Value 列直接进入编辑并全选文本，模拟 Excel 效果。"""
        table = self.view.table
        if col in (2, 6):
            item = table.item(row, col)
            if item is not None:
                table.editItem(item)
                QtCore.QTimer.singleShot(0, lambda: self._select_editor_text())

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        """双击行为：
        - DID / Value：整格输入框（与单击一致）；
        - 三个下拉列：整格变成下拉框。"""
        table = self.view.table
        item = table.item(row, col)
        if item is None:
            return
        if col in (2, 3, 4, 5, 6):
            table.editItem(item)
            if col in (2, 6):
                QtCore.QTimer.singleShot(0, lambda: self._select_editor_text())

    def _select_editor_text(self) -> None:
        """找到当前编辑器并全选文本。"""
        editor = self.view.table.focusWidget()
        if isinstance(editor, QtWidgets.QLineEdit):
            editor.selectAll()

    # -------------------- 表格行编辑/移动 --------------------

    def _on_add_row(self) -> None:
        """添加一行空白 DID。"""
        self.model.did_rows.append(DIDTableRow("", ""))
        self.model.dataChanged.emit()

    def _on_remove_row(self) -> None:
        """删除当前选中行。"""
        row = self.view.table.currentRow()
        if row < 0 or row >= len(self.model.did_rows):
            return
        del self.model.did_rows[row]
        self.model.dataChanged.emit()

    def _on_move_up(self) -> None:
        """上移当前选中行。"""
        row = self.view.table.currentRow()
        if row <= 0 or row >= len(self.model.did_rows):
            return
        self.model.did_rows[row - 1], self.model.did_rows[row] = (
            self.model.did_rows[row],
            self.model.did_rows[row - 1],
        )
        self.model.dataChanged.emit()
        self.view.table.selectRow(row - 1)

    def _on_move_down(self) -> None:
        """下移当前选中行。"""
        row = self.view.table.currentRow()
        if row < 0 or row >= len(self.model.did_rows) - 1:
            return
        self.model.did_rows[row + 1], self.model.did_rows[row] = (
            self.model.did_rows[row],
            self.model.did_rows[row + 1],
        )
        self.model.dataChanged.emit()
        self.view.table.selectRow(row + 1)

    def _on_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        """表格项变化时同步到模型：处理复选、DID、下拉列与 Value 列。"""
        col = item.column()
        row = item.row()
        if row < 0 or row >= len(self.model.did_rows):
            return

        text = item.text()

        if col == 0:
            checked = item.checkState() == Qt.Checked
            self.model.update_row(row, selected=checked)
        elif col == 2:
            self.model.update_row(row, did=text)
        elif col == 3:
            self.model.update_row(row, data_format=text)
        elif col == 4:
            self.model.update_row(row, diagnostic_session=text)
        elif col == 5:
            self.model.update_row(row, security_access=text)
        elif col == 6:
            self.model.update_row(row, value=text)

    def _on_value_detail_requested(self, row: int) -> None:
        """弹出悬浮窗展示该 DID 的基础信息。"""
        if row < 0 or row >= len(self.model.did_rows):
            return
        info = self.model.did_rows[row]
        msg = (
            f"Description: {info.description}\n"
            f"DID: {info.did}\n"
            f"当前值: {info.value or '-'}\n"
            f"会话: {info.diagnostic_session}\n"
            f"安全等级: {info.security_access}"
        )
        QtWidgets.QMessageBox.information(self.view, "DID 详情", msg)
