import json
import os
import time
from PyQt5 import QtWidgets, QtCore

from app.core.base_controller import BaseController
from app.core.dependency_injection import di_container
from app.modules.uds_sequence.model.uds_sequence_model import UDSSequenceModel
from app.modules.uds_sequence.view.uds_sequence_view import UDSSequenceView, NAME_CN, ExportConfigDialog
from app.services.device_manage.device_service import DeviceService
from app.services.configuration.config_service import AppConfigurationService
from app.common.utils.security_access_helper import SecurityAccessHelper


class SequenceWorker(QtCore.QThread):
    log_signal = QtCore.pyqtSignal(str)
    update_row_signal = QtCore.pyqtSignal(int, str)
    update_request_signal = QtCore.pyqtSignal(int, str)
    finished_signal = QtCore.pyqtSignal()
    current_row_signal = QtCore.pyqtSignal(int)

    def __init__(self, device_service, data, times, stop_on_fail, config_service=None):
        super().__init__()
        self.device_service = device_service
        self.data = data
        self.times = times
        self.stop_on_fail = stop_on_fail
        self.config_service = config_service
        self.is_running = True
        self.seed_map = {}

    def run(self):
        # 升级屏障拦截：升级期间禁止执行序列
        if self.device_service.is_upgrade_active():
            self.log_signal.emit(DeviceService.UPGRADE_BLOCKED_MSG)
            self.finished_signal.emit()
            return
        try:
            for i in range(self.times):
                if not self.is_running:
                    break
                self.log_signal.emit(f"--- 第 {i+1}/{self.times} 次循环 ---")
                for row_index, item in enumerate(self.data):
                    if not self.is_running:
                        break

                    # Notify view to highlight current row
                    self.current_row_signal.emit(row_index)

                    if not item.get("checked", True):
                        continue

                    name = item.get("name", "")
                    request = item.get("request", "")

                    # Check if it is a delay
                    if name == '⏱' or item.get("response") == '延迟(ms)':
                        try:
                            delay_ms = int(request)
                            self.log_signal.emit(f"等待 {delay_ms} ms...")
                            time.sleep(delay_ms / 1000.0)
                        except ValueError:
                            self.log_signal.emit(f"无效的延迟时间: {request}")
                    else:
                        # Handle Security Access (Service 27) Key Calculation
                        try:
                            req_bytes = bytes.fromhex(request.replace(' ', ''))
                            if len(req_bytes) >= 2 and req_bytes[0] == 0x27:
                                sub_func = req_bytes[1]
                                # Even sub-function means Send Key
                                if sub_func % 2 == 0:
                                    seed_level = sub_func - 1
                                    if seed_level in self.seed_map:
                                        seed = self.seed_map[seed_level]
                                        dll_path = self._get_dll_path()

                                        key, err = SecurityAccessHelper.calculate_key(seed_level, seed, dll_path)
                                        if key:
                                            # Construct new request: 27 <sub_func> <key>
                                            new_req = bytearray([0x27, sub_func]) + key
                                            request = new_req.hex(' ').upper()

                                            # Update UI with calculated key
                                            self.update_request_signal.emit(row_index, request)
                                            self.log_signal.emit(f"计算Key成功 (Level {seed_level}): {key.hex(' ').upper()}")

                                            # Remove used seed
                                            del self.seed_map[seed_level]
                                        else:
                                            self.log_signal.emit(f"计算Key失败: {err}")
                        except Exception as e:
                            self.log_signal.emit(f"预处理请求异常: {str(e)}")

                        # Send command
                        self.log_signal.emit(f"TX: {request}")

                        resp = self._send_uds_command(request)
                        self.log_signal.emit(f"RX: {resp}")

                        # Handle Security Access (Service 27) Seed Recording
                        if not resp.startswith("Error") and not resp.startswith("No Response"):
                            try:
                                resp_bytes = bytes.fromhex(resp)
                                # Positive response for 27 is 67
                                if len(resp_bytes) >= 2 and resp_bytes[0] == 0x67:
                                    sub_func = resp_bytes[1]
                                    # Odd sub-function means Request Seed response
                                    if sub_func % 2 != 0:
                                        seed = resp_bytes[2:]
                                        self.seed_map[sub_func] = seed
                                        self.log_signal.emit(f"记录Seed (Level {sub_func}): {seed.hex(' ').upper()}")
                            except Exception:
                                pass

                        # Update table response
                        self.update_row_signal.emit(row_index, resp)

                        # Check for failure if stop_on_fail is enabled
                        if self.stop_on_fail:
                            is_fail = False
                            if "Error" in resp or "No Response" in resp:
                                is_fail = True
                            elif resp.startswith("7F"):
                                is_fail = True

                            if is_fail:
                                self.log_signal.emit(f"执行失败，停止序列 (响应: {resp})")
                                return # Stop execution
        except Exception as e:
            self.log_signal.emit(f"执行异常: {str(e)}")
        finally:
            self.seed_map.clear()
            self.finished_signal.emit()

    def stop(self):
        self.is_running = False

    def _get_dll_path(self):
        if self.config_service:
            return self.config_service._settings.get("diag_layer", {}).get("dll_path", "")
        return None  # Default fallback to None

    def _send_uds_command(self, request_str: str, timeout: float = None) -> str:

        # Clean request string
        req_hex = request_str.replace(' ', '')
        try:
            # Convert hex string to bytes
            payload = bytes.fromhex(req_hex)

            # Use DeviceService to send payload (it handles timeout from config)
            resp = self.device_service.send_doip_payload(payload, timeout=timeout)


            if resp is None:
                return "No Response"

            return resp.hex(' ').upper()
        except Exception as e:
            return f"Error: {str(e)}"

class BatchSendWorker(QtCore.QThread):
    log_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal()

    def __init__(self, device_service, request_str, times):
        super().__init__()
        self.device_service = device_service
        self.request_str = request_str
        self.times = times
        self.is_running = True

    def run(self):
        # 升级屏障拦截：升级期间禁止执行批量发送
        if self.device_service.is_upgrade_active():
            self.log_signal.emit(DeviceService.UPGRADE_BLOCKED_MSG)
            self.finished_signal.emit()
            return
        try:
            for i in range(self.times):
                if not self.is_running:
                    break

                self.log_signal.emit(f"TX: {self.request_str}")

                req_hex = self.request_str.replace(' ', '')
                try:
                    payload = bytes.fromhex(req_hex)
                    resp = self.device_service.send_doip_payload(payload) # timeout default

                    resp_str = "No Response"
                    if resp is not None:
                        resp_str = resp.hex(' ').upper()

                    self.log_signal.emit(f"RX: {resp_str}")
                except Exception as e:
                    self.log_signal.emit(f"Error: {str(e)}")

        except Exception as e:
            self.log_signal.emit(f"Batch execution exception: {str(e)}")
        finally:
            self.finished_signal.emit()

    def stop(self):
        self.is_running = False

class UDSSequenceController(BaseController):

    def __init__(self, parent=None):
        self.model = UDSSequenceModel(parent)
        self.view = UDSSequenceView(self.model, parent)
        super().__init__(self.model, self.view, parent)

        self._config_service = di_container.resolve(AppConfigurationService)
        if not self._config_service:
             self._config_service = AppConfigurationService()
             di_container.register_singleton(AppConfigurationService, self._config_service)

        self._device_service = di_container.resolve(DeviceService)
        if not self._device_service:
             self._device_service = DeviceService()
             di_container.register_singleton(DeviceService, self._device_service)

        self.current_config_name = None
        self.worker = None
        self.batch_worker = None
        self._single_send_active = False  # 单次发送是否正在执行
        self.is_loading = False
        self._connect_signals()

    def _connect_signals(self):
        self.view.send_requested.connect(self._on_send_requested)
        self.view.send_single_requested.connect(self._on_send_requested)
        self.view.insert_requested.connect(self._on_insert_requested)
        self.view.table_operation_requested.connect(self._on_table_operation)
        self.view.delay_insert_requested.connect(self._on_delay_insert_requested)
        self.view.send_batch_requested.connect(self._on_send_batch_requested)
        self.view.run_sequence_requested.connect(self._on_run_sequence_requested)
        self.view.config_save_requested.connect(self._on_config_save_requested)
        self.view.config_load_requested.connect(self._on_config_load_requested)
        self.view.config_delete_requested.connect(self._on_config_delete_requested)
        self.view.config_import_requested.connect(self._on_config_import_requested)
        self.view.config_export_requested.connect(self._on_config_export_requested)
        self.view.add_command_requested.connect(self._on_add_command_requested)
        self.view.insert_command_requested.connect(self._on_insert_command_requested)
        # view now emits string code like '10' or '10.01'
        self.view.command_selected.connect(self._on_command_selected)
        self.view.table_data_changed.connect(self._on_table_data_changed)

        # Search bindings
        self.view.search_btn.clicked.connect(self._on_search_clicked)
        self.view.search_input.returnPressed.connect(self._on_search_clicked)

        # Load initial config names
        self.view.update_config_list(self.model.get_config_names())
        self._on_config_load_requested("默认")

        # Timer for Tester Present（基于 S3 定时器动态计算间隔，符合 ISO 14229-1）
        self.tester_present_timer = QtCore.QTimer(self)
        self.tester_present_timer.timeout.connect(self._send_tester_present)
        self.tester_present_mode = "80"  # Default 3E 80
        self._tp_in_flight = False  # 3E 00 请求是否还在等待响应
        # S3/2 作为 3E 发送间隔（确保在 S3 超时前发送，留 50% 安全余量）
        try:
            s3_ms = int(self._config_service.diag_layer_settings.get("s3_client_time", 3000))
        except (ValueError, TypeError):
            s3_ms = 3000
        self.tester_present_interval_ms = max(500, s3_ms // 2)

        # 连接 3E 控件信号
        self.view.tp_toggled.connect(self._on_tester_present_toggled)
        self.view.tp_mode_changed.connect(self._on_tester_present_mode_changed)

    def _on_table_data_changed(self):
        if self.current_config_name == "默认":
            # auto save when default
            data = self.view.get_table_data()
            self.model.save_config(self.current_config_name, data)

    def _on_search_clicked(self):
        """Handle search button clicked or Enter pressed in UDS module."""
        text = self.view.search_input.text().strip().lower()
        if not text:
            return

        start_row = 0
        current_rows = self.view.data_table.selectionModel().selectedRows()
        if current_rows:
            start_row = current_rows[-1].row() + 1 # Search from next row

        row_count = self.view.data_table.rowCount()
        found_row = -1

        # Search downward
        for i in range(start_row, row_count):
            if self._match_row(i, text):
                found_row = i
                break

        # Wrap around
        if found_row == -1 and start_row > 0:
            for i in range(0, start_row):
                if self._match_row(i, text):
                    found_row = i
                    break

        if found_row != -1:
            self.view.data_table.scrollToItem(self.view.data_table.item(found_row, 0))
            self._highlight_search_row(found_row)
        else:
            from app.common.ui.modern_widgets import MessageToast
            MessageToast(self.view).show_toast("未找到匹配的指令或描述", 1)

    def _match_row(self, row, text):
        """Check if UDS Name (1), Request (2) or Response (4) matches text."""
        for col in [1, 2, 4]:
            item = self.view.data_table.item(row, col)
            if item and text in item.text().lower():
                return True
        return False

    def _highlight_search_row(self, row: int):
        self.view.data_table.clearSelection()
        self.view.data_table.selectRow(row)

        orig_style = self.view.data_table.styleSheet()
        if "#FDE047" not in orig_style:
            self._normal_stylesheet = orig_style

        # Add yellow highlight for selected items to only affect the selected row
        new_style = getattr(self, "_normal_stylesheet", orig_style) + "\nQTableWidget::item:selected { background-color: #FDE047; color: #1F2937; }"
        self.view.data_table.setStyleSheet(new_style)

        if hasattr(self, "_highlight_timer"):
            self._highlight_timer.stop()
        else:
            from PyQt5 import QtCore
            self._highlight_timer = QtCore.QTimer()
            self._highlight_timer.setSingleShot(True)
            self._highlight_timer.timeout.connect(self._restore_highlight)

        self._highlight_timer.start(1200)

    def _restore_highlight(self):
        if hasattr(self, "_normal_stylesheet"):
            self.view.data_table.setStyleSheet(self._normal_stylesheet)

    def _on_add_command_requested(self, code: str):
        node, _ = self.model.find_node_by_code(code)
        if node is not None:
            name = node.get('name', '')
            cn = NAME_CN.get(name)
            display_name = f"{code} {name} ({cn})" if cn else f"{code} {name}"
            request = ' '.join(code.split('.'))

            # Append to table
            self.view.append_table_row(display_name, request, "")
            self.view.log_message(f"添加到末尾: {code} {display_name}")

        else:
            # Don't clear the table on invalid selection — just disable editor inputs.
            self.view.set_editor_enabled(False)

    def _on_insert_command_requested(self, code: str):
        node, _ = self.model.find_node_by_code(code)
        if node:
            name = node.get('name', '')
            cn = NAME_CN.get(name)
            display_name = f"{code} {name} ({cn})" if cn else f"{code} {name}"
            request = ' '.join(code.split('.'))

            # Insert at current row or append if no selection
            current_row = self.view.get_current_row()
            if current_row < 0:
                self.view.append_table_row(display_name, request, "")
                self.view.log_message(f"添加到末尾: {code} {display_name}")
                return

            self.view.insert_table_row(current_row, display_name, request, "")
            self.view.log_message(f"插入指令: {code} {display_name}")

    def _do_send_tester_present(self, cmd, timeout):
        """发送 TesterPresent 报文并记录 TX/RX 到日志。"""
        self.view.log_message(f"TX: {cmd}")
        resp = self._send_uds_command(cmd, timeout=timeout)
        is_suppress = "80" in cmd

        if is_suppress:
            # 3E 80 抑制正响应模式：只打印实际响应或异常，不打印 No Response
            if resp and resp != "No Response" and resp.startswith("Error"):
                self.view.log_message(f"RX: {resp}")
        else:
            # 3E 00 正常响应模式：仅当收到实际响应（7E 00）时打印，超时不打印
            if resp and resp != "No Response":
                self.view.log_message(f"RX: {resp}")

        # 3E 00 模式：响应收到（或超时）后清除 in-flight 标志，
        # 允许定时器触发下一轮发送，实现"从响应时间算起"的间隔
        if not is_suppress:
            self._tp_in_flight = False

    def _on_tester_present_mode_changed(self, mode: str):
        """3E 模式下拉框切换：更新心跳报文模式。

        :param mode: "00" 或 "80"
        """
        self.tester_present_mode = mode
        self._tp_in_flight = False  # 切换模式时重置 in-flight 标志
        desc = "抑制正响应 (3E 80)" if mode == "80" else "正常响应 (3E 00)"
        self.view.log_message(f"TesterPresent 模式已切换: {desc}")

    def _on_tester_present_toggled(self, checked: bool):
        """3E 心跳按钮切换：启用/停止 TesterPresent 定时器。

        符合 ISO 14229-1：以 S3/2 为间隔发送 TesterPresent，确保在
        S3 Client Timer 超时前刷新 ECU 会话，防止会话回退到默认会话。
        """
        if checked:
            # 升级屏障拦截：升级期间禁止启动 3E 心跳
            if self._device_service.is_upgrade_active():
                from app.common.ui.modern_widgets import MessageToast
                MessageToast(self.view).show_toast(DeviceService.UPGRADE_BLOCKED_MSG, 1)
                self.view.log_message(DeviceService.UPGRADE_BLOCKED_MSG)
                # 恢复按钮状态为未按下，避免 UI 状态不一致
                self.view.btn_3e.blockSignals(True)
                self.view.btn_3e.setChecked(False)
                self.view.btn_3e.blockSignals(False)
                return
            # 动态重新读取 S3 值（用户可能在运行期间修改了配置）
            try:
                s3_ms = int(self._config_service.diag_layer_settings.get("s3_client_time", 3000))
            except (ValueError, TypeError):
                s3_ms = 3000
            self.tester_present_interval_ms = max(500, s3_ms // 2)
            self._tp_in_flight = False  # 启动时重置 in-flight 标志
            self.tester_present_timer.start(self.tester_present_interval_ms)
            self.view.log_message(
                f"TesterPresent(3E) 心跳已启动 [间隔={self.tester_present_interval_ms}ms, S3/2]"
            )
        else:
            self.tester_present_timer.stop()
            self.view.log_message("TesterPresent(3E) 心跳已停止")

    def _send_tester_present(self):
        """发送 TesterPresent (3E) 心跳，保持 ECU 会话不超时。"""
        # 连接检查：未连接时静默跳过
        client = self._device_service.get_doip_client()
        if not client or not client.is_connected():
            return

        # 升级期间静默跳过心跳，不打印日志避免刷屏
        if self._device_service.is_upgrade_active():
            return

        # 序列/批量/单次发送任务执行期间静默跳过，不影响任何正在执行的诊断操作
        if self.worker is not None or self.batch_worker is not None or self._single_send_active:
            return

        # 3E 00 模式：上一轮请求还没收到响应，跳过本轮，等响应回来后再发下一轮
        if self._tp_in_flight:
            return

        cmd = f"3E {self.tester_present_mode}"

        # 3E 00：标记 in-flight，响应回来后清除，定时器下一轮才能发送
        if self.tester_present_mode == "00":
            self._tp_in_flight = True

        # 抑制正响应 (3E 80) 时用短超时，普通请求 (3E 00) 用默认超时
        timeout = 0.05 if self.tester_present_mode == "80" else None

        import threading
        threading.Thread(
            target=self._do_send_tester_present, args=(cmd, timeout), daemon=True
        ).start()

    def _on_run_sequence_requested(self, times: int):
        """Execute the checked instructions in the table sequentially."""
        data = self.view.get_table_data()
        if not data:
            self.view.log_message("序列为空，无法执行")
            return

        if not self._device_service.get_doip_client() or not self._device_service.get_doip_client().is_connected():
            from app.common.ui.modern_widgets import MessageToast
            MessageToast(self.view).show_toast("请先连接设备 (DoIP)", 1)
            self.view.log_message("Error: 未连接 DoIP 客户端")
            return

        # 升级屏障拦截
        if self._device_service.is_upgrade_active():
            from app.common.ui.modern_widgets import MessageToast
            MessageToast(self.view).show_toast(DeviceService.UPGRADE_BLOCKED_MSG, 1)
            self.view.log_message(DeviceService.UPGRADE_BLOCKED_MSG)
            return

        # Start execution thread
        self.worker = SequenceWorker(self._device_service, data, times, True, self._config_service)
        self.worker.log_signal.connect(self.view.log_message)
        self.worker.update_row_signal.connect(self.view.update_row_response)
        self.worker.update_request_signal.connect(self.view.update_row_request)
        self.worker.finished_signal.connect(self._on_sequence_finished)
        self.worker.current_row_signal.connect(self.view.highlight_row)
        self.worker.start()

    def _on_sequence_finished(self):
        self.view.set_editor_enabled(True)
        self.view.run_sequence_btn.setEnabled(True)
        self.view.log_message("序列执行结束")
        self.worker = None

    def _on_send_requested(self, request_data: str):
        if not self._device_service.get_doip_client() or not self._device_service.get_doip_client().is_connected():
            from app.common.ui.modern_widgets import MessageToast
            MessageToast(self.view).show_toast("请先连接设备 (DoIP)", 1)
            self.view.log_message("Error: 未连接 DoIP 客户端")
            return

        # 升级屏障拦截
        if self._device_service.is_upgrade_active():
            from app.common.ui.modern_widgets import MessageToast
            MessageToast(self.view).show_toast(DeviceService.UPGRADE_BLOCKED_MSG, 1)
            self.view.log_message(DeviceService.UPGRADE_BLOCKED_MSG)
            return

        if request_data:
            self.model.log += f"TX: {request_data}\n"
            self.view.log_message(f"TX: {request_data}")

            self.view.set_editor_enabled(False)
            self.view.run_sequence_btn.setEnabled(False)
            QtWidgets.QApplication.processEvents()

            # 标记单次发送进行中，屏蔽 3E 心跳
            self._single_send_active = True

            # Execute send in background thread
            import threading
            def bg_send():
                try:
                    resp = self._send_uds_command(request_data)
                    # Safely update UI
                    QtCore.QMetaObject.invokeMethod(self, "_on_single_send_finished",
                                                    QtCore.Qt.QueuedConnection,
                                                    QtCore.Q_ARG(str, resp))
                except Exception as e:
                    QtCore.QMetaObject.invokeMethod(self, "_on_single_send_finished",
                                                    QtCore.Qt.QueuedConnection,
                                                    QtCore.Q_ARG(str, f"Error: {str(e)}"))

            threading.Thread(target=bg_send, daemon=True).start()
        else:
            self.view.log_message("请求数据为空，无法发送")

    @QtCore.pyqtSlot(str)
    def _on_single_send_finished(self, resp: str):
        self._single_send_active = False  # 清除单次发送标志，恢复 3E 心跳
        self.view.log_message(f"RX: {resp}")
        try:
            self.view.response_edit.setPlainText(resp)
        except Exception:
            pass
        self.view.set_editor_enabled(True)
        self.view.run_sequence_btn.setEnabled(True)

    def _on_insert_requested(self, response_data: str):
        if response_data:
            self.view.append_table_row("response_data", response_data, "手动插入的响应")
            self.view.log_message(f"插入响应数据到表格: {response_data}")
        else:
            self.view.log_message("响应数据为空，无法插入")

    def _on_table_operation(self, operation: str):
        current_row = self.view.get_current_row()

        if operation == "添加":
            self.view.append_table_row("诊断服务", "", "请输入描述")
        elif operation == "删除":
            self.view.delete_selected_rows()
        elif operation == "上移":
            if current_row > 0:
                self.view.swap_table_rows(current_row, current_row - 1)
                self.view.data_table.setCurrentCell(current_row - 1, 0)
        elif operation == "下移":
            if 0 <= current_row < self.view.data_table.rowCount() - 1:
                self.view.swap_table_rows(current_row, current_row + 1)
                self.view.data_table.setCurrentCell(current_row + 1, 0)

    def _on_delay_insert_requested(self, delay_text: str):
        """Handle delay insertion: insert a row whose name shows a clock icon and value is the delay text."""
        # normalize the delay text; default to '0' if empty
        d = delay_text.strip() or '0'
        name = '⏱'  # show only the clock icon in the name column
        self.view.append_table_row(name, d, '延迟(ms)')
        # clear the input field for convenience if available
        try:
            self.view.delay_input.clear()
        except Exception:
            pass
        self.view.log_message(f"插入延迟: {d} ms")

    def _on_send_batch_requested(self, times: int):
        """Send the current Request multiple times using BatchSendWorker."""
        if not self._device_service.get_doip_client() or not self._device_service.get_doip_client().is_connected():
            from app.common.ui.modern_widgets import MessageToast
            MessageToast(self.view).show_toast("请先连接设备 (DoIP)", 1)
            self.view.log_message("Error: 未连接 DoIP 客户端")
            return

        # 升级屏障拦截
        if self._device_service.is_upgrade_active():
            from app.common.ui.modern_widgets import MessageToast
            MessageToast(self.view).show_toast(DeviceService.UPGRADE_BLOCKED_MSG, 1)
            self.view.log_message(DeviceService.UPGRADE_BLOCKED_MSG)
            return

        req = self.view.get_request_text()
        if not req:
            self.view.log_message("请求数据为空，无法列表发送")
            return

        self.view.log_message(f"开始 列表发送 x{times}: {req}")

        self.view.set_editor_enabled(False)
        self.view.run_sequence_btn.setEnabled(False)
        QtWidgets.QApplication.processEvents()

        self.batch_worker = BatchSendWorker(self._device_service, req, times)
        self.batch_worker.log_signal.connect(self.view.log_message)
        self.batch_worker.finished_signal.connect(self._on_batch_send_finished)
        self.batch_worker.start()

    def _on_batch_send_finished(self):
        self.view.set_editor_enabled(True)
        self.view.run_sequence_btn.setEnabled(True)
        self.view.log_message("完成 列表发送")
        self.batch_worker = None

    def _on_command_selected(self, code: str):
        # code is like '10' or '10.01'
        node, path = self.model.find_node_by_code(code)
        if node is not None:
            # enable editor and set placeholders using human readable name
            display = f"{code} {node.get('name')}" if node.get('name') else code
            self.view.set_editor_enabled(True)
            self.view.set_placeholders(display)

            # Fill the request field automatically: '10' -> '10', '10.01' -> '10 01'
            request_text = ' '.join(code.split('.'))
            try:
                # QTextEdit: setPlainText to place the code into the editor
                self.view.request_edit.setPlainText(request_text)
            except Exception:
                # fallback: if view doesn't expose request_edit, use placeholder only
                pass

            # IMPORTANT: do NOT change/clear the right-hand table when clicking the tree.
            # The table should remain under user control; only update editor placeholders and request text.
        else:
            # Don't clear the table on invalid selection — just disable editor inputs.
            self.view.set_editor_enabled(False)

    def _send_uds_command(self, request_str: str, timeout: float = None) -> str:
        if not self._device_service.get_doip_client():
            return "Error: No Client"

        # Clean request string
        req_hex = request_str.replace(' ', '')
        try:
            # Convert hex string to bytes
            payload = bytes.fromhex(req_hex)

            # Use DeviceService to send payload (it handles timeout from config)
            resp = self._device_service.send_doip_payload(payload, timeout=timeout)


            if resp is None:
                return "No Response"

            return resp.hex(' ').upper()
        except Exception as e:
            return f"Error: {str(e)}"

    def _on_config_save_requested(self, config_name: str):
        """Handle saving the current configuration."""
        if config_name:
            # Check for duplicates/overwrite
            existing_names = self.model.get_config_names()
            current_view_config = self.view.config_combo.currentText()

            if config_name in existing_names and config_name != current_view_config:
                # Overwriting a DIFFERENT config
                reply = QtWidgets.QMessageBox.question(
                    self.view,
                    "覆盖确认",
                    f"配置 '{config_name}' 已存在，是否覆盖？",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                )
                if reply != QtWidgets.QMessageBox.Yes:
                    return

            # Auto-save '默认' if we are currently in it and saving to another name
            if self.current_config_name == "默认" and config_name != "默认":
                self.model.save_config("默认", self.view.get_table_data())

            data = self.view.get_table_data()
            self.model.save_config(config_name, data)
            self.view.update_config_list(self.model.get_config_names(), current=config_name)
            self.view.log_message(f"配置 '{config_name}' 保存成功")
            self.current_config_name = config_name

    def _on_config_load_requested(self, config_name: str):
        """Handle loading a selected configuration."""
        if config_name:
            self.is_loading = True
            try:
                # Auto-save '默认' if switching away from it
                if self.current_config_name == "默认" and self.current_config_name != config_name:
                    data = self.view.get_table_data()
                    self.model.save_config("默认", data)

                data = self.model.load_config(config_name)
                self.view.set_table_data(data)
                self.view.log_message(f"配置 '{config_name}' 加载成功")
                self.current_config_name = config_name
            finally:
                self.is_loading = False

    def _on_config_delete_requested(self, config_name: str):
        """Handle deleting a selected configuration."""
        if config_name:
            self.model.delete_config(config_name)
            self.view.update_config_list(self.model.get_config_names())
            self.view.log_message(f"配置 '{config_name}' 删除成功")

            # Reset current config name so we don't try to save the deleted one
            if self.current_config_name == config_name:
                self.current_config_name = None

            self._on_config_load_requested("默认")

    def _on_config_import_requested(self):
        """Handle importing configuration(s) from file(s)."""
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self.view, "导入配置", "", "JSON Files (*.json)")
        if not paths:
            return

        success_count = 0
        existing_names = self.model.get_config_names()

        for path in paths:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if not isinstance(data, list):
                    self.view.log_message(f"导入失败 ({os.path.basename(path)}): 文件格式错误 (应为列表)")
                    continue

                # Use filename as config name
                filename = os.path.basename(path)
                config_name = os.path.splitext(filename)[0]

                # Auto-rename if duplicate
                base_name = config_name
                counter = 1
                while config_name in existing_names:
                    config_name = f"{base_name} ({counter})"
                    counter += 1

                # Add to existing names list so next iteration knows about it
                existing_names.append(config_name)

                # Auto-save '默认' if we are currently in it (only once)
                if self.current_config_name == "默认" and success_count == 0:
                    self.model.save_config("默认", self.view.get_table_data())

                self.model.save_config(config_name, data)
                success_count += 1
                self.view.log_message(f"配置 '{config_name}' 导入成功")

            except Exception as e:
                self.view.log_message(f"导入失败 ({os.path.basename(path)}): {str(e)}")

        if success_count > 0:
            # Refresh list
            self.view.update_config_list(self.model.get_config_names(), current=self.current_config_name)
            # If we imported something, we might want to switch to it?
            # Usually batch import just adds them. User stays on current.
            if self.current_config_name:
                 self.view.config_combo.setCurrentText(self.current_config_name)


    def _on_config_export_requested(self):
        """Handle exporting configurations."""
        config_names = self.model.get_config_names()
        dialog = ExportConfigDialog(config_names, self.view)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            selected_configs = dialog.selected_configs
            export_path = dialog.export_path

            if not os.path.exists(export_path):
                try:
                    os.makedirs(export_path)
                except Exception as e:
                    self.view.log_message(f"创建导出目录失败: {str(e)}")
                    return

            success_count = 0
            for name in selected_configs:
                try:
                    # If it's the current one, save it first to ensure latest changes are exported
                    if name == self.current_config_name:
                        self.model.save_config(name, self.view.get_table_data())

                    data = self.model.load_config(name)
                    file_path = os.path.join(export_path, f"{name}.json")

                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)

                    success_count += 1
                except Exception as e:
                    self.view.log_message(f"导出 '{name}' 失败: {str(e)}")

            self.view.log_message(f"成功导出 {success_count} 个配置到 {export_path}")


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    m = UDSSequenceModel()
    v = UDSSequenceView(m)
    v.show()
    sys.exit(app.exec_())
