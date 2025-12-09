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

    def _on_command_selected(self, row: int):
        if 0 <= row < len(self.model.commands):
            self.view.set_editor_enabled(True)
            command = self.model.commands[row]
            self.view.set_placeholders(command)
            self._load_table_data_for_command(command)
        else:
            self.view.clear_editor()

    def _load_table_data_for_command(self, command: str):
        """Load table data for a given command from model (placeholder implementation)."""
        self.view.reset_table()
        # 示例数据逻辑可根据真实 model 拓展
        if "DiagnosticSessionControl" in command:
            self.view.append_table_row("session_type", "03", "会话类型(03=扩展会话)")
            self.view.append_table_row("suppress_rsp", "False", "抑制正响应")
if __name__ == "__main__":
    import sys
    from app.modules.uds_sequence.model.uds_sequence_model import UDSSequenceModel

    app = QtWidgets.QApplication(sys.argv)
    m = UDSSequenceModel()
    v = UDSSequenceView(m)
    v.show()
    sys.exit(app.exec_())