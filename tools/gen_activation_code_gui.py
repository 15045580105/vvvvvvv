import sys

from PyQt5 import QtWidgets

from app.common.ui.modern_widgets import MessageToast
from app.common.utils.license_manager import expected_activation_code


class ActivationCodeGenerator(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VCC上位机激活码生成器")
        self.resize(640, 240)
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        mc_row = QtWidgets.QHBoxLayout()
        mc_row.addWidget(QtWidgets.QLabel("机器码:"))
        self.mc_input = QtWidgets.QLineEdit()
        self.mc_input.setPlaceholderText("在此粘贴用户机器码")
        mc_row.addWidget(self.mc_input, 1)
        layout.addLayout(mc_row)

        code_row = QtWidgets.QHBoxLayout()
        code_row.addWidget(QtWidgets.QLabel("激活码:"))
        self.code_output = QtWidgets.QTextEdit()
        self.code_output.setReadOnly(True)
        self.code_output.setMinimumHeight(80)
        code_row.addWidget(self.code_output, 1)
        layout.addLayout(code_row)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        gen_btn = QtWidgets.QPushButton("生成激活码")
        gen_btn.clicked.connect(self._on_generate)
        btn_row.addWidget(gen_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def _on_generate(self):
        mc = self.mc_input.text().strip()
        if not mc:
            MessageToast(self.view).show_toast("请先输入机器码", 1)
            return
        code = expected_activation_code(mc)
        self.code_output.setPlainText(code)


def main():
    app = QtWidgets.QApplication(sys.argv)
    dlg = ActivationCodeGenerator()
    dlg.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

