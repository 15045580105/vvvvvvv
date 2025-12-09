from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QGroupBox,
)


class GPTPStatusWidget(QWidget):
    def __init__(self, parent=None):
        # 支持作为子组件嵌入到 ClockManagementWidget 中
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        # 顶层：一个 QGroupBox 包裹整个 gPTP 状态区域，保持与系统主题统一
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(12)

        group = QGroupBox("gPTP 状态")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(12, 12, 12, 12)
        group_layout.setSpacing(12)

        # 顶部标题行（右侧预留设置/刷新按钮，当前仅占位可扩展）
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        top_bar.addStretch(1)
        group_layout.addLayout(top_bar)

        # 第一行：角色（左对齐）
        role_card = self.create_simple_card_left("角色", "Master", "#10B981")
        group_layout.addWidget(role_card)

        # 第二行：同步状态（左对齐）
        sync_card = self.create_simple_card_left("同步状态", "B同步", "#3B82F6")
        group_layout.addWidget(sync_card)

        # 第三行：时间偏移统计
        offset_card = self.create_offset_card()
        group_layout.addWidget(offset_card)

        # 第四行：gPTP时间戳
        gptp_card = self.create_gptp_card()
        group_layout.addWidget(gptp_card)

        # 第五行：时钟拓扑视图
        topology_card = self.create_topology_card()
        group_layout.addWidget(topology_card)

        outer_layout.addWidget(group)

    def create_simple_card_left(self, title, value, accent_color):
        """创建左对齐的简单信息卡片（浅色卡片风格）。"""
        card = QFrame()
        card.setObjectName("simpleCard")
        card.setStyleSheet(
            f"""
            QFrame#simpleCard {{
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 10px;
                padding: 12px 16px;
                min-height: 56px;
            }}
            QLabel {{
                background: transparent;
                color: #111827;
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
                font-size: 10pt;
            }}
            QLabel.cardTitle {{
                color: #6B7280;
            }}
            QLabel.cardValue {{
                font-size: 18px;
                font-weight: 600;
                color: {accent_color};
                font-family: 'Consolas', 'Courier New', monospace;
            }}
        """
        )

        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        title_label = QLabel(f"{title}:")
        title_label.setObjectName("titleLabel")
        title_label.setProperty("class", "cardTitle")

        value_label = QLabel(value)
        value_label.setObjectName("valueLabel")
        value_label.setProperty("class", "cardValue")

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addStretch(1)  # 将剩余空间推到右侧，保持左对齐效果

        return card

    def create_offset_card(self):
        """创建时间偏移统计卡片（浅色统计卡片）。"""
        card = QFrame()
        card.setObjectName("offsetCard")
        card.setStyleSheet(
            """
            QFrame#offsetCard {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 10px;
                padding: 16px 18px;
                min-height: 200px;
            }
            QLabel {
                background: transparent;
                color: #111827;
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
                font-size: 10pt;
            }
            QLabel.sectionTitle {
                font-size: 11pt;
                font-weight: 600;
                color: #DC2626;
                margin-bottom: 8px;
            }
            QLabel.currentOffset {
                font-size: 20px;
                font-weight: 600;
                color: #D97706;
                margin: 8px 0 12px 0;
                font-family: 'Consolas', 'Courier New', monospace;
            }
            QLabel.statLabel {
                color: #6B7280;
            }
            QLabel.statValue {
                color: #111827;
                font-weight: 500;
                font-family: 'Consolas', 'Courier New', monospace;
            }
            QLabel.recentTitle {
                font-size: 9pt;
                color: #6B7280;
                margin-top: 10px;
                margin-bottom: 4px;
            }
            QLabel.recentValues {
                font-size: 9pt;
                color: #4B5563;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """
        )

        layout = QVBoxLayout(card)
        layout.setSpacing(6)

        # 标题
        title = QLabel("时间偏移统计")
        title.setObjectName("offsetTitle")
        title.setProperty("class", "sectionTitle")
        layout.addWidget(title)

        # 当前偏移
        current = QLabel("当前偏移: +12.3μs")
        current.setObjectName("currentOffsetLabel")
        current.setProperty("class", "currentOffset")
        current.setAlignment(Qt.AlignCenter)
        layout.addWidget(current)

        # 统计数据
        stats = [
            ("偏移量最大值", "+25.6μs"),
            ("偏移量最小值", "-12.5μs"),
            ("偏移量平均值", "+5.2μs"),
        ]

        for label_text, value_text in stats:
            row = QHBoxLayout()
            row.setSpacing(4)

            label = QLabel(f"{label_text}:")
            label.setProperty("class", "statLabel")

            value = QLabel(value_text)
            value.setProperty("class", "statValue")

            row.addWidget(label)
            row.addStretch(1)
            row.addWidget(value)
            layout.addLayout(row)

        # 最近10次偏移
        recent_title = QLabel("最近10次偏移:")
        recent_title.setProperty("class", "recentTitle")
        layout.addWidget(recent_title)

        recent_vals = QLabel(
            "+12.3, -5.7, +8.2, +3.4, -2.1, +7.8, -1.5, +9.6, +4.3, -0.8μs"
        )
        recent_vals.setProperty("class", "recentValues")
        recent_vals.setWordWrap(True)
        layout.addWidget(recent_vals)

        return card

    def create_gptp_card(self):
        """创建 gPTP 时间戳卡片（浅色卡片）。"""
        card = QFrame()
        card.setObjectName("gptpCard")
        card.setStyleSheet(
            """
            QFrame#gptpCard {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 10px;
                padding: 12px 16px;
                min-height: 72px;
            }
            QLabel {
                background: transparent;
                color: #111827;
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
                font-size: 10pt;
            }
            QLabel.cardTitle {
                color: #6B7280;
            }
            QLabel.timestamp {
                font-size: 14px;
                font-weight: 600;
                color: #6D28D9;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """
        )

        layout = QVBoxLayout(card)
        layout.setSpacing(4)

        title = QLabel("gPTP时间戳")
        title.setProperty("class", "cardTitle")

        timestamp = QLabel("1234567895,987654321 ns")
        timestamp.setProperty("class", "timestamp")
        timestamp.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(timestamp)

        return card

    def create_topology_card(self):
        """创建时钟拓扑视图卡片（浅色占位卡片）。"""
        card = QFrame()
        card.setObjectName("topologyCard")
        card.setStyleSheet(
            """
            QFrame#topologyCard {
                background-color: #FFFFFF;
                border: 1px dashed #E5E7EB;
                border-radius: 10px;
                padding: 20px;
                min-height: 140px;
            }
            QLabel {
                background: transparent;
                color: #6B7280;
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
                font-size: 10pt;
            }
            QLabel.placeholderTitle {
                font-size: 11pt;
                font-weight: 600;
                color: #4B5563;
            }
            QLabel.placeholderText {
                font-size: 9pt;
                color: #9CA3AF;
                font-style: italic;
            }
        """
        )

        layout = QVBoxLayout(card)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("时钟拓扑视图")
        title.setProperty("class", "placeholderTitle")
        title.setAlignment(Qt.AlignCenter)

        placeholder = QLabel("拓扑图显示区域\n(预留接口)")
        placeholder.setProperty("class", "placeholderText")
        placeholder.setAlignment(Qt.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(placeholder)

        return card


if __name__ == '__main__':
    import sys

    app = QApplication(sys.argv)
    # 注意：这里不再设置深色全局样式，主程序中会统一设置 APP_STYLE
    window = GPTPStatusWidget()
    window.show()
    sys.exit(app.exec_())