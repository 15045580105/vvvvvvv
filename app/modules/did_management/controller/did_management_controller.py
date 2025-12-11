from typing import Optional, Tuple

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
    ValueButtonDelegate,
)
from app.services.diagnostic.dpt_service import DPTService


class DIDController(BaseController):
    """DID 控制器：负责界面交互、消息监听与 DPT 解析的协调逻辑。"""

    def __init__(self, parent=None, dpt_service: Optional[DPTService] = None):
        # 初始化模型 & 视图
        self.model = DIDModel(parent)
        self.view = DIDView(parent)
        # call BaseController to wire model/view signals
        super().__init__(self.model, self.view, parent)

        # services and helpers
        self._dpt_service = dpt_service or DPTService()
        self._data_center = DataCenter.get_instance()
        self._is_registered = False
        self._value_detail_dialog: Optional["ValueDetailDialog"] = None

        # 应用默认列比例（用于初始布局）：
        # [勾选, Description, DID, STR/HEX, DiagnosticSession, SecurityAccess, Value]
        # 第一列窄，Description 宽，Value 最宽��填充剩余空间。
        try:
            self.view.set_column_weights([1, 8, 3, 2, 4, 4, 10])
        except Exception:
            pass

        # 在视图就绪后给出明确的像素宽度，以保证长表头能显示完整。
        # 通过 singleShot 延迟到布局完成时执行。
        try:
            QtCore.QTimer.singleShot(
                0,
                lambda: self.view.set_column_pixel_widths([30, 400, 100, 100, 200, 200, 600]),
            )
        except Exception:
            pass

        # reference table from view
        table = self.view.table

        # 为 Description（列1）、DID（列2）与 Value（列6）使用整格编辑委托，
        # 以保证编辑器覆盖整格并使用不透明背景，避免重影问题。
        full_delegate = FullCellDelegate(self.view.table)
        table.setItemDelegateForColumn(1, full_delegate)
        table.setItemDelegateForColumn(2, full_delegate)
        # Value 列使用 ValueButtonDelegate：保留文本显示，右侧绘制并响应一个方形按钮
        try:
            value_delegate = ValueButtonDelegate(table, clicked_callback=lambda idx: self._on_value_detail_requested(idx.row()))
            table.setItemDelegateForColumn(6, value_delegate)
        except Exception:
            # 若任意原因 delegate 创建失败，忽略以保证表格仍可工作
            pass

        # 三个下拉列：常态显示文本，编辑时整格显示下拉框
        fmt_delegate = ComboBoxDelegate(self._data_format_items, table)
        sess_delegate = ComboBoxDelegate(self._session_items, table)
        sec_delegate = ComboBoxDelegate(self._security_items, table)
        table.setItemDelegateForColumn(3, fmt_delegate)
        table.setItemDelegateForColumn(4, sess_delegate)
        table.setItemDelegateForColumn(5, sec_delegate)

        # 绑定视图信号
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

        # 初始化示例 DID 数据（正式使用时应从 DPT/配置加载）
        demo_rows = [
            DIDTableRow("GAC ECUHardwareVersion", "F17F"),
            DIDTableRow("ECUBootSoftwareVersion", "F180", data_format="HEX"),
        ]
        self.model.set_did_rows(demo_rows)

        # 打开 DID 页面时注册消息监听器
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

        # TODO: 将下面的 TX 构造和发送替换为真实的诊断服务调用
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

        # TODO: 将下面的 TX 构造和发送替换为真实的诊断服务调用
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
        """注册为 DataCenter ��监听者，确保仅注册一次。"""
        if not self._is_registered:
            self._data_center.register_listener(self)
            self._is_registered = True

    def _on_view_destroyed(self) -> None:
        """视图销毁时取消注册以避免悬挂引用。"""
        if self._is_registered:
            self._data_center.unregister_listener(self)
            self._is_registered = False

    def on_eth_message(self, raw_bytes: bytes, parsed):
        """DataCenter 回调入口：收到以太网报文后进行 DID 相关处理。"""
        if raw_bytes:
            self.on_response(raw_bytes)

    def on_response(self, payload: bytes):
        """处理收到的响应：刷新原始 RX 文本并尝试用 DPT 解析。"""
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
        """选择 DPT 文件后委托 DPTService 加载并保存路径。"""
        try:
            self._dpt_service.load_from_file(file_path)
            self.model.apply_update(dpt_path=file_path)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self.view, "DPT 导入失败", str(exc))

    def _handle_dpt_import(self) -> None:
        """处理视图发起的 DPT 导入：弹出文件对话框并调用加载接口。"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.view,
            "选择 DPT 文件",
            "",
            "DPT Files (*.DPT *.dpt);;All Files (*.*)",
        )
        if file_path:
            self.on_dpt_selected(file_path)

    def _handle_ecu_map_import(self) -> None:
        """处理 ECU 目的地址表导入（占位实现，后续替换为真实逻辑）。"""
        QtWidgets.QMessageBox.information(self.view, "提示", "ECU 目的地址表导入逻辑��实现")

    def on_model_changed(self):
        """模型更新时刷表格与原始数据显示。"""
        self._rebuild_table()
        self.view.raw_text.setText(self.model.raw_data)

    def get_view(self):
        """返回视图实例供外部容器使用。"""
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
            # 初始化该行的基础单元格
            self.view.build_row_widgets(r)

            # checkbox
            chk_item = table.item(r, 0)
            if chk_item is not None:
                chk_item.setCheckState(
                    Qt.Checked if row.selected else Qt.Unchecked
                )

            # Description
            desc_item = QtWidgets.QTableWidgetItem(row.description)
            # 确保 Description 可编辑（与 DID/Value 行为一致）
            flags = desc_item.flags()
            flags |= Qt.ItemIsEditable | Qt.ItemIsSelectable | Qt.ItemIsEnabled
            desc_item.setFlags(flags)
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

            # Value 列
            val_item = table.item(r, 6)
            if val_item is None:
                val_item = QtWidgets.QTableWidgetItem(row.value)
                table.setItem(r, 6, val_item)
            else:
                val_item.setText(row.value)

            # Value 列使用委托绘制右侧按钮并保持文本显示一致
            if getattr(row, "value_color", None):
                try:
                    color = QtGui.QColor(row.value_color)
                    val_item.setForeground(QtGui.QBrush(color))
                except Exception:
                    pass

        table.itemChanged.connect(self._on_item_changed)
        table.blockSignals(False)

    def _on_cell_clicked(self, row: int, col: int) -> None:
        """单击事件：在 Description/DID/Value 列直接进入编辑并全选文本，模拟 Excel 行为。"""
        table = self.view.table
        if col in (1, 2, 6):
            item = table.item(row, col)
            if item is not None:
                table.editItem(item)
                if col == 6:
                    QtCore.QTimer.singleShot(0, lambda: self.view.focus_value_editor(row, True))
                else:
                    QtCore.QTimer.singleShot(0, lambda: self._select_editor_text())

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        """双击事件：
        - Description/DID/Value：整格输入编辑；
        - 下拉列（3/4/5）：显示整格下拉框并尝试展开。"""
        table = self.view.table
        item = table.item(row, col)
        if item is None:
            return
        if col in (1, 2, 3, 4, 5, 6):
            table.editItem(item)
            if col == 6:
                QtCore.QTimer.singleShot(0, lambda: self.view.focus_value_editor(row, True))
            elif col in (1, 2):
                QtCore.QTimer.singleShot(0, lambda: self._select_editor_text())
            # 如果是下拉列，编辑器应该自动弹出下拉并且 popup 宽度填满单元格
            if col in (3, 4, 5):
                QtCore.QTimer.singleShot(0, lambda: self._show_combo_popup())

    def _show_combo_popup(self) -> None:
        """寻找当前焦点编辑器：如果是 QComboBox，则展开并尽量让 popup 与单元格宽度一致。"""
        editor = self.view.table.focusWidget()
        if isinstance(editor, QtWidgets.QComboBox):
            try:
                # ensure editor geometry matches the cell
                # showPopup 时 popup 的宽度会在 delegate 中被设置为 editor 的宽度
                editor.showPopup()
            except Exception:
                pass

    def _select_editor_text(self) -> None:
        """找到当前焦点编辑器（QLineEdit）并全选其文本。"""
        editor = self.view.table.focusWidget()
        if isinstance(editor, QtWidgets.QLineEdit):
            editor.selectAll()

    # -------------------- 表格行编辑/移动 --------------------

    def _on_add_row(self) -> None:
        """在末尾添加一条空白 DID 行。"""
        self.model.did_rows.append(DIDTableRow("", ""))
        self.model.dataChanged.emit()

    def _on_remove_row(self) -> None:
        """删除当前激活/选中的行。"""
        row = self.view.table.currentRow()
        if row < 0 or row >= len(self.model.did_rows):
            return
        del self.model.did_rows[row]
        self.model.dataChanged.emit()

    def _on_move_up(self) -> None:
        """将当前行上移一位（如可上移）。"""
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
        """将当��行下移一位（如可下移）。"""
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
        """表格单元格内容改变时将变更同步回模型（处理复选、文本与下拉列）。"""
        col = item.column()
        row = item.row()
        if row < 0 or row >= len(self.model.did_rows):
            return

        text = item.text()

        if col == 0:
            checked = item.checkState() == Qt.Checked
            self.model.update_row(row, selected=checked)
        elif col == 1:
            self.model.update_row(row, description=text)
        elif col == 2:
            self.model.update_row(row, did=text)
        elif col == 3:
            self.model.update_row(row, data_format=text)
        elif col == 4:
            self.model.update_row(row, diagnostic_session=text)
        elif col == 5:
            self.model.update_row(row, security_access=text)
        elif col == 6:
            # Value 列直接使用表格项文本同步到模型
            self.model.update_row(row, value=text)

    def _flush_value_cell(self, row: int) -> None:
        # 将表格中 Value 单元格的文本刷新到模型（兼容旧逻辑）
        table_item = self.view.table.item(row, 6)
        if table_item is None:
            return
        value = table_item.text()
        self.model.update_row(row, value=value)

    def _on_value_detail_requested(self, row: int) -> None:
        if row < 0 or row >= len(self.model.did_rows):
            return
        payload, error = self._get_row_bytes(row)
        if error:
            QtWidgets.QMessageBox.warning(self.view, "提示", error)
            return
        if not payload:
            QtWidgets.QMessageBox.information(self.view, "提示", "当前行无可解析数据")
            return
        if not self._dpt_service.is_ready():
            QtWidgets.QMessageBox.information(self.view, "提示", "请先导入 DPT 文件")
            return
        result = self._dpt_service.parse_bytes(payload)
        if not result:
            QtWidgets.QMessageBox.information(self.view, "提示", "解析失败或无结果")
            return

        dialog_parent = self.view
        if self._value_detail_dialog is not None:
            try:
                self._value_detail_dialog.close()
            except Exception:
                pass
        self._value_detail_dialog = ValueDetailDialog(dialog_parent, result, self.model.did_rows[row])
        self._value_detail_dialog.move(self._popup_position(row))
        self._value_detail_dialog.show()
        self._value_detail_dialog.finished.connect(lambda _: self._clear_value_dialog())

    def _clear_value_dialog(self) -> None:
        self._value_detail_dialog = None

    def _popup_position(self, row: int) -> QtCore.QPoint:
        table = self.view.table
        item = table.item(row, 6)
        if item is None:
            return self.view.mapToGlobal(self.view.rect().center())
        rect = table.visualItemRect(item)
        # 将弹窗放到该单元格右上角
        return table.viewport().mapToGlobal(rect.topRight())

    def _get_row_bytes(self, row: int) -> Tuple[Optional[bytes], Optional[str]]:
        info = self.model.did_rows[row]
        text = (info.value or "").strip()
        if not text:
            return None, "请先读取该 DID 获取值"
        fmt = (info.data_format or "STR").upper()
        try:
            if fmt == "HEX":
                filtered = "".join(ch for ch in text if ch not in {" ", "-"})
                if len(filtered) % 2:
                    filtered = "0" + filtered
                data = bytes.fromhex(filtered)
            else:
                if text.startswith("0x"):
                    data = bytes.fromhex(text[2:])
                else:
                    data = text.encode("utf-8", errors="ignore")
            return data, None
        except ValueError:
            return None, "Value 字段不是合法的十六进制字符串"


class ValueDetailDialog(QtWidgets.QDialog):
    def __init__(self, parent, result, row_info):
        super().__init__(parent)
        self.setWindowTitle(f"{row_info.description or row_info.did} 的 DPT 解析")
        self.setWindowFlag(Qt.Tool, True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setModal(False)
        self.resize(520, 360)
        layout = QtWidgets.QVBoxLayout(self)

        bytes_label = QtWidgets.QLabel(f"原始数据: {result.bytes_hex}")
        layout.addWidget(bytes_label)

        table = QtWidgets.QTableWidget(self)
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Bit", "Signal", "Binary", "Status"])
        table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        table.verticalHeader().setVisible(False)
        table.setRowCount(len(result.fields))
        for idx, field in enumerate(result.fields):
            table.setItem(idx, 0, QtWidgets.QTableWidgetItem(field.bit_range))
            table.setItem(idx, 1, QtWidgets.QTableWidgetItem(field.name))
            table.setItem(idx, 2, QtWidgets.QTableWidgetItem(field.raw_bits))
            status_parts = [str(field.physical_value)]
            if field.description:
                status_parts.append(f"({field.description})")
            table.setItem(idx, 3, QtWidgets.QTableWidgetItem(" ".join(status_parts)))
        layout.addWidget(table)

        close_btn = QtWidgets.QPushButton("关闭", self)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
