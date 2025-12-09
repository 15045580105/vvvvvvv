from PyQt5 import QtWidgets

from app.presentation.views.base_view import BaseView
from app.modules.clock_management.view.system_time_info_widget import SystemTimeInfoWidget
from app.modules.clock_management.view.gptp_status_widget import GPTPStatusWidget
from app.modules.clock_management.view.alarm_management_widget import AlarmManagementWidget


class ClockManagementWidget(BaseView):
    """时钟管理总页面：系统时间信息 + gPTP 状态 + 闹钟管理，支持滚动，主题统一。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(900, 700)
        # 将本页背景设置为白色，避免使用主窗口的灰色背景
        self.setStyleSheet("background-color: #FFFFFF;")
        self._init_ui()

    def _init_ui(self):
        # 顶层布局
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # 创建滚动区域，用于容纳三个子页面
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)

        # 滚动内容容器
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)

        # 上方：系统时间信息视图（内部自带“时钟管理”分组）
        self.system_time_widget = SystemTimeInfoWidget(parent=scroll_content)
        scroll_layout.addWidget(self.system_time_widget)

        # 中部：gPTP 状态视图（内部自带“gPTP 状态”分组）
        self.gptp_status_widget = GPTPStatusWidget()
        scroll_layout.addWidget(self.gptp_status_widget)

        # 底部：闹钟管理视图（内部有“闹钟管理”标题和 Tab 区域）
        self.alarm_management_widget = AlarmManagementWidget(parent=scroll_content)
        scroll_layout.addWidget(self.alarm_management_widget)

        # 占位伸缩，避免子控件被挤压
        scroll_layout.addStretch(1)

        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

    def refresh_all(self):
        """预留刷新入口：后续可在此调用子视图的刷新逻辑。"""
        if hasattr(self.system_time_widget, "update_local_time"):
            self.system_time_widget.update_local_time()


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    window = ClockManagementWidget()
    window.show()
    sys.exit(app.exec_())
