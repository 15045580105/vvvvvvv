# python
from PyQt5 import QtWidgets, QtGui

from app.common.ui.widgets import ModernButton, TableButton
from app.presentation.views.base_view import BaseView


class UpgradeView(BaseView):
    """纯 UI 升级页面：仅负责界面布局，不包含业务逻辑或信号。"""

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # --- Tab widget 包含：常规升级 / 升级压测 ---
        self.tab = QtWidgets.QTabWidget()
        self._init_normal_upgrade_tab()
        self._init_stress_tab()
        main_layout.addWidget(self.tab)

        # --- Log panel 保持不变 ---
        log_group = QtWidgets.QGroupBox("升级日志")
        log_layout = QtWidgets.QVBoxLayout()

        filter_row = QtWidgets.QHBoxLayout()
        filter_row.addWidget(QtWidgets.QLabel("🔍 过滤:"))
        self.log_filter = QtWidgets.QLineEdit()
        self.log_filter.setPlaceholderText("输入关键字过滤日志")
        filter_row.addWidget(self.log_filter)
        self.auto_scroll_chk = QtWidgets.QCheckBox("自动滚动")
        self.auto_scroll_chk.setChecked(True)
        filter_row.addWidget(self.auto_scroll_chk)
        filter_row.addWidget(TableButton("清空", "#6B7280", "🧹"))
        filter_row.addStretch(1)
        log_layout.addLayout(filter_row)

        self.upgrade_log = QtWidgets.QTextEdit()
        self.upgrade_log.setReadOnly(True)
        self.upgrade_log.setFont(QtGui.QFont("Consolas", 9))
        self.upgrade_log.setMinimumHeight(180)
        log_layout.addWidget(self.upgrade_log)

        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group, 1)

    # -------------------- 常规升级 Tab --------------------
    def _init_normal_upgrade_tab(self):
        """常规升级：保持原来的单升级包 + 配置 + 校验 UI，不含循环次数和 +/-。"""
        normal_page = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout(normal_page)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        # 升级包（单行，无 +/-）
        layout.addWidget(QtWidgets.QLabel("📦 升级包:"), 0, 0)
        self.upgrade_file = QtWidgets.QLineEdit()
        self.upgrade_file.setPlaceholderText("选择升级包 (.zip / .bin)")
        layout.addWidget(self.upgrade_file, 0, 1)
        self.upgrade_file_browse_btn = ModernButton("浏览", "#0EA5E9", "📂")
        layout.addWidget(self.upgrade_file_browse_btn, 0, 2)

        # Config file
        layout.addWidget(QtWidgets.QLabel("⚙️ 配置文件:"), 1, 0)
        self.config_file = QtWidgets.QLineEdit()
        self.config_file.setPlaceholderText("选择升级配置 (.json / .yaml)")
        layout.addWidget(self.config_file, 1, 1)
        self.config_file_browse_btn = ModernButton("浏览", "#0EA5E9", "📂")
        layout.addWidget(self.config_file_browse_btn, 1, 2)

        # Checksum / size info
        layout.addWidget(QtWidgets.QLabel("🔐 校验信息:"), 2, 0)
        self.checksum_label = QtWidgets.QLabel("未解析")
        self.checksum_label.setStyleSheet("color:#6B7280;")
        layout.addWidget(self.checksum_label, 2, 1)
        self.checksum_refresh_btn = TableButton("重新解析", "#6B7280", "🔄")
        layout.addWidget(self.checksum_refresh_btn, 2, 2)

        # Action buttons row（沿用原来的开始/停止按钮）
        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(12)
        action_row.addStretch(1)
        self.start_btn = ModernButton("开始升级", "#059669", "🚀")
        self.stop_btn = ModernButton("停止升级", "#EF4444", "⏹️")
        self.start_btn.setEnabled(False)  # 需选择文件后启用
        self.stop_btn.setEnabled(False)
        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.stop_btn)

        layout.addLayout(action_row, 3, 0, 1, 3)

        self.tab.addTab(normal_page, "常规升级")

    # -------------------- 升级压测 Tab --------------------
    def _init_stress_tab(self):
        """升级压测：支持多升级包、循环次数、配置文件和校验信息。"""
        stress_page = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout(stress_page)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        # 升级包（压测支持多包，为未来交替升级做准备）
        layout.addWidget(QtWidgets.QLabel("📦 升级包:"), 0, 0)
        self.stress_pkg_container = QtWidgets.QWidget()
        self.stress_pkg_layout = QtWidgets.QVBoxLayout(self.stress_pkg_container)
        self.stress_pkg_layout.setContentsMargins(0, 0, 0, 0)
        self.stress_pkg_layout.setSpacing(4)
        layout.addWidget(self.stress_pkg_container, 0, 1, 1, 2)

        self.stress_pkg_rows = []  # list[tuple[QLineEdit, ModernButton]]
        self._add_stress_pkg_row()

        # 压测配置文件
        layout.addWidget(QtWidgets.QLabel("⚙️ 配置文件:"), 1, 0)
        self.stress_config_file = QtWidgets.QLineEdit()
        self.stress_config_file.setPlaceholderText("选择压测配置 (.json / .yaml)")
        layout.addWidget(self.stress_config_file, 1, 1)
        self.stress_config_browse_btn = ModernButton("浏览", "#0EA5E9", "📂")
        layout.addWidget(self.stress_config_browse_btn, 1, 2)

        # 压测校验信息
        layout.addWidget(QtWidgets.QLabel("🔐 校验信息:"), 2, 0)
        self.stress_checksum_label = QtWidgets.QLabel("未解析")
        self.stress_checksum_label.setStyleSheet("color:#6B7280;")
        layout.addWidget(self.stress_checksum_label, 2, 1)
        self.stress_checksum_refresh_btn = TableButton("重新解析", "#6B7280", "🔄")
        layout.addWidget(self.stress_checksum_refresh_btn, 2, 2)

        # 压测循环次数
        layout.addWidget(QtWidgets.QLabel("🔁 压测循环次数:"), 3, 0)
        self.stress_loop_spin = QtWidgets.QSpinBox()
        self.stress_loop_spin.setRange(1, 1_000_000)
        self.stress_loop_spin.setValue(100)
        layout.addWidget(self.stress_loop_spin, 3, 1)

        # 压测操作按钮
        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(12)
        action_row.addStretch(1)
        self.stress_start_btn = ModernButton("开始压测", "#0F766E", "🔥")
        self.stress_stop_btn = ModernButton("停止压测", "#DC2626", "⏹️")
        self.stress_start_btn.setEnabled(False)
        self.stress_stop_btn.setEnabled(False)
        action_row.addWidget(self.stress_start_btn)
        action_row.addWidget(self.stress_stop_btn)

        layout.addLayout(action_row, 4, 0, 1, 3)

        self.tab.addTab(stress_page, "升级压测")

    # -------------------- 升级压测：多包行管理 --------------------
    def _add_stress_pkg_row(self):
        row_widget = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        line_edit = QtWidgets.QLineEdit()
        line_edit.setPlaceholderText("选择升级包 (.zip / .bin)")
        browse_btn = ModernButton("浏览", "#0EA5E9", "📂")

        add_btn = ModernButton("➕", "#22C55E", "")
        remove_btn = ModernButton("➖", "#EF4444", "")

        # 这里只管理 UI 行；业务逻辑可在 controller 里统一接管
        add_btn.clicked.connect(self._add_stress_pkg_row)
        remove_btn.clicked.connect(lambda: self._remove_stress_pkg_row(row_widget))

        row_layout.addWidget(line_edit, 1)
        row_layout.addWidget(browse_btn)
        row_layout.addWidget(add_btn)
        row_layout.addWidget(remove_btn)

        self.stress_pkg_layout.addWidget(row_widget)
        self.stress_pkg_rows.append((line_edit, browse_btn))

    def _remove_stress_pkg_row(self, row_widget: QtWidgets.QWidget):
        """删除一行压测升级包，至少保留一行。"""
        if len(self.stress_pkg_rows) <= 1:
            return

        self.stress_pkg_layout.removeWidget(row_widget)
        row_widget.setParent(None)

        # 重建 rows 列表（扫描现有行）
        self.stress_pkg_rows = []
        for i in range(self.stress_pkg_layout.count()):
            item = self.stress_pkg_layout.itemAt(i)
            w = item.widget()
            if w is None:
                continue
            le = w.findChild(QtWidgets.QLineEdit)
            btn = w.findChild(ModernButton)
            if le is not None and btn is not None:
                self.stress_pkg_rows.append((le, btn))

    def show_device_targets(self, devices):
        """在升级界面显示目标设备信息（如设备名/IP等）"""
        # 功能已裁剪：仅保留接口以避免其他模块引用报错
        # 如果未来需要重新展示设备信息，可在此补充 UI 元素
        pass


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    w = UpgradeView()
    w.setup_ui()
    w.show()
    app.exec_()
