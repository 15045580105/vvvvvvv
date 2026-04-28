from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLineEdit,
    QGroupBox,
    QFormLayout,
    QTextEdit,
)

from app.common.utils.license_manager import get_license_info


class LicenseInfoPage(QWidget):
    """License 信息展示页"""

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.refresh_license_info()

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        license_group = self._create_group_box("激活信息", "#3498db")
        license_form = QFormLayout()
        license_form.setSpacing(12)
        license_form.setLabelAlignment(Qt.AlignLeft)

        self.machine_id_edit = self._create_readonly_edit()
        self.status_edit = self._create_readonly_edit()
        self.expire_time_edit = self._create_readonly_edit()
        self.remaining_days_edit = self._create_readonly_edit()
        self.activation_code_edit = QTextEdit()
        self.activation_code_edit.setReadOnly(True)
        self.activation_code_edit.setMinimumHeight(140)
        self.activation_code_edit.setPlaceholderText("当前未检测到激活码")

        license_form.addRow("激活状态:", self.status_edit)
        license_form.addRow("Machine ID:", self.machine_id_edit)
        license_form.addRow("过期时间:", self.expire_time_edit)
        license_form.addRow("剩余时间:", self.remaining_days_edit)
        license_form.addRow("Activation Code:", self.activation_code_edit)
        license_group.setLayout(license_form)
        main_layout.addWidget(license_group)

        main_layout.addStretch()
        self.setLayout(main_layout)

    def _create_readonly_edit(self) -> QLineEdit:
        edit = QLineEdit()
        edit.setReadOnly(True)
        edit.setMinimumWidth(280)
        return edit

    def _create_group_box(self, title, border_color):
        group = QGroupBox(title)
        if border_color == "#3498db":
            border_color = "#3B82F6"
            title_color = "#1E40AF"
            bg_color = "#EFF6FF"
        elif border_color == "#e74c3c":
            border_color = "#EF4444"
            title_color = "#991B1B"
            bg_color = "#FEF2F2"
        elif border_color == "#9b59b6":
            border_color = "#8B5CF6"
            title_color = "#5B21B6"
            bg_color = "#F5F3FF"
        else:
            title_color = "#374151"
            bg_color = "#F9FAFB"

        group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600;
                border: 1px solid {border_color};
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 16px;
                font-family: \"Segoe UI\", \"Microsoft YaHei\";
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 4px 8px;
                color: {title_color};
                background-color: {bg_color};
                border-radius: 4px;
            }}
        """)
        return group

    def _apply_field_state_style(self, widget: QLineEdit, highlight: bool):
        if highlight:
            widget.setStyleSheet(
                "background-color: #ECFDF5; color: #047857; border: 1px solid #A7F3D0; border-radius: 6px;"
            )
        else:
            widget.setStyleSheet("")

    def refresh_license_info(self):
        info = get_license_info()
        self.status_edit.setText(info.status_text or "--")
        self.machine_id_edit.setText(info.machine_id or "--")
        self.expire_time_edit.setText(info.expire_time_text or "--")
        self.remaining_days_edit.setText(f"{info.remaining_days}天" if info.activation_code else "--")
        self.activation_code_edit.setPlainText(info.activation_code or "")

        highlight_ok = info.activated
        self._apply_field_state_style(self.status_edit, highlight_ok)
        self._apply_field_state_style(self.expire_time_edit, highlight_ok)
        self._apply_field_state_style(self.remaining_days_edit, highlight_ok)

