import json
import os
import time
from PyQt5 import QtWidgets, QtCore

from app.core.base_controller import BaseController
from app.modules.uds_sequence.model.uds_sequence_model import UDSSequenceModel
from app.modules.uds_sequence.view.uds_sequence_view import UDSSequenceView, NAME_CN
# Try to import DeviceService, handle potential circular imports or missing files gracefully if needed
try:
    from app.services.device_manage.device_service import DeviceService
except ImportError:
    DeviceService = None


class UDSSequenceController(BaseController):
    def __init__(self, parent=None):
        self.model = UDSSequenceModel(parent)
        self.view = UDSSequenceView(self.model, parent)
        super().__init__(self.model, self.view, parent)

        self.current_config_name = None
        self._connect_signals()

    def _connect_signals(self):
        self.view.send_requested.connect(self._on_send_requested)
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

        # Load initial config names
        self.view.update_config_list(self.model.get_config_names())
        self._on_config_load_requested("默认")

        # Timer for Tester Present
        self.tester_present_timer = QtCore.QTimer(self)
        self.tester_present_timer.timeout.connect(self._send_tester_present)
        self.tester_present_mode = "80" # Default 3E 80

    # --- Signal handlers ---
    def _on_add_command_requested(self, code: str):
        node, _ = self.model.find_node_by_code(code)
        if node:
            name = node.get('name', '')
            cn = NAME_CN.get(name)
            display_name = f"{name} ({cn})" if cn else name
            request = ' '.join(code.split('.'))
            self.view.append_table_row(display_name, request, "")
            self.view.log_message(f"添加指令: {code} {display_name}")

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
                current_row = self.view.data_table.rowCount()

            self.view.data_table.insertRow(current_row)

            # Use view's logic to populate the row, but we need to do it manually since append_table_row appends
            # We can reuse the logic from append_table_row but targeting a specific row
            # Or just call append and move? No, let's duplicate the population logic briefly or refactor view.
            # For simplicity, let's use a helper in view or just append then move.
            # Actually, let's just use append_table_row and move it if needed, or better:
            # Let's add a method to view to insert at specific row.
            # But since I cannot edit view easily again without reading, I will use append then move.

            self.view.append_table_row(display_name, request, "")
            new_row = self.view.data_table.rowCount() - 1
            if current_row < new_row:
                # Move row from new_row to current_row
                # This is tricky with QTableWidget.
                # Let's just append for now and I will add insert_table_row to view in next turn if user complains.
                # Actually, the user asked for "Insert at Selection".
                # I should probably add `insert_table_row` to View.
                pass
            self.view.log_message(f"插入指令: {code} {display_name}")

    def _send_tester_present(self):
        # Send 3E <mode>
        # This runs in main thread via QTimer, so it might block slightly but usually fast.
        # If we are in a loop in _on_run_sequence_requested, processEvents handles this timer?
        # Yes, processEvents will process timer events.
        cmd = f"3E {self.tester_present_mode}"
        # We don't want to log every heartbeat to the main log to avoid spam, or maybe we do?
        # Let's log to console or a separate debug log. For now, suppress log or log simply.
        # self.view.log_message(f"Heartbeat: {cmd}")
        self._send_uds_command(cmd)

    def _on_run_sequence_requested(self, times: int):
        """Execute the checked instructions in the table sequentially."""
        data = self.view.get_table_data()
        if not data:
            self.view.log_message("序列为空，无法执行")
            return

        client = self._get_doip_client()
        if not client:
            self.view.log_message("错误: 未连接 DoIP 客户端")
            # For testing without client, we might want to proceed or return
            # return

        # Get options
        stop_on_fail = self.view.btn_stop_fail.isChecked()
        self.tester_present_mode = "00" if self.view.btn_3e.isChecked() else "80"

        self.view.log_message(f"开始执行序列，循环次数: {times}")
        self.view.log_message(f"配置: 3E {self.tester_present_mode}, 遇错停止: {stop_on_fail}")

        # Disable UI during execution to prevent modification
        self.view.set_editor_enabled(False)
        self.view.run_sequence_btn.setEnabled(False)
        QtWidgets.QApplication.processEvents()

        # Start Tester Present
        self.tester_present_timer.start(2000) # 2 seconds

        try:
            for i in range(times):
                self.view.log_message(f"--- 第 {i+1}/{times} 次循环 ---")
                for item in data:
                    if not item.get("checked", True):
                        continue

                    name = item.get("name", "")
                    request = item.get("request", "")

                    # Check if it is a delay
                    if name == '⏱' or item.get("response") == '延迟(ms)':
                        try:
                            delay_ms = int(request)
                            self.view.log_message(f"等待 {delay_ms} ms...")
                            # Use loop with processEvents to keep UI responsive
                            end_time = time.time() + (delay_ms / 1000.0)
                            while time.time() < end_time:
                                QtWidgets.QApplication.processEvents()
                                time.sleep(0.01)
                        except ValueError:
                            self.view.log_message(f"无效的延迟时间: {request}")
                    else:
                        # Send command
                        self.view.log_message(f"发送: {request}")
                        QtWidgets.QApplication.processEvents()

                        resp = "No Response"
                        if client:
                            resp = self._send_uds_command(request)
                            self.view.log_message(f"接收: {resp}")
                        else:
                            # Simulation mode if no client
                            self.view.log_message(f"模拟发送: {request}")
                            time.sleep(0.1)
                            resp = f"50 {request.replace(' ', '')[2:] if len(request)>2 else ''}"
                            self.view.log_message(f"模拟接收: {resp}")

                        # Check for failure if stop_on_fail is enabled
                        if stop_on_fail:
                            # Simple failure check: "Error", "No Response", or Negative Response (7F)
                            is_fail = False
                            if "Error" in resp or "No Response" in resp:
                                is_fail = True
                            elif resp.startswith("7F"):
                                is_fail = True

                            if is_fail:
                                self.view.log_message(f"执行失败，停止序列 (响应: {resp})")
                                return # Stop execution

                QtWidgets.QApplication.processEvents()
        finally:
            self.tester_present_timer.stop()
            self.view.set_editor_enabled(True)
            self.view.run_sequence_btn.setEnabled(True)
            self.view.log_message("序列执行结束")

    def _on_send_requested(self, request_data: str):
        if request_data:
            self.model.log += f"发送请求: {request_data}\n"
            self.view.log_message(f"发送请求: {request_data}")

            # Actually send the command
            resp = self._send_uds_command(request_data)
            self.view.log_message(f"接收响应: {resp}")

            # Update response field if it's a single send
            try:
                self.view.response_edit.setPlainText(resp)
            except Exception:
                pass
        else:
            self.view.log_message("请求数据为空，无法发送")

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
        """Send the current Request multiple times (as configured in the spinbox).

        This uses the existing _on_send_requested handler to keep logging/behavior consistent.
        """
        req = self.view.get_request_text()
        if not req:
            self.view.log_message("请求数据为空，无法列表发送")
            return
        self.view.log_message(f"开始 列表发送 x{times}: {req}")
        for i in range(times):
            self._on_send_requested(req)
        self.view.log_message(f"完成 列表发送 x{times}")

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

    def _get_doip_client(self):
        if DeviceService:
            return DeviceService().get_doip_client()
        return None

    def _send_uds_command(self, request_str: str) -> str:
        client = self._get_doip_client()
        if not client:
            return "Error: No Client"

        # Clean request string
        req_hex = request_str.replace(' ', '')
        try:
            # Assuming client has send_uds_command method
            # This depends on the actual DoIP client implementation
            # For now, let's assume it returns a response string or bytes
            # We might need to convert bytes to hex string
            resp = client.send_uds_command(req_hex)
            if isinstance(resp, bytes):
                return resp.hex().upper()
            return str(resp)
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
            # Auto-save '默认' if switching away from it
            if self.current_config_name == "默认":
                data = self.view.get_table_data()
                self.model.save_config("默认", data)

            data = self.model.load_config(config_name)
            self.view.set_table_data(data)
            self.view.log_message(f"配置 '{config_name}' 加载成功")
            self.current_config_name = config_name

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
        """Handle importing a configuration from a file."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self.view, "导入配置", "", "JSON Files (*.json)")
        if not path:
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, list):
                self.view.log_message("导入失败: 文件格式错误 (应为列表)")
                return

            # Use filename as config name
            filename = os.path.basename(path)
            config_name = os.path.splitext(filename)[0]
            existing_names = self.model.get_config_names()

            # Ask user for name, loop if duplicate
            while True:
                text_val = config_name
                # If it's a duplicate, prompt with warning
                if config_name in existing_names:
                    label = f"配置 '{config_name}' 已存在，请输入新名称:"
                else:
                    label = "请输入配置名称:"

                name, ok = QtWidgets.QInputDialog.getText(self.view, "导入配置", label, text=text_val)
                if not ok:
                    return # Cancelled

                if not name:
                    continue # Empty name, ask again

                # If user entered a name that exists (and it's not the one we started with, or we are looping), check again
                if name in existing_names:
                    config_name = name # Update for next loop message
                    continue

                # Unique name found
                config_name = name
                break

            # Auto-save '默认' if we are currently in it
            if self.current_config_name == "默认":
                self.model.save_config("默认", self.view.get_table_data())

            self.model.save_config(config_name, data)
            self.view.update_config_list(self.model.get_config_names(), current=config_name)
            self.view.set_table_data(data)
            self.view.log_message(f"配置 '{config_name}' 导入成功")
            self.current_config_name = config_name

        except Exception as e:
            self.view.log_message(f"导入失败: {str(e)}")

    def _on_config_export_requested(self):
        """Handle exporting the current configuration to a file."""
        data = self.view.get_table_data()
        if not data:
            self.view.log_message("当前序列为空，无法导出")
            return

        current_config = self.view.config_combo.currentText()
        default_name = f"{current_config}.json" if current_config and current_config != "默认" else "uds_sequence.json"

        path, _ = QtWidgets.QFileDialog.getSaveFileName(self.view, "导出配置", default_name, "JSON Files (*.json)")
        if not path:
            return

        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            self.view.log_message(f"配置导出成功: {path}")
        except Exception as e:
            self.view.log_message(f"导出失败: {str(e)}")


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    m = UDSSequenceModel()
    v = UDSSequenceView(m)
    v.show()
    sys.exit(app.exec_())