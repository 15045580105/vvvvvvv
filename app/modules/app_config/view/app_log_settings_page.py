from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QComboBox, QLineEdit,
                             QGroupBox, QGridLayout, QFileDialog, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5 import QtWidgets, QtCore

from app.common.log.operation_log_manager import OperationLogManager
from app.common.ui.widgets import ModernButton


class AppLogSettingsPage(QWidget):
    """APP Log Settings Page"""
    save_signal = pyqtSignal(dict)
    reset_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.refresh_modules()

    def init_ui(self):
        """Initialize UI"""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title_label = QLabel("APP 日志设置")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50;")
        main_layout.addWidget(title_label)

        # Export APP settings group
        export_group = self._create_group_box("导出 APP 日志", "#10B981")
        export_layout = QGridLayout()
        export_layout.setHorizontalSpacing(12)
        export_layout.setVerticalSpacing(12)

        row = 0
        # Row 0: export path selector
        export_layout.addWidget(QLabel("导出路径:"), row, 0)
        self.export_path_edit = QLineEdit()
        self.export_path_edit.setPlaceholderText("选择导出文件夹")
        self.export_path_edit.setReadOnly(True)
        export_layout.addWidget(self.export_path_edit, row, 1)
        self.export_path_btn = ModernButton("浏览", "#3B82F6", "📁")
        self.export_path_btn.clicked.connect(self.browse_export_path)
        export_layout.addWidget(self.export_path_btn, row, 2)

        row += 1
        # Row 1: module/page dropdown selector
        export_layout.addWidget(QLabel("导出模块:"), row, 0)
        self.export_module_combo = QComboBox()
        self.export_module_combo.setMinimumWidth(200)
        self.export_module_combo.setEditable(False)
        export_layout.addWidget(self.export_module_combo, row, 1, 1, 2)

        row += 1
        # Row 2: start/end datetime
        export_layout.addWidget(QLabel("开始时间:"), row, 0)

        datetime_row_layout = QHBoxLayout()
        self.export_start_datetime = QtWidgets.QDateTimeEdit(QtCore.QDateTime.currentDateTime())
        self.export_start_datetime.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.export_start_datetime.setCalendarPopup(True)
        datetime_row_layout.addWidget(self.export_start_datetime)

        datetime_row_layout.addWidget(QLabel("结束时间:"))
        self.export_end_datetime = QtWidgets.QDateTimeEdit(QtCore.QDateTime.currentDateTime())
        self.export_end_datetime.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.export_end_datetime.setCalendarPopup(True)
        datetime_row_layout.addWidget(self.export_end_datetime)

        datetime_row_layout.addStretch()
        export_layout.addLayout(datetime_row_layout, row, 1, 1, 2)

        row += 1
        # Row 3: Export Button
        self.export_start_btn = ModernButton("导出日志", "#3B82F6", "⬇")
        self.export_start_btn.clicked.connect(self.on_export_clicked)
        export_layout.addWidget(self.export_start_btn, row, 1, 1, 2, Qt.AlignRight)

        export_group.setLayout(export_layout)
        main_layout.addWidget(export_group)

        main_layout.addStretch()
        self.setLayout(main_layout)

    def showEvent(self, event):
        """Page shown event - refresh modules"""
        self.refresh_modules()
        super().showEvent(event)

    def refresh_modules(self):
        """Refresh the list of available modules from log manager"""
        current = self.export_module_combo.currentText()
        self.export_module_combo.clear()
        self.export_module_combo.addItem("所有模块")

        modules = OperationLogManager.instance().get_modules()
        self.export_module_combo.addItems(modules)

        # Restore selection if possible
        index = self.export_module_combo.findText(current)
        if index >= 0:
            self.export_module_combo.setCurrentIndex(index)
        else:
            self.export_module_combo.setCurrentIndex(0)

    def on_export_clicked(self):
        """Handle export button click"""
        path = self.export_path_edit.text()
        if not path:
            QMessageBox.warning(self, "提示", "请先选择导出路径")
            return

        module = self.export_module_combo.currentText()
        start_dt = self.export_start_datetime.dateTime().toPyDateTime()
        end_dt = self.export_end_datetime.dateTime().toPyDateTime()

        try:
            # Call manager to export
            files = OperationLogManager.instance().export_logs(module, path, start_dt, end_dt)
            if files:
                QMessageBox.information(self, "导出成功", f"已成功导出 {len(files)} 个日志文件到:\n{path}")
            else:
                QMessageBox.information(self, "提示", "没有找到符合条件的日志可导出。")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出过程中发生错误:\n{str(e)}")

    def _create_group_box(self, title, border_color):
        """Create styled GroupBox"""
        group = QGroupBox(title)
        # Use theme colors
        if border_color == "#10B981": # Green
            border_color = "#10B981"
            title_color = "#065F46"
            bg_color = "#ECFDF5"
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
                font-family: "Segoe UI", "Microsoft YaHei";
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

    def browse_export_path(self):
        path = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if path:
            self.export_path_edit.setText(path)

    def update_ui(self, settings):
        """Update UI from settings"""
        self.export_path_edit.setText(settings.get("export_path", ""))
        self.export_module_combo.setCurrentText(settings.get("export_module", "所有模块"))
        # Date times might not be stored in settings usually, but if they are:
        # self.export_start_datetime.setDateTime(...)
        pass

    def save_settings(self):
        """Save settings"""
        settings = {
            "export_path": str(self.export_path_edit.text()),
            "export_module": str(self.export_module_combo.currentText()),
            # "start_time": ...
        }
        self.save_signal.emit(settings)

    def reset_to_defaults(self):
        """Reset to defaults"""
        self.reset_signal.emit()
