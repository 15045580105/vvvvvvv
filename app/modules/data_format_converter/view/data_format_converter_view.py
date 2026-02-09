from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QTextEdit,
    QGroupBox,
    QGridLayout,
    QFrame,
    QProgressBar,
    QSplitter,
)

from app.common.ui.widgets import ModernButton
from app.presentation.views.base_view import BaseView


class DataFormatConverterView(BaseView):
    """数据格式转换 View：纯 UI，业务逻辑交给 Controller/Model。"""

    # 对外信号
    sig_file_dropped = pyqtSignal(str)  # 拖拽/选择到文件路径
    sig_output_dir_browse = pyqtSignal()
    sig_convert_clicked = pyqtSignal()
    sig_clear_log_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # BaseView 会调用 setup_ui

    def setup_ui(self):
        self.setAcceptDrops(True)

        main_splitter = QSplitter(Qt.Vertical)

        work_area = self._create_work_area()
        main_splitter.addWidget(work_area)

        log_area = self._create_log_area()
        main_splitter.addWidget(log_area)

        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([560, 190])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(main_splitter)

    # -------- UI 组装 --------
    def _create_work_area(self) -> QWidget:
        work_area = QWidget()
        work_layout = QVBoxLayout(work_area)
        work_layout.setContentsMargins(24, 24, 24, 24)
        work_layout.setSpacing(16)

        # 顶部标题行：标题 + 简短说明
        header_layout = QHBoxLayout()
        title_label = QLabel("数据格式转换")
        title_label.setObjectName("pageTitle")
        title_label.setStyleSheet("font-size: 12pt; font-weight: 600; color: #111827;")
        subtitle_label = QLabel("拖拽日志或总线数据文件，选择输出格式后一键转换")
        subtitle_label.setStyleSheet("font-size: 8.5pt; color: #6B7280; padding-left: 8px;")
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        header_layout.addStretch(1)
        work_layout.addLayout(header_layout)

        # 中间：拖拽区域 + 配置面板
        self.drop_zone = self._create_drop_zone()
        work_layout.addWidget(self.drop_zone)

        config_panel = self._create_config_panel()
        work_layout.addWidget(config_panel)

        # 底部仅保留一个“开始转换”按钮，紧贴右下角
        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 8, 0, 0)
        action_row.addStretch(1)

        self.convert_btn = ModernButton("开始转换")
        self.convert_btn.setObjectName("primaryButton")
        self.convert_btn.clicked.connect(self.sig_convert_clicked)
        action_row.addWidget(self.convert_btn)

        work_layout.addLayout(action_row)

        work_layout.setStretch(0, 0)  # 标题
        work_layout.setStretch(1, 3)  # 拖拽
        work_layout.setStretch(2, 2)  # 配置
        work_layout.setStretch(3, 0)  # 操作行

        return work_area

    def _create_drop_zone(self) -> QFrame:
        drop_frame = QFrame()
        drop_frame.setObjectName("dropZone")
        drop_frame.setStyleSheet(
            "QFrame#dropZone { background-color: #F8FAFC; border: 2px dashed #CBD5E1;"
            "border-radius: 12px; padding: 32px; }"
            "QFrame#dropZone:hover { background-color: #F1F5F9; border-color: #94A3B8; }"
        )

        layout = QVBoxLayout(drop_frame)
        layout.setSpacing(12)

        self.drop_icon_label = QLabel("📂")
        self.drop_icon_label.setAlignment(Qt.AlignCenter)
        self.drop_icon_label.setStyleSheet("font-size: 27pt; color: #9CA3AF;")

        self.drop_text_label = QLabel("拖拽文件到此处或点击选择")
        self.drop_text_label.setAlignment(Qt.AlignCenter)
        self.drop_text_label.setStyleSheet("font-size: 10pt; color: #4B5563;")

        self.select_file_btn = QPushButton("选择文件")
        self.select_file_btn.setObjectName("secondaryButton")
        self.select_file_btn.setStyleSheet(
            "QPushButton#secondaryButton { background-color: #3B82F6; color: white; border: none;"
            "border-radius: 6px; padding: 6px 18px; font-size: 10pt; }"
            "QPushButton#secondaryButton:hover { background-color: #2563EB; }"
        )
        # 交给 controller 打开文件对话框
        self.select_file_btn.clicked.connect(lambda: self.sig_file_dropped.emit(""))

        layout.addWidget(self.drop_icon_label)
        layout.addWidget(self.drop_text_label)
        layout.addWidget(self.select_file_btn, 0, Qt.AlignCenter)
        return drop_frame

    def _create_config_panel(self) -> QWidget:
        panel = QWidget()
        panel_layout = QGridLayout(panel)
        panel_layout.setHorizontalSpacing(20)
        panel_layout.setVerticalSpacing(16)

        # 左侧：输入配置
        input_group = QGroupBox("输入配置")
        input_layout = QVBoxLayout(input_group)
        input_layout.setSpacing(8)

        self.file_path_display = QLineEdit()
        self.file_path_display.setReadOnly(True)
        self.file_path_display.setPlaceholderText("未选择文件")
        self.file_path_display.setStyleSheet(
            "QLineEdit { background-color: #F3F4F6; border: 1px solid #E5E7EB;"
            "border-radius: 6px; padding: 6px 10px; font-size: 10pt; }"
        )
        input_layout.addWidget(QLabel("已选文件:"))
        input_layout.addWidget(self.file_path_display)

        input_layout.addWidget(QLabel("转换类型:"))
        self.conversion_type_combo = QComboBox()
        self.conversion_type_combo.addItems([
            "DLT日志 → 通用格式",
            "总线数据 → 分析格式",
        ])
        self.conversion_type_combo.setStyleSheet(
            "QComboBox { background-color: #FFFFFF; border: 1px solid #D1D5DB;"
            "border-radius: 6px; padding: 4px 10px; font-size: 10pt; }"
        )
        input_layout.addWidget(self.conversion_type_combo)

        input_layout.addWidget(QLabel("源格式:"))
        self.source_format_combo = QComboBox()
        self.source_format_combo.addItems(["DLT", "CAN", "LIN", "FlexRay", "Ethernet"])
        self.source_format_combo.setStyleSheet(self.conversion_type_combo.styleSheet())
        input_layout.addWidget(self.source_format_combo)
        input_layout.addStretch(1)

        # 右侧：输出配置
        output_group = QGroupBox("输出配置")
        output_layout = QVBoxLayout(output_group)
        output_layout.setSpacing(8)

        output_dir_layout = QHBoxLayout()
        output_dir_layout.setSpacing(6)
        self.output_path_display = QLineEdit()
        self.output_path_display.setReadOnly(True)
        self.output_path_display.setPlaceholderText("默认为源文件目录")
        self.output_path_display.setStyleSheet(self.file_path_display.styleSheet())
        self.output_browse_btn = QPushButton("📂")
        self.output_browse_btn.setFixedWidth(34)
        self.output_browse_btn.setToolTip("选择输出目录")
        self.output_browse_btn.setObjectName("accentButton")
        self.output_browse_btn.setStyleSheet(
            "QPushButton#accentButton { background-color: #8B5CF6; color: white; border: none;"
            "border-radius: 6px; padding: 4px 8px; }"
            "QPushButton#accentButton:hover { background-color: #7C3AED; }"
        )
        self.output_browse_btn.clicked.connect(self.sig_output_dir_browse)

        output_dir_layout.addWidget(self.output_path_display, 1)
        output_dir_layout.addWidget(self.output_browse_btn)

        output_layout.addWidget(QLabel("输出目录:"))
        output_layout.addLayout(output_dir_layout)

        output_layout.addWidget(QLabel("目标格式:"))
        self.target_format_combo = QComboBox()
        self.target_format_combo.addItems(["TXT", "CSV", "JSON", "MATLAB", "PCAP"])
        self.target_format_combo.setStyleSheet(self.conversion_type_combo.styleSheet())
        output_layout.addWidget(self.target_format_combo)

        output_layout.addWidget(QLabel("文件名模板:"))
        self.filename_template = QLineEdit()
        self.filename_template.setPlaceholderText("{original}_{timestamp}.{ext}")
        self.filename_template.setStyleSheet(
            "QLineEdit { background-color: #FFFFFF; border: 1px solid #D1D5DB;"
            "border-radius: 6px; padding: 6px 10px; font-size: 10pt; }"
        )
        output_layout.addWidget(self.filename_template)
        output_layout.addStretch(1)

        panel_layout.addWidget(input_group, 0, 0)
        panel_layout.addWidget(output_group, 0, 1)
        return panel

    def _create_log_area(self) -> QGroupBox:
        log_group = QGroupBox("转换日志")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(12, 12, 12, 12)

        toolbar = QHBoxLayout()
        self.log_clear_btn = QPushButton("🗑️ 清空")
        self.log_clear_btn.setObjectName("ghostButton")
        # 改为浅色主题按钮
        self.log_clear_btn.setStyleSheet(
            "QPushButton#ghostButton { background-color: #F9FAFB; color: #6B7280; border: 1px solid #E5E7EB;"
            "border-radius: 4px; padding: 4px 10px; font-size: 9pt; }"
            "QPushButton#ghostButton:hover { background-color: #E5E7EB; }"
        )
        self.log_clear_btn.clicked.connect(self.sig_clear_log_clicked)
        toolbar.addWidget(self.log_clear_btn)
        toolbar.addStretch(1)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("拖放文件或点击快速转换开始任务...\n支持批量处理和格式自动识别")
        # 日志区域改为浅色背景，深色文字，保持编码字体
        self.log_text.setStyleSheet(
            "QTextEdit { background-color: #FFFFFF; color: #111827; border: 1px solid #E5E7EB; border-radius: 6px;"
            "padding: 10px; font-family: 'Consolas','Monaco',monospace; font-size: 9pt; }"
        )

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        # 进度条也统一为浅色风格
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #E5E7EB; background-color: #F3F4F6; height: 8px; border-radius: 4px; }"
            "QProgressBar::chunk { background-color: #22C55E; border-radius: 4px; }"
        )

        log_layout.addLayout(toolbar)
        log_layout.addWidget(self.log_text)
        log_layout.addWidget(self.progress_bar)
        return log_group

    # -------- View 提供给 Controller 的方法 --------
    def set_selected_file(self, path: str):
        self.file_path_display.setText(path or "")

    def set_output_dir(self, path: str):
        self.output_path_display.setText(path or "")

    def append_log(self, msg: str):
        if not msg:
            return
        self.log_text.append(msg)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def clear_log(self):
        self.log_text.clear()

    def set_progress(self, value: int, visible: bool = True):
        """仅更新日志区域底部进度条。"""
        safe_value = max(0, min(100, int(value)))
        self.progress_bar.setVisible(visible)
        self.progress_bar.setValue(safe_value)

    def set_busy(self, busy: bool):
        self.convert_btn.setEnabled(not busy)

    def set_status_text(self, text: str):
        """预留状态文案接口，当前不在顶部显示，仅可选写入日志。"""
        if text:
            self.append_log(text)

    # -------- 拖拽事件：只负责 UI 和发信号 --------
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            # 保持和其它页面一致的浅蓝高亮效果
            self.drop_zone.setStyleSheet(
                "QFrame#dropZone { background-color: #DBEAFE; border: 2px dashed #3B82F6;"
                "border-radius: 12px; padding: 32px; }"
            )
            self.drop_text_label.setText("释放文件开始转换")
            self.drop_icon_label.setText("📤")

    def dragLeaveEvent(self, event):
        # 恢复为默认浅色背景
        self.drop_zone.setStyleSheet(
            "QFrame#dropZone { background-color: #F8FAFC; border: 2px dashed #CBD5E1;"
            "border-radius: 12px; padding: 32px; }"
        )
        self.drop_text_label.setText("拖拽文件到此处或点击选择")
        self.drop_icon_label.setText("📂")

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        file_path = urls[0].toLocalFile() if urls else ""
        if file_path:
            self.set_selected_file(file_path)
            self.sig_file_dropped.emit(file_path)
            event.acceptProposedAction()

        # 恢复样式
        self.dragLeaveEvent(event)
