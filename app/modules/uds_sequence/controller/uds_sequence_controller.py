from PyQt5 import QtWidgets

from app.core.base_controller import BaseController
from app.modules.uds_sequence.model.uds_sequence_model import UDSSequenceModel
from app.modules.uds_sequence.view.uds_sequence_view import UDSSequenceView


class UDSSequenceController(BaseController):
    def __init__(self, parent=None):
        self.model = UDSSequenceModel(parent)
        self.view = UDSSequenceView(self.model, parent)
        super().__init__(self.model, self.view, parent)

        self._connect_signals()

    def _connect_signals(self):
        self.view.send_requested.connect(self._on_send_requested)
        self.view.insert_requested.connect(self._on_insert_requested)
        self.view.table_operation_requested.connect(self._on_table_operation)
        self.view.delay_insert_requested.connect(self._on_delay_insert_requested)
        self.view.send_batch_requested.connect(self._on_send_batch_requested)
        # view now emits string code like '10' or '10.01'
        self.view.command_selected.connect(self._on_command_selected)

    # --- Signal handlers ---
    def _on_send_requested(self, request_data: str):
        if request_data:
            self.model.log += f"发送请求: {request_data}\n"
            self.view.log_message(f"发送请求: {request_data}")
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
            self.view.append_table_row("新参数", "", "请输入描述")
        elif operation == "删除":
            if current_row >= 0:
                self.view.remove_table_row(current_row)
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


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    m = UDSSequenceModel()
    v = UDSSequenceView(m)
    v.show()
    sys.exit(app.exec_())