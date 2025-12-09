from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QGroupBox,
    QHBoxLayout,  # 修复按钮居中布局错误
)

from app.common.ui.widgets import TableButton


class AlarmManagementWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(900, 600)
        self.setup_ui()

    def setup_ui(self):
        # 主布局（外层沿用全局留白，与其他 section 一致）
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # 使用 GroupBox 统一呈现“闹钟管理”区域
        group = QGroupBox("闹钟管理")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(12, 12, 12, 12)
        group_layout.setSpacing(12)

        # Tab 区域
        tab_widget = QTabWidget()
        tab_widget.setObjectName("alarmTabWidget")
        tab_bar = tab_widget.tabBar()
        tab_bar.setExpanding(False)
        tab_bar.setStyleSheet(
            "QTabBar::tab { min-width: 170px; padding: 10px 24px; }"
        )

        tab_widget.addTab(self.create_relative_alarm_tab(), "相对时间预约闹钟")
        tab_widget.addTab(self.create_absolute_alarm_tab(), "绝对时间预约闹钟")
        tab_widget.addTab(self.create_rtc_alarm_tab(), "唤醒时刻RTC闹钟")

        group_layout.addWidget(tab_widget)
        main_layout.addWidget(group)

    def create_relative_alarm_tab(self):
        """创建相对时间预约闹钟Tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        table = self.create_alarm_table("闹钟剩余时间")
        layout.addWidget(table)

        # 添加示例数据
        self.add_table_row(table, "1001", "系统监控", "19分36秒", "未过期")
        self.add_table_row(table, "1002", "数据备份", "1小时43分", "已过期")

        return tab

    def create_absolute_alarm_tab(self):
        """创建绝对时间预约闹钟Tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        table = self.create_alarm_table("闹钟到期时间")
        layout.addWidget(table)

        # 添加示例数据
        self.add_table_row(table, "2001", "系统更新", "2023-12-25 08:00", "未过期")
        self.add_table_row(table, "2002", "日志清理", "2023-12-31 23:50", "已过期")

        return tab

    def create_rtc_alarm_tab(self):
        """创建唤醒时刻RTC闹钟Tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        table = self.create_alarm_table("闹钟到期时间")
        layout.addWidget(table)

        # 添加示例数据
        self.add_table_row(table, "WC001", "主控器", "2023-12-15 08:00", "未过期")
        self.add_table_row(table, "WC002", "备用控制器", "2023-11-30 06:30", "已过期")

        return tab

    def create_alarm_table(self, time_column_title):
        """创建闹钟表格"""
        table = QTableWidget()
        table.setObjectName("alarmTable")

        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(
            ["APPID", "应用名称", time_column_title, "闹钟状态", "操作"]
        )

        # 表格样式沿用系统主题，仅额外指定居中
        base_style = table.styleSheet()
        table.setStyleSheet(base_style + "\nQTableWidget::item { text-align: center; }\n")

        # 设置表格属性
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        # 设置统一行高
        table.verticalHeader().setDefaultSectionSize(50)

        return table

    def add_table_row(self, table, appid, app_name, time_info, status):
        """添加一行数据到表格，所有文本居中对齐"""
        row = table.rowCount()
        table.insertRow(row)

        # 普通文本列居中
        item_appid = QTableWidgetItem(appid)
        item_appid.setTextAlignment(Qt.AlignCenter)
        table.setItem(row, 0, item_appid)

        item_name = QTableWidgetItem(app_name)
        item_name.setTextAlignment(Qt.AlignCenter)
        table.setItem(row, 1, item_name)

        item_time = QTableWidgetItem(time_info)
        item_time.setTextAlignment(Qt.AlignCenter)
        table.setItem(row, 2, item_time)

        # 状态列：颜色 + 居中
        status_item = QTableWidgetItem(status)
        status_item.setTextAlignment(Qt.AlignCenter)
        if status == "已过期":
            status_item.setForeground(Qt.red)
        else:
            status_item.setForeground(Qt.darkGreen)
        table.setItem(row, 3, status_item)

        # 操作列：按钮直接居中，无多余色块
        edit_btn = TableButton("编辑")
        edit_btn.setStyleSheet(edit_btn.styleSheet() + "\nbackground: transparent; border: none;")
        table.setCellWidget(row, 4, edit_btn)


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    window = AlarmManagementWidget()
    window.show()
    sys.exit(app.exec_())
