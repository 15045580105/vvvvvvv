"""
@FileName：system_time_info_widget.py
@Description：
@Author：QinHao
@Time：2025/12/8 14:13
@Department：PTV_AT
"""
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt

from app.presentation.views.base_view import BaseView
from app.common.ui.widgets import ModernButton


class SystemTimeInfoWidget(BaseView):
    """时钟管理界面：统一项目主题，保留原有结构和布局。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(900, 450)
        self.local_clock = None
        self.rt1_clock = None
        self.rt2_clock = None
        self.vm1_clock = None
        self.timer = None
        self.setup_ui()

    def setup_ui(self):
        # 整体主布局：先放一个分组，再在分组内部保持原有布局结构
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # 用 QGroupBox("时钟管理") 包裹整个内容，使风格与其他模块统一
        group = QtWidgets.QGroupBox("时钟管理")
        group_layout = QtWidgets.QVBoxLayout(group)
        group_layout.setContentsMargins(12, 12, 12, 12)
        group_layout.setSpacing(12)

        # 顶部一行：左空白 + 右侧设置按钮（保持结构简单）
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setSpacing(8)

        header_layout.addStretch(1)
        settings_btn = ModernButton("设置", "#0EA5E9", "⚙️")
        header_layout.addWidget(settings_btn)

        group_layout.addLayout(header_layout)

        # 原来的上位机本地时间块
        self.local_clock = self.create_time_block("上位机本地时间", "#0EA5E9")
        group_layout.addWidget(self.local_clock)

        # 原来的下方三列布局
        bottom_layout = QtWidgets.QHBoxLayout()
        bottom_layout.setSpacing(12)

        self.rt1_clock = self.create_time_block("RT1系统时间查询", "#10B981")
        self.rt2_clock = self.create_time_block("RT2系统时间查询", "#EF4444")
        self.vm1_clock = self.create_time_block("VM1系统时间查询", "#F59E0B")

        bottom_layout.addWidget(self.rt1_clock)
        bottom_layout.addWidget(self.rt2_clock)
        bottom_layout.addWidget(self.vm1_clock)

        group_layout.addLayout(bottom_layout)

        # 将分组添加到主布局中
        main_layout.addWidget(group)

        # 启动定时器更新本地时间
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_local_time)
        self.timer.start(1000)
        self.update_local_time()

    def create_time_block(self, title, accent_color):
        """创建统一风格的时间块（浅色卡片风格，保留原结构）。"""
        container = QtWidgets.QFrame()
        container.setObjectName("timeBlock")

        # 浅色卡片样式，对齐项目主题
        container.setStyleSheet(
            f"""
            QFrame#timeBlock {{
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 10px;
                padding: 16px;
                min-height: 150px;
            }}
            QLabel {{
                color: #111827;
                background: transparent;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QLabel.title {{
                font-size: 15px;
                font-weight: 600;
                color: {accent_color};
                margin-bottom: 8px;
            }}
            QLabel.time {{
                font-size: 28px;
                font-weight: 600;
                color: #111827;
                margin: 4px 0;
                font-family: "Consolas", "Courier New", monospace;
            }}
            QLabel.date {{
                font-size: 13px;
                color: #4B5563;
                margin: 2px 0;
            }}
            QLabel.timezone {{
                font-size: 12px;
                color: {accent_color};
                margin: 2px 0;
            }}
            QLabel.relative {{
                font-size: 12px;
                color: #6B7280;
                margin-top: 6px;
            }}
        """
        )

        layout = QtWidgets.QVBoxLayout(container)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        # 标题
        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName("titleLabel")
        title_label.setProperty("class", "title")
        title_label.setAlignment(Qt.AlignCenter)

        # 时间
        time_label = QtWidgets.QLabel("--:--:--")
        time_label.setObjectName("timeLabel")
        time_label.setProperty("class", "time")
        time_label.setAlignment(Qt.AlignCenter)

        # 日期
        date_label = QtWidgets.QLabel("----年--月--日")
        date_label.setObjectName("dateLabel")
        date_label.setProperty("class", "date")
        date_label.setAlignment(Qt.AlignCenter)

        # 时区
        tz_label = QtWidgets.QLabel("时区: GMT+8")
        tz_label.setObjectName("tzLabel")
        tz_label.setProperty("class", "timezone")
        tz_label.setAlignment(Qt.AlignCenter)

        # 相对时间
        rel_label = QtWidgets.QLabel("相对时间偏差: --秒")
        rel_label.setObjectName("relLabel")
        rel_label.setProperty("class", "relative")
        rel_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(title_label)
        layout.addWidget(time_label)
        layout.addWidget(date_label)
        layout.addWidget(tz_label)
        layout.addWidget(rel_label)

        return container

    def update_local_time(self):
        """更新本地时间显示（保持原逻辑）。"""
        current = QtCore.QDateTime.currentDateTime()

        # 查找本地时间块的子控件
        time_label = self.local_clock.findChild(QtWidgets.QLabel, "timeLabel")
        date_label = self.local_clock.findChild(QtWidgets.QLabel, "dateLabel")

        if time_label and date_label:
            time_label.setText(current.toString("HH:mm:ss"))
            date_label.setText(current.toString("yyyy年MM月dd日 dddd"))


if __name__ == '__main__':
    import sys

    app = QtWidgets.QApplication(sys.argv)
    window = SystemTimeInfoWidget()
    window.show()
    sys.exit(app.exec_())