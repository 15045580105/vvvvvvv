from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QMessageBox, QTextEdit)
from PyQt5.QtCore import pyqtSignal, Qt

from app.common.utils.machine_code import get_machine_code
from app.common.utils.license_manager import activate, expected_activation_code


class LoginDialog(QDialog):
    """登录对话框——在主界面上方悬浮的激活窗口"""

    login_success = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GAC工具激活")
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.resize(720, 320)  # 缩小窗口，避免比主界面大
        self.setup_ui()
        # 将对话框居中到父窗口上方
        if parent is not None:
            geo = parent.frameGeometry()
            center = geo.center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("首次使用需要完成机器码激活")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        # 机器码一排：标签 + 可复制的多行文本
        machine_code = get_machine_code()
        self.machine_code = machine_code
        mc_layout = QHBoxLayout()
        mc_label = QLabel("机器码:")
        mc_layout.addWidget(mc_label)
        machine_value = QLabel(machine_code)
        machine_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        machine_value.setWordWrap(True)
        machine_value.setStyleSheet(
            "border: 1px solid #ccc; padding: 8px; background: #f5f5f5; font-family: Consolas;"
        )
        mc_layout.addWidget(machine_value, 1)
        layout.addLayout(mc_layout)

        # 激活码一排：标签 + 高文本输入框（支持多行）
        auth_layout = QHBoxLayout()
        auth_layout.addWidget(QLabel("激活码:"))
        self.auth_input = QTextEdit()
        self.auth_input.setPlaceholderText("请输入激活码")
        self.auth_input.setMinimumHeight(80)  # 设置最小高度，支持长激活码
        auth_layout.addWidget(self.auth_input, 1)
        layout.addLayout(auth_layout)

        # 测试环境自动填入激活码
        expected_code = expected_activation_code(machine_code)
        self.auth_input.setPlainText(expected_code)

        # 按钮行
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        login_btn = QPushButton("激活")
        login_btn.clicked.connect(self.attempt_login)
        button_layout.addWidget(login_btn)

        cancel_btn = QPushButton("退出")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        button_layout.addStretch(1)

        layout.addLayout(button_layout)

    def attempt_login(self):
        """尝试激活"""
        auth_code = self.auth_input.toPlainText().strip()

        if not auth_code:
            QMessageBox.warning(self, "输入错误", "请输入激活码")
            return

        if activate(auth_code):
            self.login_success.emit()
            self.accept()
        else:
            QMessageBox.critical(self, "激活失败", "激活码无效，请联系管理员")
