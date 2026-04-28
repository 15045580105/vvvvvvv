import sys

from PyQt5 import QtWidgets

from app.common.ui.modern_widgets import MessageToast
from app.common.utils.license_manager import ActivationCodeError, decode_activation_code


class ActivationCodeGenerator(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VCC License 校验工具")
        self.resize(760, 420)
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        tip = QtWidgets.QLabel("旧的本地激活码生成方式已移除。此工具仅用于校验并解析新的 443 位激活码。")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        code_row = QtWidgets.QHBoxLayout()
        code_row.addWidget(QtWidgets.QLabel("激活码:"))
        self.code_input = QtWidgets.QTextEdit()
        self.code_input.setPlaceholderText("在此粘贴激活码")
        self.code_input.setMinimumHeight(100)
        code_row.addWidget(self.code_input, 1)
        layout.addLayout(code_row)

        result_row = QtWidgets.QHBoxLayout()
        result_row.addWidget(QtWidgets.QLabel("解析结果:"))
        self.result_output = QtWidgets.QTextEdit()
        self.result_output.setReadOnly(True)
        self.result_output.setMinimumHeight(180)
        result_row.addWidget(self.result_output, 1)
        layout.addLayout(result_row)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        decode_btn = QtWidgets.QPushButton("校验激活码")
        decode_btn.clicked.connect(self._on_generate)
        btn_row.addWidget(decode_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def _on_generate(self):
        code = self.code_input.toPlainText().strip()
        if not code:
            MessageToast(self).show_toast("请先输入激活码", 1)
            return
        try:
            decoded = decode_activation_code(code)
        except ActivationCodeError as exc:
            self.result_output.setPlainText(f"校验失败：{exc}")
            return

        self.result_output.setPlainText(
            "\n".join(
                [
                    "校验成功",
                    f"Machine ID: {decoded.machine_id}",
                    f"授权天数: {decoded.license_days}",
                    f"激活码失效时间(秒): {decoded.expire_code_seconds}",
                    f"已激活次数: {decoded.activated_count}",
                    f"生成时间: {decoded.generate_time:%Y-%m-%d %H:%M:%S}",
                    f"过期时间: {decoded.expire_time:%Y-%m-%d %H:%M:%S}",
                    f"姓名: {decoded.user_info.name or '-'}",
                    f"部门: {decoded.user_info.department or '-'}",
                    f"邮箱: {decoded.user_info.email or '-'}",
                    f"Token: {decoded.token}",
                ]
            )
        )


def main():
    app = QtWidgets.QApplication(sys.argv)
    dlg = ActivationCodeGenerator()
    dlg.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

