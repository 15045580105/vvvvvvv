from PyQt5 import QtWidgets

from app.common.ui.widgets import ModernButton


class UDSSequenceView(QtWidgets.QDialog):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.setWindowTitle("UDS指令编排")
        self.resize(900, 650)
        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        cmd_group = QtWidgets.QGroupBox("UDS服务序列")
        cmd_layout = QtWidgets.QHBoxLayout()
        cmd_layout.setSpacing(12)
        self.cmd_list = QtWidgets.QListWidget()
        self.cmd_list.addItems(self.model.commands)
        cmd_layout.addWidget(self.cmd_list)
        btn_layout = QtWidgets.QVBoxLayout()
        btn_layout.setSpacing(8)
        for text in ["添加", "编辑", "删除", "上移", "下移"]:
            btn_layout.addWidget(ModernButton(text, "#059669" if text == "添加" else "#0EA5E9"))
        btn_layout.addStretch()
        cmd_layout.addLayout(btn_layout)
        cmd_group.setLayout(cmd_layout)
        layout.addWidget(cmd_group)
        exec_group = QtWidgets.QGroupBox("执行控制")
        exec_layout = QtWidgets.QHBoxLayout()
        exec_layout.setSpacing(12)
        exec_layout.addWidget(ModernButton("执行序列", "#059669", "▶️"))
        exec_layout.addWidget(ModernButton("暂停", "#F59E0B", "⏸️"))
        exec_layout.addWidget(ModernButton("停止", "#EF4444", "⏹️"))
        exec_layout.addStretch()
        exec_layout.addWidget(QtWidgets.QLabel("循环次数:"))
        self.loop_spin = QtWidgets.QSpinBox()
        self.loop_spin.setValue(1)
        self.loop_spin.setMaximum(100)
        exec_layout.addWidget(self.loop_spin)
        exec_group.setLayout(exec_layout)
        layout.addWidget(exec_group)
        log_group = QtWidgets.QGroupBox("执行日志")
        log_layout = QtWidgets.QVBoxLayout()
        self.exec_log = QtWidgets.QTextEdit()
        self.exec_log.setReadOnly(True)
        self.exec_log.setPlaceholderText("UDS指令执行日志将在这里显示...\n包含发送数据、响应数据、时间戳")
        log_layout.addWidget(self.exec_log)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
