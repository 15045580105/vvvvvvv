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
        self.setStyleSheet("""
            ECUInitView {
                background-color: #F8FAFC;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
            }
            QLabel {
                font-family: "Segoe UI", "Microsoft YaHei";
                font-size: 10pt;
                color: #4B5563;
                font-weight: 600;
            }
            QLineEdit {
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
            QComboBox {
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 8px 12px;
                background-color: #FFFFFF;
                color: #1F2937;
                font-size: 9.5pt;
            }
            QComboBox:hover, QLineEdit:hover {
                border: 1px solid #3B82F6;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(25)

        # 1. 文件导入区域 (无边框)
        file_layout = QtWidgets.QHBoxLayout()

        self.file_label = QtWidgets.QLabel("全局配置码ini导入:")
        self.file_label.setFixedWidth(140) # 固定宽度对齐

        self.file_path_edit = QtWidgets.QLineEdit()
        self.file_path_edit.setPlaceholderText("请选择 cfg.ini 文件路径...")
        self.file_path_edit.setReadOnly(True)
        self.file_path_edit.setMinimumHeight(36)

        self.file_btn = ModernButton("选择文件", "#3B82F6", "📂")
        self.file_btn.setFixedSize(110, 36)
        self.file_btn.clicked.connect(self._on_file_btn_clicked)

        file_layout.addWidget(self.file_label)
        file_layout.addWidget(self.file_path_edit)
        file_layout.addWidget(self.file_btn)

        layout.addLayout(file_layout)

        # 2. MTOC 选择区域 (居中下拉框)
        mtoc_layout = QtWidgets.QHBoxLayout()

        self.mtoc_label = QtWidgets.QLabel("车型MTOC选择:") # 稍微改下文案匹配风格
        self.mtoc_label.setFixedWidth(140)

        self.mtoc_combo = QtWidgets.QComboBox()
        self.mtoc_combo.setPlaceholderText("请先导入配置文件...")
        self.mtoc_combo.setMinimumHeight(36)
        self.mtoc_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        mtoc_layout.addWidget(self.mtoc_label)
        mtoc_layout.addWidget(self.mtoc_combo)
        # 右侧添加一个占位控件以保持与上方按钮对齐的视觉平衡，或者让下拉框填满
        # 这里让下拉框填满，与上方输入框对齐
        placeholder = QtWidgets.QWidget()
        placeholder.setFixedSize(110, 36) # 与上方按钮同宽
        # mtoc_layout.addWidget(placeholder) # 如果想让下拉框和输入框一样宽，可以加这个占位，或者直接让下拉框伸展

        # 为了美观，让下拉框占据剩余空间，不加占位了，这样下拉框会比输入框长一点（因为输入框右边有按钮）
        # 或者我们可以让下拉框和输入框对齐，右边留空
        # 方案：让下拉框和输入框一样长，右边放一个空的 widget 占位
        spacer_widget = QtWidgets.QWidget()
        spacer_widget.setFixedSize(118, 36) # 110 + spacing
        mtoc_layout.addWidget(spacer_widget)

        layout.addLayout(mtoc_layout)

        # 3. 操作区域
        action_layout = QtWidgets.QHBoxLayout()
        action_layout.addStretch()

        self.init_btn = ModernButton("一键初始化", "#10B981", "🚀")
        self.init_btn.setFixedSize(180, 44) # 稍微大一点
        self.init_btn.clicked.connect(self.init_requested.emit)

        action_layout.addWidget(self.init_btn)
        action_layout.addStretch()

        layout.addLayout(action_layout)

        # 4. 进度条
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setFixedHeight(24)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 12px;
                text-align: center;
                background-color: #E5E7EB;
                color: #374151;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #10B981;
                border-radius: 12px;
            }
        """)

        layout.addWidget(self.progress_bar)

        # 填充剩余空间
        layout.addStretch()

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

    def get_selected_mtoc(self) -> str:
        """获取当前选中的 MTOC"""
        return self.mtoc_combo.currentText()

    def set_progress(self, value: int):
        """设置进度条值"""
        self.progress_bar.setValue(value)
