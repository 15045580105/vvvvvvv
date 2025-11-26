from PyQt5 import QtWidgets, QtCore

from app.common.ui.widgets import ModernButton
from app.presentation.views.base_view import BaseView


class LogConfigView(BaseView):
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        ecu_group = QtWidgets.QGroupBox("ECU日志等级设置")
        ecu_layout = QtWidgets.QHBoxLayout()
        ecu_layout.setSpacing(15)
        self.ecu_combos = {}
        for ecu in ["CCUA","CCU0","CCU1"]:
            ecu_layout.addWidget(QtWidgets.QLabel(f"{ecu}:"))
            combo = QtWidgets.QComboBox()
            combo.setMinimumWidth(140)
            combo.addItems(["OFF","FATAL","ERROR","WARN","INFO","DEBUG","VERBOSE"])
            self.ecu_combos[ecu] = combo
            ecu_layout.addWidget(combo)
        ecu_layout.addStretch()
        ecu_group.setLayout(ecu_layout)
        layout.addWidget(ecu_group)
        app_group = QtWidgets.QGroupBox("APP日志设置")
        app_layout = QtWidgets.QVBoxLayout()
        search_layout = QtWidgets.QHBoxLayout()
        search_layout.addWidget(QtWidgets.QLabel("🔍 搜索:"))
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("APPID或ECU...")
        search_layout.addWidget(self.search_edit)
        search_layout.addStretch()
        search_layout.addWidget(ModernButton("刷新", "#0EA5E9", "🔄"))
        app_layout.addLayout(search_layout)
        self.app_table = QtWidgets.QTableWidget(0,4)
        self.app_table.setHorizontalHeaderLabels(["APPID","ECU","当前等级","操作"])
        self.app_table.verticalHeader().setVisible(False)
        self.app_table.setAlternatingRowColors(True)
        app_layout.addWidget(self.app_table)
        app_group.setLayout(app_layout)
        layout.addWidget(app_group)
        restore_group = QtWidgets.QGroupBox("恢复默认配置")
        restore_layout = QtWidgets.QHBoxLayout()
        restore_layout.setSpacing(15)
        self.restore_ccua = QtWidgets.QCheckBox("恢复CCUA默认")
        self.restore_ccu0 = QtWidgets.QCheckBox("恢复CCU0默认")
        self.restore_ccu1 = QtWidgets.QCheckBox("恢复CCU1默认")
        self.delete_logs = QtWidgets.QCheckBox("删除日志文件")
        for chk in [self.restore_ccua,self.restore_ccu0,self.restore_ccu1,self.delete_logs]:
            restore_layout.addWidget(chk)
        restore_layout.addStretch()
        self.restore_btn = ModernButton("执行恢复", "#EF4444", "⚠️")
        restore_layout.addWidget(self.restore_btn)
        restore_group.setLayout(restore_layout)
        layout.addWidget(restore_group)

    def populate(self, apps):
        self.app_table.setRowCount(len(apps))
        for i,(app,ecu,level) in enumerate(apps):
            for col,val in enumerate([app,ecu,level,"修改"]):
                item = QtWidgets.QTableWidgetItem(val)
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                self.app_table.setItem(i,col,item)

