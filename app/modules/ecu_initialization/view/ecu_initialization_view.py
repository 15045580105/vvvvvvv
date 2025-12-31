from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt
from app.presentation.views.base_view import BaseView
from app.common.ui.widgets import ModernButton

class ECUInitView(BaseView):
    file_selected = QtCore.pyqtSignal(str)
    init_requested = QtCore.pyqtSignal()

    def setup_ui(self):
        # 设置整体样式，增加背景色和边界感
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        # 设置初始大小，确保尽量显示完整内容
        self.resize(1000, 850)
        self.setMinimumSize(800, 600)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        self.setStyleSheet("""
            ECUInitView {
                background-color: #F8FAFC;
            }
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QWidget#content_widget {
                background-color: #F8FAFC;
            }
            QFrame.card {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
            QLabel {
                font-family: "Segoe UI", "Microsoft YaHei";
                font-size: 10pt;
                color: #4B5563;
                font-weight: 600;
            }
            QLabel.header {
                font-size: 12pt;
                color: #1F2937;
                font-weight: bold;
                margin-bottom: 5px;
            }
            QLineEdit, QComboBox {
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 8px 12px;
                background-color: #FFFFFF;
                color: #1F2937;
                font-size: 9.5pt;
            }
            QLineEdit:read-only {
                background-color: #F3F4F6;
                color: #6B7280;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #3B82F6;
            }
            QListWidget {
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                background-color: #FFFFFF;
                padding: 5px;
                outline: none;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #F3F4F6;
                color: #374151;
            }
            QListWidget::item:hover {
                background-color: #F3F4F6;
            }
            QListWidget::item:selected {
                background-color: #EFF6FF;
                color: #1D4ED8;
            }
            QPushButton.action-btn {
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 6px 16px;
                background-color: #FFFFFF;
                color: #374151;
                font-weight: 500;
            }
            QPushButton.action-btn:hover {
                background-color: #F3F4F6;
                border-color: #9CA3AF;
            }
        """)

        # Main layout wrapper for scrolling
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.content_widget = QtWidgets.QWidget()
        self.content_widget.setObjectName("content_widget")

        layout = QtWidgets.QVBoxLayout(self.content_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll_area)

        # --- 1. Configuration Card ---
        config_card = QtWidgets.QFrame()
        config_card.setProperty("class", "card")
        config_card.setStyleSheet(".QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }")
        config_layout = QtWidgets.QVBoxLayout(config_card)
        config_layout.setContentsMargins(15, 15, 15, 15)
        config_layout.setSpacing(10)

        # Header
        header_label = QtWidgets.QLabel("配置导入")
        header_label.setProperty("class", "header")
        header_label.setStyleSheet("font-size: 12pt; color: #1F2937; font-weight: bold;")
        config_layout.addWidget(header_label)

        # File Import Row
        file_layout = QtWidgets.QHBoxLayout()
        self.file_label = QtWidgets.QLabel("配置文件:")
        self.file_label.setFixedWidth(80)

        self.file_path_edit = QtWidgets.QLineEdit()
        self.file_path_edit.setPlaceholderText("请选择 cfg.ini 文件路径...")
        self.file_path_edit.setReadOnly(True)
        self.file_path_edit.setMinimumHeight(36)

        self.file_btn = ModernButton("浏览", "#3B82F6", "📂")
        self.file_btn.setFixedSize(90, 36)
        self.file_btn.clicked.connect(self._on_file_btn_clicked)

        file_layout.addWidget(self.file_label)
        file_layout.addWidget(self.file_path_edit)
        file_layout.addWidget(self.file_btn)
        config_layout.addLayout(file_layout)

        # MTOC Selection Row
        mtoc_layout = QtWidgets.QHBoxLayout()
        self.mtoc_label = QtWidgets.QLabel("车型选择:")
        self.mtoc_label.setFixedWidth(80)

        self.mtoc_combo = QtWidgets.QComboBox()
        self.mtoc_combo.setPlaceholderText("请先导入配置文件...")
        self.mtoc_combo.setMinimumHeight(36)
        self.mtoc_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        mtoc_layout.addWidget(self.mtoc_label)
        mtoc_layout.addWidget(self.mtoc_combo)

        # Spacer to align with file button
        spacer = QtWidgets.QWidget()
        spacer.setFixedSize(98, 36) # 90 + spacing
        mtoc_layout.addWidget(spacer)

        config_layout.addLayout(mtoc_layout)
        layout.addWidget(config_card)

        # --- 2. ECU Selection Card ---
        ecu_card = QtWidgets.QFrame()
        ecu_card.setProperty("class", "card")
        ecu_card.setStyleSheet(".QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }")
        ecu_layout = QtWidgets.QVBoxLayout(ecu_card)
        ecu_layout.setContentsMargins(15, 15, 15, 15)
        ecu_layout.setSpacing(10)

        # Header & Filter Row
        ecu_header_layout = QtWidgets.QHBoxLayout()
        ecu_header_label = QtWidgets.QLabel("ECU 选择")
        ecu_header_label.setStyleSheet("font-size: 12pt; color: #1F2937; font-weight: bold;")

        self.ecu_filter_edit = QtWidgets.QLineEdit()
        self.ecu_filter_edit.setPlaceholderText("🔍 搜索 ECU...")
        self.ecu_filter_edit.setFixedWidth(250)
        self.ecu_filter_edit.textChanged.connect(self.filter_ecus)

        ecu_header_layout.addWidget(ecu_header_label)
        ecu_header_layout.addStretch()
        ecu_header_layout.addWidget(self.ecu_filter_edit)
        ecu_layout.addLayout(ecu_header_layout)

        # List Widget
        self.ecu_list = QtWidgets.QListWidget()
        self.ecu_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        # Use a flexible height policy
        self.ecu_list.setMinimumHeight(200)
        self.ecu_list.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        ecu_layout.addWidget(self.ecu_list)

        # Selection Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.select_all_btn = QtWidgets.QPushButton("全选")
        self.select_all_btn.setCursor(Qt.PointingHandCursor)
        self.select_all_btn.setProperty("class", "action-btn")
        self.select_all_btn.clicked.connect(self.select_all_ecus)

        self.deselect_all_btn = QtWidgets.QPushButton("全不选")
        self.deselect_all_btn.setCursor(Qt.PointingHandCursor)
        self.deselect_all_btn.setProperty("class", "action-btn")
        self.deselect_all_btn.clicked.connect(self.deselect_all_ecus)

        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.deselect_all_btn)
        btn_layout.addStretch()
        ecu_layout.addLayout(btn_layout)

        layout.addWidget(ecu_card, 1) # Give ECU card stretch factor 1 to fill space

        # --- 3. Action Card ---
        action_card = QtWidgets.QFrame()
        action_card.setProperty("class", "card")
        action_card.setStyleSheet(".QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }")
        action_layout = QtWidgets.QVBoxLayout(action_card)
        action_layout.setContentsMargins(15, 15, 15, 15)
        action_layout.setSpacing(10)

        # Progress Bar
        progress_layout = QtWidgets.QVBoxLayout()
        progress_label = QtWidgets.QLabel("初始化进度")
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 10px;
                text-align: center;
                background-color: #F3F4F6;
                color: #374151;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #10B981;
                border-radius: 10px;
            }
        """)
        progress_layout.addWidget(progress_label)
        progress_layout.addWidget(self.progress_bar)
        action_layout.addLayout(progress_layout)

        # Init Button
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        self.init_btn = ModernButton("开始初始化", "#10B981", "🚀")
        self.init_btn.setFixedSize(200, 48)
        self.init_btn.clicked.connect(self.init_requested.emit)
        btn_row.addWidget(self.init_btn)
        btn_row.addStretch()

        action_layout.addLayout(btn_row)
        layout.addWidget(action_card)

    def _on_file_btn_clicked(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "选择配置文件",
            "",
            "INI Files (*.ini);;All Files (*.*)"
        )
        if file_path:
            self.file_path_edit.setText(file_path)
            self.file_selected.emit(file_path)

    def set_mtoc_items(self, items: list):
        """设置下拉框选项"""
        self.mtoc_combo.clear()
        self.mtoc_combo.addItems(items)

    def set_ecu_items(self, items: list):
        """设置 ECU 选项"""
        self.ecu_list.clear()
        for item_text in items:
            item = QtWidgets.QListWidgetItem(item_text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.ecu_list.addItem(item)

    def filter_ecus(self, text: str):
        """Filter ECUs based on text"""
        for i in range(self.ecu_list.count()):
            item = self.ecu_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def get_selected_ecus(self) -> list:
        """获取选中的 ECU 列表"""
        selected = []
        for i in range(self.ecu_list.count()):
            item = self.ecu_list.item(i)
            if item.checkState() == Qt.Checked:
                selected.append(item.text())
        return selected

    def select_all_ecus(self):
        """全选 ECU"""
        for i in range(self.ecu_list.count()):
            item = self.ecu_list.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.Checked)

    def deselect_all_ecus(self):
        """全不选 ECU"""
        for i in range(self.ecu_list.count()):
            item = self.ecu_list.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.Unchecked)

    def get_selected_mtoc(self) -> str:
        """获取当前选中的 MTOC"""
        return self.mtoc_combo.currentText()

    def set_progress(self, value: int):
        """设置进度条值"""
        self.progress_bar.setValue(value)
