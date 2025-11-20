from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QMessageBox, QCheckBox)
from PyQt5.QtCore import pyqtSignal

from app.common.utils.machine_code import get_machine_code


class LoginDialog(QDialog):
    """登录对话框"""

    login_success = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GAC工具登录")
        self.setModal(True)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # 机器码显示
        machine_code = get_machine_code()
        machine_label = QLabel(f"机器码: {machine_code}")
        layout.addWidget(machine_label)

        # 授权码输入
        auth_layout = QHBoxLayout()
        auth_layout.addWidget(QLabel("授权码:"))
        self.auth_input = QLineEdit()
        self.auth_input.setPlaceholderText("请输入授权码")
        auth_layout.addWidget(self.auth_input)
        layout.addLayout(auth_layout)

        # 记住我选项
        self.remember_check = QCheckBox("记住登录状态")
        layout.addWidget(self.remember_check)

        # 按钮布局
        button_layout = QHBoxLayout()
        login_btn = QPushButton("登录")
        login_btn.clicked.connect(self.attempt_login)
        button_layout.addWidget(login_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def attempt_login(self):
        """尝试登录"""
        auth_code = self.auth_input.text().strip()

        if not auth_code:
            QMessageBox.warning(self, "输入错误", "请输入授权码")
            return

        # 简化的授权验证（实际应该更复杂）
        if self.validate_auth_code(auth_code):
            self.login_success.emit()
            self.accept()
        else:
            QMessageBox.critical(self, "登录失败", "授权码无效")

    def validate_auth_code(self, code):
        """验证授权码（简化版）"""
        # 实际应该根据机器码进行复杂的验证
        return len(code) >= 8  # 简单长度验证