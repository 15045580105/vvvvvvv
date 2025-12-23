from typing import Optional, Tuple, cast, Any
import re

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt

from app.core.base_controller import BaseController
from app.core.dependency_injection import di_container
from app.services.device_manage.device_service import DeviceService
from app.services.configuration.config_service import AppConfigurationService
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
    ValueDetailDialog,
)
from app.services.diagnostic.dpt_service import DPTService
from app.common.utils.security_access_helper import SecurityAccessHelper


class DPTLoaderThread(QtCore.QThread):
    finished_signal = QtCore.pyqtSignal(bool, str)

    def __init__(self, dpt_service):
        super().__init__()
        self.dpt_service = dpt_service

    def run(self):
        try:
            if self.dpt_service.current_path:
                self.dpt_service.load_from_file(self.dpt_service.current_path, persist=False)
            self.finished_signal.emit(True, "")
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class DIDController(BaseController):
    """DID 控制器：负责界面交互、消息监听与 DPT 解析的协调逻辑。"""

    def __init__(self, parent=None, dpt_service: Optional[DPTService] = None):
        # 初始化模型 & 视图
        self.model = DIDModel(parent)
        self.view = DIDView(parent)
        # call BaseController to wire model/view signals
        super().__init__(self.model, self.view, parent)

        self._config_service = di_container.resolve(AppConfigurationService)
        if not self._config_service:
             self._config_service = AppConfigurationService()
             di_container.register_singleton(AppConfigurationService, self._config_service)

        self._device_service = di_container.resolve(DeviceService)
        if not self._device_service:
             self._device_service = DeviceService()
             di_container.register_singleton(DeviceService, self._device_service)

        # services and helpers
        self._dpt_service = dpt_service or DPTService()
        self._dpt_loader_thread: Optional[DPTLoaderThread] = None
        self._value_detail_dialog: Optional["ValueDetailDialog"] = None

        # 应用默认列比例（用于初始布局）：
        # [勾选, Description, DID, STR/HEX, DiagnosticSession, SecurityAccess, Value]
        # 第一列窄，Description 宽，Value 最宽以填充剩余空间。
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
        self.view.dpt_import_requested.connect(self._handle_dpt_import)
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


    # ---------- delegate 选项提供 ----------

    def _data_format_items(self, index: QtCore.QModelIndex):
        return self.model.data_format_options

    def _session_items(self, index: QtCore.QModelIndex):
        return self.model.session_options

    def _security_items(self, index: QtCore.QModelIndex):
        return self.model.security_options

    # -------------------- 顶部按钮行为 --------------------

    def _process_did_row(self, row_index: int, row, is_write: bool = False) -> None:
        """处理单行 DID 的读/写操作。

        流程：
        1. 获取 DoIP 客户端
        2. 切换 Diagnostic Session (0x10)
        3. 执行 Security Access (0x27)
        4. 执行 Read (0x22) 或 Write (0x2E)
        5. 更新 UI
        """
        if not self._device_service.get_doip_client():
            self.model.apply_update(rx="错误: 未连接 DoIP 设备")
            self.model.update_row(row_index, value_color="#EF4444")
            return

        # 1. 诊断会话控制 (0x10)
        target_session = 0x01
        sess_str = row.diagnostic_session

        # 1. 尝试解析 "0xXX" 格式 (支持括号、方括号或直接写)
        match = re.search(r"0x([0-9A-Fa-f]+)", sess_str)
        if match:
            target_session = int(match.group(1), 16)
        else:
            # 兼容旧逻辑或纯文本
            if "Programming" in sess_str:
                target_session = 0x02
            elif "Extended" in sess_str:
                target_session = 0x03
            elif "Default" in sess_str:
                target_session = 0x01
            else:
                try:
                    target_session = int(sess_str)
                except:
                    pass

        tx_session = bytes([0x10, target_session])
        self.model.apply_update(tx=f"会话控制: {tx_session.hex(' ').upper()}")
        rx_session = self._device_service.send_doip_payload(tx_session)

        if not rx_session or rx_session[0] != 0x50:
             self.model.apply_update(rx=f"会话控制失败: {rx_session.hex(' ').upper() if rx_session else '无响应'}")
             self.model.update_row(row_index, value_color="#EF4444")
             return
        self.model.apply_update(rx=f"会话控制成功: {rx_session.hex(' ').upper()}")

        # 2. 安全访问 (0x27)
        sec_level = 0
        sec_str = row.security_access

        # 如果是 Locked 或 None，则不进行安全访问
        if "Locked" in sec_str or "None" in sec_str:
            sec_level = 0
        else:
            # 尝试解析 "LevelX [0xXX]" 或 "0xXX" 格式
            match = re.search(r"0x([0-9A-Fa-f]+)", sec_str)
            if match:
                sec_level = int(match.group(1), 16)
            else:
                try:
                    if sec_str.isdigit():
                        sec_level = int(sec_str)
                    else:
                        # 尝试提取数字
                        nums = re.findall(r'\d+', sec_str)
                        if nums:
                            sec_level = int(nums[-1])
                except:
                    pass

        if sec_level > 0:
            # 请求种子: 27 Level (奇数)
            req_seed_level = sec_level
            if req_seed_level % 2 == 0:
                req_seed_level -= 1

            tx_seed = bytes([0x27, req_seed_level])
            self.model.apply_update(tx=f"请求种子: {tx_seed.hex(' ').upper()}")
            rx_seed = self._device_service.send_doip_payload(tx_seed)
            self.model.apply_update(rx=f"收到种子: {rx_seed.hex(' ').upper()}")
            if not rx_seed or rx_seed[0] != 0x67:
                self.model.apply_update(rx=f"请求种子失败: {rx_seed.hex(' ').upper() if rx_seed else '无响应'}")
                self.model.update_row(row_index, value_color="#EF4444")
                return

            # 计算密钥
            if len(rx_seed) < 3:
                 self.model.apply_update(rx=f"种子响应长度不足")
                 self.model.update_row(row_index, value_color="#EF4444")
                 return

            seed = rx_seed[2:]

            dll_path = self._config_service.diag_layer_settings.get("dll_path")
            if dll_path:
                key, error_msg = SecurityAccessHelper.calculate_key(sec_level, seed, dll_path=dll_path)
            else:
                key, error_msg = SecurityAccessHelper.calculate_key(sec_level, seed)

            if key:
                # 发送密钥: 27 Level+1 Key
                tx_key = bytes([0x27, req_seed_level + 1]) + key
                self.model.apply_update(tx=f"发送密钥: {tx_key.hex(' ').upper()}")
                rx_key = self._device_service.send_doip_payload(tx_key)

                if not rx_key or rx_key[0] != 0x67:
                    self.model.apply_update(rx=f"安全访问失败: {rx_key.hex(' ').upper() if rx_key else '无响应'}")
                    self.model.update_row(row_index, value_color="#EF4444")
                    return
                self.model.apply_update(rx=f"安全访问成功: {rx_key.hex(' ').upper()}")
            else:
                self.model.apply_update(rx=error_msg or "密钥计算失败")
                self.model.update_row(row_index, value_color="#EF4444")
                return

        # 3. 读/写 DID
        did_str = row.did.strip().replace(" ", "")
        try:
            did_val = int(did_str, 16)
        except ValueError:
            self.model.apply_update(rx=f"无效 DID: {did_str}")
            return

        hi = (did_val >> 8) & 0xFF
        lo = did_val & 0xFF

        if is_write:
            # 写入 (0x2E)
            value_str = row.value.strip()
            payload = b""

            # 处理 STR/HEX 格式
            fmt = (row.data_format or "STR").upper()
            try:
                if fmt == "HEX":
                    filtered = "".join(ch for ch in value_str if ch not in {" ", "-"})
                    if len(filtered) % 2:
                        filtered = "0" + filtered
                    payload = bytes.fromhex(filtered)
                else: # STR
                    payload = value_str.encode("utf-8")
            except ValueError:
                self.model.apply_update(rx=f"写入值无效: {value_str}")
                return

            tx_bytes = bytes([0x2E, hi, lo]) + payload
            self.model.apply_update(tx=f"写入 DID: {tx_bytes.hex(' ').upper()}")
            rx_bytes = self._device_service.send_doip_payload(tx_bytes)

            if not rx_bytes:
                self.model.apply_update(rx="写入失败: 无响应")
                self.model.update_row(row_index, value_color="#EF4444")
                return

            self.model.apply_update(rx=f"写入响应: {rx_bytes.hex(' ').upper()}")

            if rx_bytes[0] == 0x6E: # 肯定响应
                 self.model.update_row(row_index, value_color=None)
            else:
                 self.model.update_row(row_index, value_color="#EF4444")

        else:
            # 读取 (0x22)
            tx_bytes = bytes([0x22, hi, lo])
            self.model.apply_update(tx=f"读取 DID: {tx_bytes.hex(' ').upper()}")
            rx_bytes = self._device_service.send_doip_payload(tx_bytes)

            if not rx_bytes:
                self.model.apply_update(rx="读取失败: 无响应")
                self.model.update_row(row_index, value="", value_color="#EF4444")
                return

            self.model.apply_update(rx=f"读取响应: {rx_bytes.hex(' ').upper()}")

            # 解析响应: 62 DID_HI DID_LO DATA...
            if rx_bytes[0] == 0x62 and len(rx_bytes) >= 3:
                data_bytes = rx_bytes[3:]

                # 如果有 DPT 服务则解析
                rows = None
                if self._dpt_service.is_ready():
                    result = self._dpt_service.parse_bytes(rx_bytes)
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
                self.model.apply_update(rows=rows)

                # 根据 STR/HEX 设置格式化值
                fmt = (row.data_format or "STR").upper()
                display_val = ""
                if fmt == "HEX":
                    display_val = data_bytes.hex(' ').upper()
                else:
                    try:
                        display_val = data_bytes.decode("utf-8")
                    except:
                        display_val = data_bytes.hex(' ').upper() # 解码失败回退到 HEX

                self.model.update_row(row_index, value=display_val, value_color=None)
            else:
                self.model.update_row(row_index, value="", value_color="#EF4444")


    def _on_read_clicked(self) -> None:
        """点击“读取”：按勾选顺序处理每一行。"""
        selected_rows = [
            (idx, row)
            for idx, row in enumerate(self.model.did_rows)
            if row.selected
        ]
        if not selected_rows:
            QtWidgets.QMessageBox.information(self.view, "提示", "请先勾选需要读取的 DID")
            return

        if not self._device_service.get_doip_client():
             QtWidgets.QMessageBox.warning(self.view, "提示", "请先连接设备 (DoIP)")
             return

        for row_index, row in selected_rows:
            self._process_did_row(row_index, row, is_write=False)
            QtWidgets.QApplication.processEvents()

    def _on_write_clicked(self) -> None:
        """点击“写入”：按勾选顺序处理每一行。"""
        selected_rows = [
            (idx, row)
            for idx, row in enumerate(self.model.did_rows)
            if row.selected
        ]
        if not selected_rows:
            QtWidgets.QMessageBox.information(self.view, "提示", "请先勾选需要写入的 DID")
            return

        if not self._device_service.get_doip_client():
             QtWidgets.QMessageBox.warning(self.view, "提示", "请先连接设备 (DoIP)")
             return

        for row_index, row in selected_rows:
            self._process_did_row(row_index, row, is_write=True)
            QtWidgets.QApplication.processEvents()




    def on_dpt_selected(self, file_path: str) -> None:
        """选择 DPT 文件后委托 DPTService 加载并保存路径。"""
        try:
            self._dpt_service.load_from_file(file_path)
            self.model.apply_update(dpt_path=file_path)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self.view, "DPT 导入失败", str(exc))

    def _handle_dpt_import(self) -> None:
        """处理视图发起的 DPT 导入：弹出文件对话框并调用加载接口。"""
        current_path = self._dpt_service.current_path
        start_dir = ""

        if current_path:
            reply = QtWidgets.QMessageBox.question(
                self.view,
                "当前 DPT 路径",
                f"当前已设定 DPT 文件路径：\n{current_path}\n\n是否重新选择？",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes
            )
            if reply == QtWidgets.QMessageBox.No:
                return
            start_dir = current_path

        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.view,
            "选择 DPT 文件",
            start_dir,
            "DPT Files (*.xlsx *.xls);;All Files (*.*)",
        )
        if file_path:
            self.on_dpt_selected(file_path)


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

        if not self._dpt_service.current_path:
            QtWidgets.QMessageBox.information(self.view, "提示", "请先导入 DPT 文件")
            return

        if not self._dpt_service.is_ready():
            self._load_dpt_and_show_detail(row)
        else:
            self._show_value_detail_dialog(row, payload)

    def _load_dpt_and_show_detail(self, row: int):
        progress = QtWidgets.QProgressDialog("正在解析 DPT 文件...", "取消", 0, 0, self.view)
        progress.setModal(True)
        progress.setMinimumDuration(0)
        progress.setWindowTitle("请稍候")
        # Set cancel button
        progress.setCancelButtonText("取消")

        self._dpt_loader_thread = DPTLoaderThread(self._dpt_service)

        def on_finished(success, message):
            progress.close()
            if success:
                payload, error = self._get_row_bytes(row)
                if not error and payload:
                    self._show_value_detail_dialog(row, payload)
            else:
                # If it was not a manual cancellation (which we can't easily distinguish here without flag,
                # but if thread was terminated, this signal might not emit or emit with error)
                # Actually if we terminate, this slot won't be called.
                if message:
                    QtWidgets.QMessageBox.critical(self.view, "解析失败", message)

        self._dpt_loader_thread.finished_signal.connect(on_finished)

        def on_canceled():
            if self._dpt_loader_thread and self._dpt_loader_thread.isRunning():
                self._dpt_loader_thread.terminate()
                self._dpt_loader_thread.wait()

        progress.canceled.connect(on_canceled)
        progress.show()
        self._dpt_loader_thread.start()

    def _show_value_detail_dialog(self, row: int, payload: bytes):
        # 获取当前行的 DID
        did_str = self.model.did_rows[row].did

        result = self._dpt_service.parse_bytes(payload)
        if not result:
            QtWidgets.QMessageBox.information(self.view, "提示", "解析失败或无结果")
            return

        dialog_parent = self.view
        # 关闭旧对话框（运行时 _value_detail_dialog 为 QDialog 或 None，这里仅做 None 判断）
        dlg = cast(Any, self._value_detail_dialog)
        if dlg:
            try:
                dlg.close()
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
