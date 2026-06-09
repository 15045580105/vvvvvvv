from typing import Optional, Tuple, cast, Any
import re
import json
import os

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt

from app.common.ui.modern_widgets import MessageToast
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
from app.modules.ecu_initialization.controller.ecu_initialization_controller import ECUInitController
from app.common.utils.path_utils import get_app_data_path


_did_dir = os.path.join(get_app_data_path(), "DID")
if not os.path.exists(_did_dir):
    try:
        os.makedirs(_did_dir, exist_ok=True)
    except OSError:
        pass
DID_LIST_FILE = os.path.join(_did_dir, "did_list.json")


class DIDLoaderThread(QtCore.QThread):
    finished_signal = QtCore.pyqtSignal(list)

    def run(self):
        if not os.path.exists(DID_LIST_FILE):
            self.finished_signal.emit([])
            return
        try:
            with open(DID_LIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            rows = []
            for item in data:
                rows.append(DIDTableRow(
                    description=item.get("description", ""),
                    did=item.get("did", ""),
                    data_format=item.get("data_format", "STR"),
                    follow_dpt=item.get("follow_dpt", False),
                    diagnostic_session=item.get("diagnostic_session", "Default"),
                    security_access=item.get("security_access", "Locked"),
                    value=item.get("value", ""),
                    selected=item.get("selected", True)
                ))
            self.finished_signal.emit(rows)
        except Exception as e:
            print(f"Failed to load DID list: {e}")
            self.finished_signal.emit([])


class DIDProcessThread(QtCore.QThread):
    apply_update_signal = QtCore.pyqtSignal(dict)
    update_row_signal = QtCore.pyqtSignal(int, dict)
    warn_signal = QtCore.pyqtSignal(str)

    def __init__(self, selected_rows, is_write, resolve_dpt_params_func, device_service, dpt_service, config_service, parent=None):
        super().__init__(parent)
        self.selected_rows = selected_rows
        self.is_write = is_write
        self._resolve_dpt_params = resolve_dpt_params_func
        self._device_service = device_service
        self._dpt_service = dpt_service
        self._config_service = config_service

    def run(self):
        for row_index, row in self.selected_rows:
            self._process_did_row(row_index, row, self.is_write)
            # Sleep slightly to allow event loop processing if needed
            self.msleep(10)

    def _apply_update(self, **kwargs):
        self.apply_update_signal.emit(kwargs)

    def _update_row(self, row_index, **kwargs):
        self.update_row_signal.emit(row_index, kwargs)

    def _process_did_row(self, row_index: int, row, is_write: bool = False) -> None:
        target_session_name = row.diagnostic_session
        target_security_name = row.security_access

        if row.follow_dpt:
            if not self._dpt_service.is_ready():
                self.warn_signal.emit("DPT解析未完成，请稍候")
                return

            did_info = self._dpt_service.get_did_info(row.did)
            if did_info:
                target_session_name, target_security_name = self._resolve_dpt_params(
                    did_info, is_write
                )

        # 1. 诊断会话控制 (0x10)
        target_session = 0x01
        sess_str = target_session_name

        match = re.search(r"0x([0-9A-Fa-f]+)", sess_str)
        if match:
            target_session = int(match.group(1), 16)
        else:
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
                    if "Extended" in sess_str:
                        target_session = 0x03
                    pass

        tx_session = bytes([0x10, target_session])
        self._apply_update(tx=f"会话控制: {tx_session.hex(' ').upper()}")
        rx_session = self._device_service.send_doip_payload(tx_session)

        if not rx_session or rx_session[0] != 0x50:
             self._apply_update(rx=f"会话控制失败: {rx_session.hex(' ').upper() if rx_session else '无响应'}")
             self._update_row(row_index, value="", value_color="#EF4444")
             return
        self._apply_update(rx=f"会话控制成功: {rx_session.hex(' ').upper()}")

        # 2. 安全访问 (0x27)
        sec_level = 0
        sec_str = target_security_name

        if "Locked" in sec_str or "None" in sec_str:
            sec_level = 0
        else:
            match = re.search(r"0x([0-9A-Fa-f]+)", sec_str)
            if match:
                sec_level = int(match.group(1), 16)
            else:
                try:
                    if sec_str.isdigit():
                        sec_level = int(sec_str)
                    else:
                        nums = re.findall(r'\d+', sec_str)
                        if nums:
                            sec_level = int(nums[-1])
                except:
                    pass

        if sec_level > 0:
            req_seed_level = sec_level
            if req_seed_level % 2 == 0:
                req_seed_level -= 1

            tx_seed = bytes([0x27, req_seed_level])
            self._apply_update(tx=f"请求种子: {tx_seed.hex(' ').upper()}")
            rx_seed = self._device_service.send_doip_payload(tx_seed)
            self._apply_update(rx=f"收到种子: {rx_seed.hex(' ').upper()}")
            if not rx_seed or rx_seed[0] != 0x67:
                self._apply_update(rx=f"请求种子失败: {rx_seed.hex(' ').upper() if rx_seed else '无响应'}")
                self._update_row(row_index, value="", value_color="#EF4444")
                return

            if len(rx_seed) < 3:
                 self._apply_update(rx=f"种子响应长度不足")
                 self._update_row(row_index, value="", value_color="#EF4444")
                 return

            seed = rx_seed[2:]

            dll_path = self._config_service.diag_layer_settings.get("dll_path")
            if dll_path:
                key, error_msg = SecurityAccessHelper.calculate_key(sec_level, seed, dll_path=dll_path)
            else:
                key, error_msg = SecurityAccessHelper.calculate_key(sec_level, seed)

            if key:
                tx_key = bytes([0x27, req_seed_level + 1]) + key
                self._apply_update(tx=f"发送密钥: {tx_key.hex(' ').upper()}")
                rx_key = self._device_service.send_doip_payload(tx_key)

                if not rx_key or rx_key[0] != 0x67:
                    self._apply_update(rx=f"安全访问失败: {rx_key.hex(' ').upper() if rx_key else '无响应'}")
                    self._update_row(row_index, value="", value_color="#EF4444")
                    return
                self._apply_update(rx=f"安全访问成功: {rx_key.hex(' ').upper()}")
            else:
                self._apply_update(rx=error_msg or "密钥计算失败")
                self._update_row(row_index, value="", value_color="#EF4444")
                return

        # 3. 读/写 DID
        did_str = row.did.strip().replace(" ", "")
        try:
            did_val = int(did_str, 16)
        except ValueError:
            self._apply_update(rx=f"无效 DID: {did_str}")
            return

        hi = (did_val >> 8) & 0xFF
        lo = did_val & 0xFF

        if is_write:
            value_str = row.value.strip()
            payload = b""

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
                self._apply_update(rx=f"写入值无效: {value_str}")
                return

            tx_bytes = bytes([0x2E, hi, lo]) + payload
            self._apply_update(tx=f"写入 DID: {tx_bytes.hex(' ').upper()}")
            rx_bytes = self._device_service.send_doip_payload(tx_bytes)

            if not rx_bytes:
                self._apply_update(rx="写入失败: 无响应")
                self._update_row(row_index, value="", value_color="#EF4444")
                return

            self._apply_update(rx=f"写入响应: {rx_bytes.hex(' ').upper()}")

            if rx_bytes[0] == 0x6E:
                 self._update_row(row_index, value_color=None)
            else:
                 self._update_row(row_index, value_color="#EF4444")

        else:
            tx_bytes = bytes([0x22, hi, lo])
            self._apply_update(tx=f"读取 DID: {tx_bytes.hex(' ').upper()}")
            rx_bytes = self._device_service.send_doip_payload(tx_bytes)

            if not rx_bytes:
                self._apply_update(rx="读取失败: 无响应")
                self._update_row(row_index, value="", value_color="#EF4444")
                return

            self._apply_update(rx=f"读取响应: {rx_bytes.hex(' ').upper()}")

            if rx_bytes[0] == 0x62 and len(rx_bytes) >= 3:
                data_bytes = rx_bytes[3:]

                rows_parsed = None
                if self._dpt_service.is_ready():
                    did_clean = row.did.strip().replace(" ", "").upper()
                    if did_clean.startswith("0X"):
                        did_clean = did_clean[2:]

                    result = self._dpt_service.parse_bytes(data_bytes, did=did_clean)
                    if result:
                        rows_parsed = [
                            DIDBitRow(
                                bit=cols[0],
                                function=cols[1],
                                binary_value=cols[2],
                                status=cols[3],
                            )
                            for cols in result.to_table_rows()
                        ]
                self._apply_update(rows=rows_parsed)

                fmt = (row.data_format or "STR").upper()
                display_val = ""
                if fmt == "HEX":
                    display_val = data_bytes.hex(' ').upper()
                else:
                    try:
                        display_val = data_bytes.decode("utf-8")
                    except:
                        display_val = data_bytes.hex(' ').upper()

                self._update_row(row_index, value=display_val, value_color=None)
            else:
                self._update_row(row_index, value="", value_color="#EF4444")


class DIDController(BaseController):
    """DID 控制器：负责界面交互、消息监听与 DPT 解析的协调逻辑。"""
    switch_page = QtCore.pyqtSignal(dict, str)
    dpt_status_signal = QtCore.pyqtSignal(str, str)

    def __init__(self, parent=None, dpt_service: Optional[DPTService] = None):
        # 初始化模型 & 视图
        self.model = DIDModel(parent)
        self.view = DIDView(parent)

        # 标志位：指示是否正在处理来自 View 的更新
        # 用于防止 View -> Model -> View 的回环更新导致回弹或性能浪费
        self._is_handling_view_update = False

        # 初始化 ECU 初始化控制器，使用 DIDView 中的子视图
        self.ecu_init_controller = ECUInitController(parent, view=self.view.ecu_init_view)
        self.ecu_init_controller.log_message.connect(self.on_ecu_init_log)

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
        # Try to resolve DPTService from container first
        self._dpt_service = dpt_service or di_container.resolve(DPTService)
        if not self._dpt_service:
             self._dpt_service = DPTService()
             di_container.register_singleton(DPTService, self._dpt_service)

        # Register status callback
        self.dpt_status_signal.connect(self.handle_dpt_status)
        self._dpt_service.add_status_callback(self._on_dpt_status)

        self._value_detail_dialog: Optional["ValueDetailDialog"] = None

        # 应用默认列比例（用于初始布局）：
        # [勾选, Description, DID, STR/HEX, Follow DPT, DiagnosticSession, SecurityAccess, Value]
        # 第一列窄，Description 宽，Value 最宽以填充剩余空间。
        try:
            self.view.set_column_weights([1, 8, 3, 2, 2, 4, 4, 10])
        except Exception:
            pass

        # 在视图就绪后给出明确的像素宽度，以保证长表头能显示完整。
        # 通过 singleShot 延迟到布局完成时执行。
        try:
            QtCore.QTimer.singleShot(
                0,
                lambda: self.view.set_column_pixel_widths([30, 400, 100, 100, 150, 200, 200, 600]),
            )
        except Exception:
            pass

        # reference table from view
        table = self.view.table

        # 为 Description（列1）、DID（列2）与 Value（列7）使用整格编辑委托，
        # 以保证编辑器覆盖整格并使用不透明背景，避免重影问题。
        full_delegate = FullCellDelegate(self.view.table)
        table.setItemDelegateForColumn(1, full_delegate)
        table.setItemDelegateForColumn(2, full_delegate)
        # Value 列使用 ValueButtonDelegate：保留文本显示，右侧绘制并响应一个方形按钮
        try:
            value_delegate = ValueButtonDelegate(table, clicked_callback=lambda idx: self._on_value_detail_requested(idx.row()))
            table.setItemDelegateForColumn(7, value_delegate)
        except Exception:
            # 若任意原因 delegate 创建失败，忽略以保证表格仍可工作
            pass

        # 三个下拉列：常态显示文本，编辑时整格显示下拉框
        fmt_delegate = ComboBoxDelegate(self._data_format_items, table)
        sess_delegate = ComboBoxDelegate(self._session_items, table)
        sec_delegate = ComboBoxDelegate(self._security_items, table)
        table.setItemDelegateForColumn(3, fmt_delegate)
        table.setItemDelegateForColumn(5, sess_delegate)
        table.setItemDelegateForColumn(6, sec_delegate)

        # 绑定视图信号
        self.view.value_detail_requested.connect(self._on_value_detail_requested)
        self.view.search_btn.clicked.connect(self._on_search_clicked)
        self.view.search_input.returnPressed.connect(self._on_search_clicked)
        self.view.read_requested.connect(self._on_read_clicked)
        self.view.write_requested.connect(self._on_write_clicked)
        self.view.clear_requested.connect(self._on_clear_clicked)
        self.view.add_row_requested.connect(self._on_add_row)
        self.view.remove_row_requested.connect(self._on_remove_row)
        self.view.move_up_requested.connect(self._on_move_up)
        self.view.move_down_requested.connect(self._on_move_down)
        self.view.move_top_requested.connect(self._on_move_top)

        # 表格交互行为：完全由 controller 控制
        self.view.cell_clicked.connect(self._on_cell_clicked)
        self.view.cell_double_clicked.connect(self._on_cell_double_clicked)

        # 连接表头复选框信号
        header = self.view.table.horizontalHeader()
        if hasattr(header, "checkBoxClicked"):
            header.checkBoxClicked.connect(self._on_header_checkbox_toggled)

        # 启用表头排序
        header.sectionClicked.connect(self._on_header_section_clicked)
        self._sort_col = -1
        self._sort_order = Qt.AscendingOrder

        # 加载保存的 DID 列表
        self._load_dids_from_file()


    def _on_dpt_status(self, status, message):
        self.dpt_status_signal.emit(status, message)

    def handle_dpt_status(self, status, message):
        # We no longer show toast here, as the main controller handles global Toasts. 
        # But we still log it.
        self.view.append_log(f"系统: {message}")

    def _save_dids_to_file(self):
        """保存当前 DID 列表到文件。"""
        data = []
        for row in self.model.did_rows:
            data.append({
                "description": row.description,
                "did": row.did,
                "data_format": row.data_format,
                "follow_dpt": row.follow_dpt,
                "diagnostic_session": row.diagnostic_session,
                "security_access": row.security_access,
                "value": row.value,
                "selected": row.selected
            })
        try:
            with open(DID_LIST_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save DID list: {e}")

    def _load_dids_from_file(self):
        """从文件加载 DID 列表（异步）。"""
        self._loader_thread = DIDLoaderThread()
        self._loader_thread.finished_signal.connect(self._on_dids_loaded)
        self._loader_thread.start()

    def _on_dids_loaded(self, rows):
        if rows:
            self.model.set_did_rows(rows)
        self._loader_thread = None


    def _on_clear_clicked(self) -> None:
        """Handle clear button clicked."""
        self.model.reset_raw_log()
        self.model.clear_all_values()

        # Manually clear text area in view if model change doesn't trigger it fast enough or if binding is missing
        # The model.reset_raw_log() cleans model data, but we should make sure View is updated.
        # on_model_changed calls view.raw_text.setText(self.model.raw_data)
        # on_model_changed calls _rebuild_table()
        # So it should be handled automatically by on_model_changed if connected properly.
        # BaseController connects model.dataChanged to on_model_changed.
        # Let's verify base_controller later, but assuming standard MV pattern here.

        # Also clean up any lingering toast or errors if needed? No, just data.


    # ---------- delegate 选项提供 ----------

    def _data_format_items(self, index: QtCore.QModelIndex):
        return self.model.data_format_options

    def _session_items(self, index: QtCore.QModelIndex):
        return self.model.session_options

    def _security_items(self, index: QtCore.QModelIndex):
        return self.model.security_options

    def _resolve_dpt_params(self, did_info: dict, is_write: bool) -> Tuple[str, str]:
        """根据 DPT 信息解析应使用的会话与安全等级。"""
        sess_map = did_info.get("raw_session_support", {})
        sec_map = did_info.get("raw_security_support", {})
        syn_sess = str(did_info.get("diagnostic_session", ""))
        syn_sec = str(did_info.get("security_access", ""))

        # Helper: 解析支持状态 (x=读, x/x=读/写, -/-=不支持)
        def _check_support(val, specific_access="READ"):
             s = str(val).strip().upper()
             # Explicit Not Supported or empty
             if not s or s in ["-", "N/A", "NONE", "0", "FALSE", "-/-"]:
                 return False

             # Case 1: Slash Format "X/Y" (Read/Write)
             if "/" in s:
                 parts = s.split("/")
                 if len(parts) >= 2:
                     read_part = parts[0].strip()
                     write_part = parts[1].strip()

                     # Check Write Part
                     can_write = write_part in ["X", "O", "1", "YES", "TRUE", "SUPPORT", "SUPPORTED"]
                     # Check Read Part
                     can_read = read_part in ["X", "O", "1", "YES", "TRUE", "SUPPORT", "SUPPORTED"]

                     if specific_access == "WRITE":
                         return can_write
                     else: # READ
                         return can_read

             # Case 2: Standard Boolean Strings (unambiguous support)
             if s in ["O", "YES", "TRUE", "SUPPORT", "SUPPORTED", "1"]:
                 return True

             # Case 3: Single "X" -> Implies Read Only (as per user rule "单独的x就是读")
             if s == "X":
                  return specific_access == "READ"

             return False

        # Priority Lists (Map key -> Display Name)
        # Session Priority: Extended -> Default -> Programming
        session_prio = [("extended", "Extended (0x03)"), ("default", "Default (0x01)"), ("programming", "Programming (0x02)")]

        # Security Priority: Level 1 -> Level 2 -> Level 3 -> Flash -> Locked
        sec_keys_prio = ["level1", "level2", "level3", "level_flash", "locked"]

        # Model Value Mappings
        sec_value_map = {
            "level1": "Level1 [0x01]",
            "level2": "Level2 [0x03]",
            "level3": "Level3 [0x21]",
            "level_flash": "Level Flash [0x11]",
            "locked": "Locked"
        }

        # Defaults
        target_sess = "Extended (0x03)"
        target_sec = "Level1 [0x01]"

        # --- 1. SESSION RESOLUTION ---
        best_sess = None
        access_mode = "WRITE" if is_write else "READ"

        def find_sess(mode):
             for k, display_name in session_prio:
                 val = sess_map.get(k)
                 if _check_support(val, mode):
                     return display_name
             return None

        # Try to find session supporting desired access
        best_sess = find_sess(access_mode)

        # Fallback logic: If Write requested but no session supports Write,
        # fallback to finding a Read session (User req: "不可写则按照读执行")
        if not best_sess and is_write:
             best_sess = find_sess("READ")

        if best_sess:
             target_sess = best_sess
        else:
             # Fallback to synthesized string if available (Legacy/Info fallback)
             if syn_sess and "Default" in syn_sess: target_sess = "Default (0x01)"
             elif syn_sess and "Programming" in syn_sess: target_sess = "Programming (0x02)"
             # Else keep Extended default

        # --- 2. SECURITY RESOLUTION ---
        best_sec = None

        def find_sec(mode):
             for k in sec_keys_prio:
                 val = sec_map.get(k)
                 if _check_support(val, mode):
                     return sec_value_map.get(k, "Locked")
             return None

        best_sec = find_sec(access_mode)
        if not best_sec and is_write:
             best_sec = find_sec("READ")

        if best_sec:
             target_sec = best_sec
        else:
             # Fallback to synthesized string
             if "Locked" in syn_sec: target_sec = "Locked"
             elif "Level 1" in syn_sec: target_sec = "Level1 [0x01]"
             elif "Level 2" in syn_sec: target_sec = "Level2 [0x03]"
             elif "Level 3" in syn_sec: target_sec = "Level3 [0x21]"
             elif "Flash" in syn_sec: target_sec = "Level Flash [0x11]"

        return target_sess, target_sec

    # -------------------- 顶部按钮行为 --------------------

    def _process_did_row(self, row_index: int, row, is_write: bool = False) -> None:
        """这个方法已在后台线程实现。不应被直接调用。"""
        pass

    def _on_search_clicked(self):
        """Handle search button clicked or Enter pressed."""
        text = self.view.search_input.text().strip().lower()
        if not text:
            return

        # Start search from current selection + 1, or from 0
        start_row = 0
        current_rows = self.view.table.selectionModel().selectedRows()
        if current_rows:
            start_row = current_rows[0].row() + 1

        row_count = self.view.table.rowCount()
        found_row = -1

        # Search from start_row to end
        for i in range(start_row, row_count):
            if self._match_row(i, text):
                found_row = i
                break

        # If not found, Wrap around logic
        if found_row == -1 and start_row > 0:
             for i in range(0, start_row):
                 if self._match_row(i, text):
                    found_row = i
                    break

        if found_row != -1:
            self.view.table.scrollToItem(self.view.table.item(found_row, 0))
            self._highlight_search_row(found_row)
        else:
            MessageToast(self.view).show_toast("未找到匹配的 DID", 1)

    def _highlight_search_row(self, row: int):
        """Temporarily highlight the found row with a noticeable color."""
        self.view.table.clearSelection()
        self.view.table.selectRow(row)

        orig_style = self.view.table.styleSheet()
        if "#FDE047" not in orig_style:
            self._normal_stylesheet = orig_style

        # 修改选中行的背景色为亮黄色
        new_style = getattr(self, "_normal_stylesheet", orig_style).replace("#bfdbfe", "#FDE047")
        self.view.table.setStyleSheet(new_style)

        if hasattr(self, "_highlight_timer"):
            self._highlight_timer.stop()
        else:
            self._highlight_timer = QtCore.QTimer()
            self._highlight_timer.setSingleShot(True)
            self._highlight_timer.timeout.connect(self._restore_highlight)

        self._highlight_timer.start(1200)

    def _restore_highlight(self):
        if hasattr(self, "_normal_stylesheet"):
            self.view.table.setStyleSheet(self._normal_stylesheet)

    def _match_row(self, row, text):
        """Check if DID (col 2) matches text."""
        # Check DID column (index 2)
        item = self.view.table.item(row, 2) # DID
        if item and text in item.text().lower():
            return True
        return False

    def _on_read_clicked(self) -> None:
        """点击“读取”：按勾选顺序处理每一行。"""
        selected_rows = [
            (idx, row)
            for idx, row in enumerate(self.model.did_rows)
            if row.selected
        ]
        if not selected_rows:
            MessageToast(self.view).show_toast("请先勾选需要读取的 DID", 2)
            return

        if not self._device_service.get_doip_client():
            MessageToast(self.view).show_toast("请先连接设备 (DoIP)", 1)
            return

        self.view.read_btn.setEnabled(False)
        self.view.write_btn.setEnabled(False)
        self.view.clear_btn.setEnabled(False)

        # Clear value and status for selected rows before reading
        if selected_rows:
            for row_index, row in selected_rows:
                self.model.update_row(row_index, emit_signal=False, value="", value_color=None)
            self.model.dataChanged.emit()

        self._start_process_thread(selected_rows, is_write=False)

    def _on_write_clicked(self) -> None:
        """点击“写入”：按勾选顺序处理每一行。"""
        selected_rows = [
            (idx, row)
            for idx, row in enumerate(self.model.did_rows)
            if row.selected
        ]
        if not selected_rows:
            MessageToast(self.view).show_toast("请先勾选需要写入�� DID", 2)
            return

        if not self._device_service.get_doip_client():
             MessageToast(self.view).show_toast("请先连接设备 (DoIP)", 1)
             return

        self.view.read_btn.setEnabled(False)
        self.view.write_btn.setEnabled(False)
        self.view.clear_btn.setEnabled(False)

        # Clear status for selected rows before writing
        if selected_rows:
            for row_index, row in selected_rows:
                self.model.update_row(row_index, emit_signal=False, value_color=None)
            self.model.dataChanged.emit()

        self._start_process_thread(selected_rows, is_write=True)

    def _start_process_thread(self, selected_rows, is_write: bool):
        self._process_thread = DIDProcessThread(
            selected_rows,
            is_write,
            self._resolve_dpt_params,
            self._device_service,
            self._dpt_service,
            self._config_service,
            self
        )
        self._process_thread.apply_update_signal.connect(lambda kwargs: self.model.apply_update(**kwargs))
        self._process_thread.update_row_signal.connect(lambda idx, kwargs: self.model.update_row(idx, **kwargs))
        self._process_thread.warn_signal.connect(lambda msg: MessageToast(self.view).show_toast(msg, 2))
        self._process_thread.finished.connect(self._on_process_finished)
        self._process_thread.start()

    def _on_process_finished(self):
        self.view.read_btn.setEnabled(True)
        self.view.write_btn.setEnabled(True)
        self.view.clear_btn.setEnabled(True)
        self._process_thread.deleteLater()
        self._process_thread = None

    def on_ecu_init_log(self, type_: str, message: str) -> None:
        """Handle log messages from ECUInitController."""
        if type_ == "TX":
            self.model.apply_update(tx=message)
        elif type_ == "RX":
            self.model.apply_update(rx=message)
        else:
            self.model.apply_update(rx=f"[{type_}] {message}")

    def _on_ecu_init_requested(self) -> None:
        """点击 ECU 初始化按钮，切换到 ECU 初始化界面。"""
        # 视图层已处理显示/隐藏逻辑，此处可添加业务逻辑（如初始化数据）
        pass

    def _format_log_html(self, log_entry: str) -> str:
        color = "#374151" 
        if "] TX" in log_entry:
            color = "#2563EB"
        elif "] RX" in log_entry:
            color = "#059669"
        elif "Error" in log_entry or "失败" in log_entry or "错误" in log_entry or "Fail" in log_entry:
            color = "#DC2626"
        elif "Warning" in log_entry or "警告" in log_entry:
            color = "#D97706"
        
        log_escaped = log_entry.replace("<", "&lt;").replace(">", "&gt;")
        return f'<span style="color: {color};">{log_escaped}</span>'

    def _update_raw_text(self):
        current_log_count = len(self.model.raw_log)
        last_count = getattr(self, '_last_log_count', 0)

        # Check if we should append incrementally
        if current_log_count > last_count > 0:
            for i in range(last_count, current_log_count):
                self.view.raw_text.append(self._format_log_html(self.model.raw_log[i]))
        else:
            # Full replace if count decreased (cleared) or it's first update
            self.view.raw_text.clear()
            for line in self.model.raw_log:
                self.view.raw_text.append(self._format_log_html(line))
            self.view.raw_text.moveCursor(QtGui.QTextCursor.End)

        self._last_log_count = current_log_count

    def on_model_changed(self):
        """模型更新时刷表格与原始数据显示。"""
        # 如果变更源自 View 自身的操作（如用户点击复选框），则无需反向刷新 View
        if self._is_handling_view_update:
            # 仅更新日志显示（如果需要），跳过表格重建
            self._update_raw_text()
            return

        # 针对编辑操作被回滚的问题：
        # 如果 View 中有编辑器正在打开（处于编辑模式），我们应该非常谨慎地更新
        # 否则更新操作会关闭编辑器，导致用户正在输入的内容丢失
        if self.view.table.state() == QtWidgets.QAbstractItemView.EditingState:
            # 如果处于编辑状态，且数据更新不是破坏性的（比如仅仅是某个非当前编辑单元格的值变了）
            # 我们可以尝试只更新其他单元格。或者如果不紧急，暂时推迟更新？
            # 简单起见，如果正在编辑，我们暂缓自动刷新，除非行数变了这种大动作。
            # 但是如果读取操作返回了结果，我们需要显示结果。
            # 如果读取操作返回结果，��常用户不是在编辑同一行。

            # 所以，diff update 策略配合 blockSignals 应该能保住编辑器？
            # 不，setItem 设置文本可能会导致编辑器关闭（如果是在同一个 cell）。
            # 如果是其他 cell，应该没事？ QTableWidget 可能会在 setItem 时关闭所有编辑器。
            # 测试表明 QTableWidget.setItem 会打断编辑。

            # 策略：如果处于编辑状态，我们应该检测当前编辑的是哪个 cell，然后不更新那个 cell 的 item。
            # 获取当前正在编辑的 item
            current_item = self.view.table.currentItem()
            # 或者 better: current index
            current_index = self.view.table.currentIndex()
        else:
            current_index = QtCore.QModelIndex()

        # 其他情况（如排序、加载文件、后台数据更新）需要刷新表格

        # 彻底解决之道：
        # 检测行数是否变化，或者顺序是否变化

        # 1. 检测行数
        current_row_count = self.view.table.rowCount()
        model_row_count = len(self.model.did_rows)

        needs_rebuild = False
        if current_row_count != model_row_count:
            needs_rebuild = True
        else:
            # 检查顺序 UserRole
            for r in range(model_row_count):
                item = self.view.table.item(r, 0)
                if not item:
                    needs_rebuild = True
                    break
                row_data = item.data(Qt.UserRole)
                if row_data is not self.model.did_rows[r]:
                    needs_rebuild = True
                    break

        if not needs_rebuild:
            # 如果不需要全量重建，这里应该只是刷新一下值（针对非 View 触发的更新，例如 Read 操作返回结果）
            # 我们需要一种机制来更新 View 中的值而不重建 Item
            # 遍历所有行，检查值是否一致并更新
            table = self.view.table
            table.blockSignals(True) # 防止更新 View 时又触发 itemChanged
            try:
                for r, row in enumerate(self.model.did_rows):
                    # Checkbox
                    chk_item = table.item(r, 0)
                    if chk_item:
                        new_state = Qt.Checked if row.selected else Qt.Unchecked
                        if chk_item.checkState() != new_state:
                            chk_item.setCheckState(new_state)

                    # Description (Col 1)
                    if not (current_index.isValid() and current_index.row() == r and current_index.column() == 1):
                        desc_item = table.item(r, 1)
                        if desc_item and desc_item.text() != row.description:
                            desc_item.setText(row.description)

                    # DID (Col 2)
                    if not (current_index.isValid() and current_index.row() == r and current_index.column() == 2):
                        did_item = table.item(r, 2)
                        if did_item and did_item.text() != row.did:
                            did_item.setText(row.did)

                    # Format (Col 3)
                    if not (current_index.isValid() and current_index.row() == r and current_index.column() == 3):
                        fmt_item = table.item(r, 3)
                        if fmt_item and fmt_item.text() != row.data_format:
                            fmt_item.setText(row.data_format)

                    # Follow DPT (Col 4)
                    dpt_item = table.item(r, 4)
                    if dpt_item:
                        new_dpt_state = Qt.Checked if row.follow_dpt else Qt.Unchecked
                        if dpt_item.checkState() != new_dpt_state:
                            dpt_item.setCheckState(new_dpt_state)

                    # Session (Col 5)
                    if not (current_index.isValid() and current_index.row() == r and current_index.column() == 5):
                        sess_item = table.item(r, 5)
                        if sess_item and sess_item.text() != row.diagnostic_session:
                            sess_item.setText(row.diagnostic_session)

                    # Security (Col 6)
                    if not (current_index.isValid() and current_index.row() == r and current_index.column() == 6):
                        sec_item = table.item(r, 6)
                        if sec_item and sec_item.text() != row.security_access:
                            sec_item.setText(row.security_access)

                    # Value (Col 7)
                    if not (current_index.isValid() and current_index.row() == r and current_index.column() == 7):
                        val_item = table.item(r, 7)
                        if val_item:
                            if val_item.text() != row.value:
                                val_item.setText(row.value)
                            # Color - always safe to update?
                            if getattr(row, "value_color", None):
                                val_item.setForeground(QtGui.QBrush(QtGui.QColor(row.value_color)))
                            else:
                                val_item.setForeground(QtWidgets.QApplication.palette().text())

            finally:
                table.blockSignals(False)
        else:
            # 如果确实需要重建（行数变了，或者顺序变了）
            # Save current state
            h_scroll = self.view.table.horizontalScrollBar().value()
            v_scroll = self.view.table.verticalScrollBar().value()
            current_row = self.view.table.currentRow()

            # Rebuild table
            self._rebuild_table()

            # Restore state
            self.view.table.horizontalScrollBar().setValue(h_scroll)
            self.view.table.verticalScrollBar().setValue(v_scroll)
            if current_row >= 0 and current_row < self.view.table.rowCount():
                self.view.table.selectRow(current_row)

        # Update raw text log
        self._update_raw_text()

    # 被移除的拖拽逻辑占位
    # def _on_row_moved_by_drag(self, from_row: int, to_row: int):
    #     """Handle exact row move from view drag & drop."""
    #     if from_row == to_row:
    #         return
    #     if from_row < 0 or from_row >= len(self.model.did_rows):
    #         return
    #     if to_row < 0 or to_row > len(self.model.did_rows):
    #         return
    #
    #     # Perform list move
    #     row_data = self.model.did_rows.pop(from_row)
    #
    #     # Adjust insertion index if moving down
    #     # When removing from 'from_row', all subsequent indices shift down by 1.
    #     # If we insert at a position > from_row, that position has conceptually shifted.
    #     if from_row < to_row:
    #         to_row -= 1
    #
    #     self.model.did_rows.insert(to_row, row_data)
    #
    #     self.model.dataChanged.emit()
    #     self._save_dids_to_file()
    #     # Force visual refresh to match model index order
    #     self._rebuild_table()


    def get_view(self):
        """返回视图实例供外部容器使用。"""
        return self.view

    # -------------------- 表格构建与交互 --------------------

    def _rebuild_table(self) -> None:
        table = self.view.table
        rows = self.model.did_rows
        # 临时断开信号防止重置时触发改变
        table.blockSignals(True)
        table.setRowCount(len(rows))

        try:
            table.itemChanged.disconnect(self._on_item_changed)
        except TypeError:
            pass

        for r, row in enumerate(rows):
            # 初始化该行的基础单元格
            self.view.build_row_widgets(r)

            # checkbox (Column 0) - Fixed: Ensure flags are set correctly
            chk_item = table.item(r, 0)
            if chk_item is not None:
                # Ensure ItemIsUserCheckable is set
                chk_item.setFlags(chk_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                chk_item.setCheckState(
                    Qt.Checked if row.selected else Qt.Unchecked
                )
                # Store the row object for drag & drop reordering
                chk_item.setData(Qt.UserRole, row)

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

            # Follow DPT
            dpt_item = QtWidgets.QTableWidgetItem()
            # Ensure ItemIsUserCheckable is set for column 4 as well
            dpt_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            dpt_item.setCheckState(Qt.Checked if row.follow_dpt else Qt.Unchecked)
            dpt_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            table.setItem(r, 4, dpt_item)

            # DiagnosticSession
            sess_item = QtWidgets.QTableWidgetItem(row.diagnostic_session)
            table.setItem(r, 5, sess_item)

            # SecurityAccess
            sec_item = QtWidgets.QTableWidgetItem(row.security_access)
            table.setItem(r, 6, sec_item)

            # Value 列
            val_item = table.item(r, 7)
            if val_item is None:
                val_item = QtWidgets.QTableWidgetItem(row.value)
                table.setItem(r, 7, val_item)
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
        if col in (1, 2, 7):
            item = table.item(row, col)
            if item is not None:
                table.editItem(item)
                if col == 7:
                    QtCore.QTimer.singleShot(0, lambda: self.view.focus_value_editor(row, True))
                else:
                    QtCore.QTimer.singleShot(0, lambda: self._select_editor_text())

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        """双击事件：
        - Description/DID/Value：整格输入编辑；
        - 下拉列（3/5/6）：显示整格下拉框并尝试展开。"""
        table = self.view.table
        item = table.item(row, col)
        if item is None:
            return
        if col in (1, 2, 3, 5, 6, 7):
            table.editItem(item)
            if col == 7:
                QtCore.QTimer.singleShot(0, lambda: self.view.focus_value_editor(row, True))
            elif col in (1, 2):
                QtCore.QTimer.singleShot(0, lambda: self._select_editor_text())
            # 如果是下拉列，编辑器应该自动弹出下拉并且 popup 宽度填满单元格
            if col in (3, 5, 6):
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
        self._save_dids_to_file()

    def _on_remove_row(self) -> None:
        """删除当前选中的行（支持多选）。"""
        selected_row_indices = sorted(
            list(set(index.row() for index in self.view.table.selectedIndexes())),
            reverse=True
        )
        if not selected_row_indices:
            # Fallback to currentRow if no selection via selection model
            row = self.view.table.currentRow()
            if row >= 0 and row < len(self.model.did_rows):
                selected_row_indices = [row]
            else:
                return

        for row in selected_row_indices:
            if 0 <= row < len(self.model.did_rows):
                del self.model.did_rows[row]

        self.model.dataChanged.emit()
        self._save_dids_to_file()

    def _on_move_up(self) -> None:
        """将选中行上移（支持多选）。"""
        selected_rows = sorted(
            list(set(index.row() for index in self.view.table.selectedIndexes()))
        )
        if not selected_rows:
            return

        if selected_rows[0] == 0:
            return

        # Swap with previous
        new_selection = []
        for r in selected_rows:
            self.model.did_rows[r-1], self.model.did_rows[r] = self.model.did_rows[r], self.model.did_rows[r-1]
            new_selection.append(r-1)

        self.model.dataChanged.emit()
        self._save_dids_to_file()

        # Restore selection
        # Need re-selection logic after table rebuild triggered by dataChanged
        # Wait, dataChanged -> on_model_changed -> _rebuild_table clears selection.
        # But we can try to restore it.
        # Actually _rebuild_table clears selection.
        # We should improve on_model_changed or restore logic here.
        # Since _rebuild_table is connected to dataChanged via BaseController...
        # Let's hope the view update preserves it or we have to force it.
        # But for now, we trigger view update first.
        # However, _rebuild_table is called.
        pass

        # Since table is rebuilt, we need to select rows in the view
        # We should do it via a timer or directly if synchronous
        for r in new_selection:
            self.view.table.selectRow(r)

    def _on_move_down(self) -> None:
        """将选中行下移（支持多选）。"""
        selected_rows = sorted(
            list(set(index.row() for index in self.view.table.selectedIndexes())),
            reverse=True
        )
        if not selected_rows:
            return

        if selected_rows[0] == len(self.model.did_rows) - 1:
            return

        new_selection = []
        for r in selected_rows:
            self.model.did_rows[r+1], self.model.did_rows[r] = self.model.did_rows[r], self.model.did_rows[r+1]
            new_selection.append(r+1)

        self.model.dataChanged.emit()
        self._save_dids_to_file()

        for r in new_selection:
            self.view.table.selectRow(r)


    def _on_move_top(self) -> None:
        """将选中的行（高亮行）移动到列表顶部（保持相对顺序），忽略复选框状态。"""
        # 获取当前视图中选中的所有行索引
        selected_model_indexes = self.view.table.selectionModel().selectedRows()

        target_indices = []
        if selected_model_indexes:
            # 提取行号并排序
            target_indices = sorted([idx.row() for idx in selected_model_indexes])
        else:
            # 备选：如果 selectionModel 为空，尝试 currentRow
            current_row = self.view.table.currentRow()
            if current_row >= 0 and current_row < len(self.model.did_rows):
                target_indices = [current_row]

        if not target_indices:
            MessageToast(self.view).show_toast("请先选中一行或多行需要置顶的数据", 2)
            return

        # 优化：如果已经在顶部，则无需操作
        # 检查 target_indices 是否已经是 0, 1, 2... len-1
        if target_indices == list(range(len(target_indices))):
            return

        # 分离目标行和其他行
        target_rows = []
        other_rows = []

        # 使用 set 加速查找
        target_indices_set = set(target_indices)

        # 按照 model 的原始顺序遍历，这样保持相对顺序稳定
        for i, row in enumerate(self.model.did_rows):
            if i in target_indices_set:
                target_rows.append(row)
            else:
                other_rows.append(row)

        new_rows = target_rows + other_rows

        if new_rows != self.model.did_rows:
            self.model.did_rows = new_rows
            self.model.dataChanged.emit()
            self._save_dids_to_file()

            # 操作后体验优化：
            # 1. 滚动到顶部
            self.view.table.scrollToTop()
            # 2. 选中/高亮被置顶的行
            self.view.table.clearSelection()

            # 由于可能一次置顶多行，且新位置在 0 到 len(target_rows)-1
            # 重新选中这些行
            if target_rows:
                # 构造一个选择区域：从第0行到第N行，覆盖所有列
                top_range = QtWidgets.QTableWidgetSelectionRange(
                    0, 0, len(target_rows) - 1, self.view.table.columnCount() - 1
                )
                self.view.table.setRangeSelected(top_range, True)
                # 将焦点设置到第一行
                self.view.table.setCurrentCell(0, 0)

    def _on_header_checkbox_toggled(self, column_index: int, checked: bool) -> None:
        """处理表头复选框点击事件：全选/全不选。"""
        # 批量更新模型
        if column_index == 0:  # Checkbox column
            for row in self.model.did_rows:
                row.selected = checked
        elif column_index == 4:  # Follow DPT column
            for row in self.model.did_rows:
                row.follow_dpt = checked

        # 触发 Model 更新信号
        # 注意：因为我们在 on_model_changed 中跳过了非结构性变更的 Rebuild，
        # 所以这里全选操作后，必须手动刷新 View，或者让 on_model_changed 知道需要强制刷新。
        # 但既然��们现在修改了 model 中的对象，而 View 还持有旧状态（如果之前没有 rebuild），
        # View 并不会自动变成 checked，因为 View 中的 Item 还没变。
        # 所以全选这种批量操作需要强制 Rebuild 或批量更新 View。
        self._rebuild_table()

        # 触发保存和信号（可选，如果 _rebuild_table 不发信号的话）
        self.model.dataChanged.emit()
        self._save_dids_to_file()

    def _on_header_section_clicked(self, logical_index: int) -> None:
        """处理表头点击事件以进行排序。"""
        header = self.view.table.horizontalHeader()

        # Determine sort order: Ascending -> Descending -> Cancel (None)
        if self._sort_col == logical_index:
            if self._sort_order == Qt.AscendingOrder:
                self._sort_order = Qt.DescendingOrder
            else:
                # Was Descending, now Cancel
                self._sort_col = -1

                # Turn off sorting
                header.setSortIndicatorShown(False)
                if hasattr(header, "setCustomSort"):
                    header.setCustomSort(-1, Qt.AscendingOrder)

                # Optionally re-sort to original order or just leave as is?
                # Usually cancel means stop sorting updates, or revert to default.
                # Leaving as is (last sorted state) is one interpretation,
                # but "Cancel" usually implies restoring original if possible or just unsorted state.
                # Here we just stop showing the indicator.
                return
        else:
            self._sort_col = logical_index
            self._sort_order = Qt.AscendingOrder

        # 使用自定义清晰的排序指示器，禁用默认的
        header.setSortIndicatorShown(False)
        if hasattr(header, "setCustomSort"):
            header.setCustomSort(self._sort_col, self._sort_order)
        else:
            # Fallback if view not updated
            header.setSortIndicator(self._sort_col, self._sort_order)
            header.setSortIndicatorShown(True)

        self._sort_did_rows()

    def _sort_did_rows(self):
        col = self._sort_col
        order = self._sort_order
        reverse = (order == Qt.DescendingOrder)

        # 0: selected, 1: description, 2: did, 3: data_format, 4: follow_dpt, 5: session, 6: security, 7: value
        key_func = None
        if col == 0:
            key_func = lambda r: bool(r.selected)
        elif col == 1:
            key_func = lambda r: (r.description or "").lower()
        elif col == 2:
            def sort_did(r):
                val = r.did
                if not val:
                    # Empty values come after valid numbers (group 1 vs group 0)
                    return (1, "")
                try:
                    # 去把空格，尝试转int
                    d = val.strip().replace(" ", "")
                    # 如果是 0x 开头，或是纯 hex
                    return (0, int(d, 16))
                except:
                    # Non-numeric strings come after valid numbers
                    return (1, val)
            key_func = sort_did
        elif col == 3:
            key_func = lambda r: (r.data_format or "")
        elif col == 4:
            key_func = lambda r: bool(r.follow_dpt)
        elif col == 5:
            key_func = lambda r: (r.diagnostic_session or "")
        elif col == 6:
            key_func = lambda r: (r.security_access or "")
        elif col == 7:
            key_func = lambda r: (r.value or "")

        if key_func:
            try:
                self.model.did_rows.sort(key=key_func, reverse=reverse)
            except Exception as e:
                print(f"Sort failed: {e}")

            # 排序一定要触发重建
            self.model.dataChanged.emit()
            # 由于 on_model_changed 现在会检测对象顺序变化，所以这里 emit 信号后会自动 rebuild
            self._save_dids_to_file()

    def _on_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        """表格单元格内容改变时将变更同步回模型（处理复选、文本与下拉列）。"""
        # 设置标志位，告诉 on_model_changed 不要处理这次变更引起的信号
        self._is_handling_view_update = True
        try:
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
                checked = item.checkState() == Qt.Checked
                self.model.update_row(row, follow_dpt=checked)
            elif col == 5:
                self.model.update_row(row, diagnostic_session=text)
            elif col == 6:
                self.model.update_row(row, security_access=text)
            elif col == 7:
                # Value 列直接使��表格项文本同步到模型
                self.model.update_row(row, value=text)

            self._save_dids_to_file()
        finally:
            self._is_handling_view_update = False

    def _flush_value_cell(self, row: int) -> None:
        # 将表格中 Value 单元格的文本刷新到模型（兼容旧逻辑）
        table_item = self.view.table.item(row, 7)
        if table_item is None:
            return
        value = table_item.text()
        self.model.update_row(row, value=value)

    def _on_value_detail_requested(self, row: int) -> None:
        if row < 0 or row >= len(self.model.did_rows):
            return

        payload, error = self._get_row_bytes(row)

        # Check if we have DPT definition
        did_str = self.model.did_rows[row].did
        did_clean = did_str.strip().replace(" ", "").upper()
        if did_clean.startswith("0X"):
             did_clean = did_clean[2:]

        has_parser = False
        if self._dpt_service.is_ready():
             has_parser = bool(self._dpt_service.get_parser(did_clean))

        # If we have payload, or if we have parser (even without payload), we proceed.
        # If we have neither, we show error.
        if not payload and not has_parser:
            if error:
                MessageToast(self.view).show_toast(error, 1)
            else:
                MessageToast(self.view).show_toast("当前行无可解析数据且无 DPT 定义", 2)
            return

        if not self._dpt_service.is_ready():
            MessageToast(self.view).show_toast("DPT 服务未就绪，请在设置中配置 DPT 文件", 2)
            return

        self._show_value_detail_dialog(row, payload)


    def _show_value_detail_dialog(self, row: int, payload: bytes):
        # 获取当前行的 DID
        did_str = self.model.did_rows[row].did

        did_clean = did_str.strip().replace(" ", "").upper()
        if did_clean.startswith("0X"):
             did_clean = did_clean[2:]

        result = self._dpt_service.parse_bytes(payload, did=did_clean)
        if not result:
            MessageToast(self.view).show_toast("解析失败或无结果", 2)
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
        item = table.item(row, 7)
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

        # Default to HEX as it is the most common format for DIDs
        fmt = (info.data_format or "HEX").upper()

        # Heuristic: If format implies STR but text looks like pure HEX, treat as HEX
        # This fixes issues where "STR" is default but user pasted HEX
        metrics_text = text.replace(" ", "").replace("-", "")
        if fmt == "STR" and len(metrics_text) > 0 and all(c in "0123456789ABCDEFabcdef" for c in metrics_text):
             # Only if length is even (or we can pad), usually hex is pairs.
             # But let's just assume HEX if it looks like HEX to avoid utf-8 encoding hex strings.
             if len(metrics_text) % 2 == 0:
                 fmt = "HEX"

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

