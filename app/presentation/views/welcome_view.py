from PyQt5 import QtWidgets, QtGui
from PyQt5.QtCore import Qt, pyqtSignal
from app.common.ui.constants import PageConfig

class WelcomeWidget(QtWidgets.QWidget):

    action_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            WelcomeWidget {
                background-color: #F9FAFB;
            }
        """)

        # Main layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        content_wrapper = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content_wrapper)
        content_layout.setAlignment(Qt.AlignCenter)
        content_layout.setSpacing(60)
        content_layout.setContentsMargins(40, 40, 40, 40)

        # Header
        header_container = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header_container)
        header_layout.setSpacing(16)

        title = QtWidgets.QLabel("OneBox For GAC")
        title.setStyleSheet("""
            font-family: "Segoe UI", "Microsoft YaHei UI";
            font-size: 48px;
            font-weight: 800;
            color: #111827;
        """)
        title.setAlignment(Qt.AlignCenter)

        subtitle = QtWidgets.QLabel("车载诊断工具平台")
        subtitle.setStyleSheet("""
            font-family: "Microsoft YaHei UI";
            font-size: 20px;
            color: #6B7280;
            letter-spacing: 4px;
        """)
        subtitle.setAlignment(Qt.AlignCenter)

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        content_layout.addWidget(header_container)

        # Cards Grid
        cards_container = QtWidgets.QWidget()
        cards_container.setMaximumWidth(1100)
        cards_layout = QtWidgets.QGridLayout(cards_container)
        cards_layout.setSpacing(24)
        cards_layout.setContentsMargins(20, 20, 20, 20)

        actions = [
            (PageConfig.PAGE_DEVICE_DISPLAY, "设备管理", "设备连接与状态监控", "#2563EB", "rgba(37, 99, 235, 0.1)"),
            (PageConfig.PAGE_TOPOLOGY_DISPLAY, "拓扑监控", "整车网络拓扑可视化", "#059669", "rgba(5, 150, 105, 0.1)"),
            (PageConfig.PAGE_DTC_DISPLAY, "DTC诊断", "故障码读取与清除", "#DC2626", "rgba(220, 38, 38, 0.1)"),
            (PageConfig.PAGE_UPGRADE_DISPLAY, "设备升级", "固件刷写与版本管理", "#7C3AED", "rgba(124, 58, 237, 0.1)"),
            (PageConfig.PAGE_FILE_TRANSFER_DISPLAY, "文件传输", "高速文件上传下载", "#D97706", "rgba(217, 119, 6, 0.1)"),
            (PageConfig.PAGE_LOG_DOWNLOAD_DISPLAY, "日志下载", "运行日志获取与分析", "#4F46E5", "rgba(79, 70, 229, 0.1)"),
        ]

        for i, (page_text, title_text, desc_text, color, bg_color) in enumerate(actions):
            card = self._create_card(page_text, title_text, desc_text, color, bg_color)
            row = i // 3
            col = i % 3
            cards_layout.addWidget(card, row, col)

        content_layout.addWidget(cards_container)

        main_layout.addStretch()
        main_layout.addWidget(content_wrapper)
        main_layout.addStretch()

    def _create_card(self, page_text, title_text, desc_text, color, bg_color):
        parts = page_text.split(' ', 1)
        emoji = parts[0] if len(parts) > 0 else ""

        btn = QtWidgets.QPushButton()
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(320, 180)

        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 20px;
                text-align: left;
            }}
            QPushButton:hover {{
                border: 1px solid {color};
                background-color: #FFFFFF;
            }}
            QPushButton:pressed {{
                background-color: #F3F4F6;
            }}
        """)

        layout = QtWidgets.QVBoxLayout(btn)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        # Header (Icon + Title)
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setSpacing(15)

        icon_label = QtWidgets.QLabel(emoji)
        icon_label.setFixedSize(48, 48)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(f"""
            background-color: {bg_color};
            border-radius: 12px;
            font-size: 24px;
            font-family: "Segoe UI Emoji"; 
        """)

        title_label = QtWidgets.QLabel(title_text)
        title_label.setStyleSheet(f"""
            font-family: "Microsoft YaHei UI";
            font-size: 18px;
            font-weight: bold;
            color: #1F2937;
            background: transparent;
            border: none;
        """)

        header_layout.addWidget(icon_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Description
        desc_label = QtWidgets.QLabel(desc_text)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("""
            font-family: "Microsoft YaHei UI";
            font-size: 14px;
            color: #6B7280;
            background: transparent;
            border: none;
            line-height: 1.4;
        """)
        desc_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        layout.addWidget(desc_label)
        layout.addStretch()

        btn.clicked.connect(lambda: self.action_clicked.emit(page_text))

        # Add shadow effect
        shadow = QtWidgets.QGraphicsDropShadowEffect(btn)
        shadow.setBlurRadius(20)
        shadow.setColor(QtGui.QColor(0, 0, 0, 15))
        shadow.setOffset(0, 4)
        btn.setGraphicsEffect(shadow)

        return btn
