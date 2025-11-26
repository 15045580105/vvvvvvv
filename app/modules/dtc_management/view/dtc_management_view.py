from PyQt5 import QtWidgets, QtGui, QtCore

from app.common.ui.widgets import ModernButton, create_icon
from app.presentation.views.base_view import BaseView


class DTCView(BaseView):
    def setup_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setSpacing(0)
        self.left_panel = QtWidgets.QFrame()
        left_layout = QtWidgets.QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0,0,0,0)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabel("故障分类")
        left_layout.addWidget(self.tree)
        self.center_panel = QtWidgets.QFrame()
        center_layout = QtWidgets.QVBoxLayout(self.center_panel)
        center_layout.setContentsMargins(0,0,0,0)
        self.table = QtWidgets.QTableWidget(0,5)
        self.table.setHorizontalHeaderLabels(["DTC代码","故障描述","状态","发生次数","首次时间"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        center_layout.addWidget(self.table)
        self.right_panel = QtWidgets.QFrame()
        right_layout = QtWidgets.QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0,0,0,0)
        self.freeze_text = QtWidgets.QTextEdit()
        self.freeze_text.setReadOnly(True)
        self.freeze_text.setFont(QtGui.QFont("Consolas",9))
        right_layout.addWidget(self.freeze_text)
        right_layout.addWidget(ModernButton("清除故障","#EF4444","🗑️"))
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self.left_panel)
        splitter.addWidget(self.center_panel)
        splitter.addWidget(self.right_panel)
        splitter.setSizes([180,500,320])
        layout.addWidget(splitter)

    def populate(self, categories, dtcs):
        self.tree.clear()
        for cat in categories:
            item = QtWidgets.QTreeWidgetItem(self.tree)
            item.setText(0, cat)
            item.setIcon(0, create_icon("⚠️", "#EF4444"))
        self.tree.expandAll()
        self.table.setRowCount(len(dtcs))
        for r, row in enumerate(dtcs):
            for c, val in enumerate(row):
                it = QtWidgets.QTableWidgetItem(val)
                it.setTextAlignment(QtCore.Qt.AlignCenter)
                self.table.setItem(r,c,it)

