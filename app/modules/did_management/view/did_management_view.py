from PyQt5 import QtWidgets, QtGui

from app.common.ui.widgets import ModernButton
from app.presentation.views.base_view import BaseView


class DIDView(BaseView):
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        ctl = QtWidgets.QHBoxLayout()
        ctl.setSpacing(12)
        ctl.addWidget(QtWidgets.QLabel("目标ECU:"))
        self.ecu_combo = QtWidgets.QComboBox()
        self.ecu_combo.addItems(["CCUA (0x71A)", "CCU0 (0x71B)", "CCU1 (0x71C)"])
        ctl.addWidget(self.ecu_combo)
        ctl.addWidget(QtWidgets.QLabel("DID:"))
        self.did_input = QtWidgets.QLineEdit()
        self.did_input.setPlaceholderText("例如: 0xF190")
        ctl.addWidget(self.did_input)
        self.read_btn = ModernButton("读取", "#0EA5E9", "🔍")
        self.write_btn = ModernButton("写入", "#F59E0B", "✏️")
        ctl.addWidget(self.read_btn)
        ctl.addWidget(self.write_btn)
        ctl.addStretch()
        layout.addLayout(ctl)
        response_group = QtWidgets.QGroupBox("响应数据")
        resp_layout = QtWidgets.QHBoxLayout()
        resp_layout.setSpacing(12)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["字段", "值"])
        resp_layout.addWidget(self.tree)
        self.raw_text = QtWidgets.QTextEdit()
        self.raw_text.setPlaceholderText("原始数据将在这里显示...")
        self.raw_text.setMaximumWidth(380)
        self.raw_text.setFont(QtGui.QFont("Consolas", 9))
        resp_layout.addWidget(self.raw_text)
        response_group.setLayout(resp_layout)
        layout.addWidget(response_group)

    def populate(self, items, raw):
        self.tree.clear()
        for k,v in items:
            it = QtWidgets.QTreeWidgetItem(self.tree)
            it.setText(0,k)
            it.setText(1,v)
        self.tree.expandAll()
        self.raw_text.setText(raw)

