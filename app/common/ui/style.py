"""
@FileName：style.py
@Description：主题样式
@Author：QinHao
@Time：2025/11/26 10:26
@Department：PTV_AT
"""
APP_STYLE = """
QMainWindow { background-color: #F9FAFB; }
QTreeWidget { background-color: #FFFFFF; color: #1F2937; border: none; outline: none; font-family: "Segoe UI", "Microsoft YaHei"; font-size: 9.5pt; }
QTreeWidget::item { padding: 10px 8px; border-radius: 6px; margin: 1px 0; }
QTreeWidget::item:hover { background-color: #EFF6FF; color: #1E40AF; }
QTreeWidget::item:selected { background-color: #3B82F6; color: white; font-weight: 600; }
QToolBar { background-color: #FFFFFF; border: none; border-bottom: 2px solid #E5E7EB; padding: 8px; spacing: 10px; }
QToolButton { background-color: #F9FAFB; color: #4B5563; border: 1px solid #D1D5DB; border-radius: 6px; padding: 8px 12px; font-family: "Segoe UI", "Microsoft YaHei"; font-size: 9pt; font-weight: 500; }
QToolButton:hover { background-color: #3B82F6; color: white; border: 1px solid #3B82F6; }
QToolButton:checked { background-color: #1E40AF; color: white; }
QTabWidget::pane { border: 1px solid #E5E7EB; background-color: #FFFFFF; border-radius: 8px; }
QTabBar::tab {
    background-color: #F3F4F6;
    color: #6B7280;
    padding: 10px 18px;
    margin: 4px 2px;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    font-weight: 500;
}
QTabBar::tab:selected { background-color: #3B82F6; color: white; border: 1px solid #3B82F6; font-weight: 600; }
QTabBar::close-button {
    subcontrol-position: right;
    subcontrol-origin: padding;
    right: 5px;
}
QTabBar::close-button:hover {
    background: #d3d3d3;
}
QTabBar::tab:hover:!selected { background-color: #E0E7FF; color: #3730A3; }
QStatusBar { background-color: #FFFFFF; color: #4B5563; border-top: 2px solid #E5E7EB; padding: 8px; font-family: "Segoe UI", "Microsoft YaHei"; font-weight: 500; }
QTableWidget { background-color: #FFFFFF; color: #1F2937; gridline-color: #F3F4F6; border: 1px solid #D1D5DB; border-radius: 8px; outline: none; font-family: "Segoe UI", "Microsoft YaHei"; font-size: 9pt; }
QTableWidget::item { padding: 8px 10px; border-bottom: 1px solid #F3F4F6; }
QTableWidget::item:hover { background-color: #EFF6FF; }
QTableWidget::item:selected { background-color: #DBEAFE; color: #1E40AF; font-weight: 600; }
QHeaderView::section { background-color: #F9FAFB; color: #374151; padding: 10px 8px; border: none; border-right: 1px solid #E5E7EB; border-bottom: 2px solid #D1D5DB; font-weight: 600; font-size: 9pt; }

/* 文本/输入类控件统一风格，加入 QDateTimeEdit */
QLineEdit, QComboBox, QTextEdit, QSpinBox, QDateTimeEdit {
    background-color: #FFFFFF;
    color: #1F2937;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    padding: 8px 12px;
    font-family: "Segoe UI", "Microsoft YaHei";
    font-size: 9pt;
    selection-background-color: #3B82F6;
    selection-color: white;
}

QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDateTimeEdit:focus {
    border: 2px solid #3B82F6;
}

QTextEdit:focus { border: 2px solid #3B82F6; }

/* QDateTimeEdit 下拉按钮和箭头，保持浅色扁平风格 */
QDateTimeEdit::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: right;
    width: 22px;
    border-left: 1px solid #D1D5DB;
    background-color: #F3F4F6;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}

QDateTimeEdit::down-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #4B5563;
    margin-right: 6px;
}

QGroupBox { color: #1F2937; border: 1px solid #E5E7EB; border-radius: 8px; margin-top: 12px; padding: 16px; font-family: "Segoe UI", "Microsoft YaHei"; font-weight: 600; font-size: 10pt; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 6px 12px; color: #3B82F6; background-color: #F3F4F6; border-radius: 6px; }
QProgressBar { border: 1px solid #D1D5DB; border-radius: 6px; text-align: center; padding: 2px; }
QProgressBar::chunk { background-color: #10B981; border-radius: 5px; }
QCheckBox { color: #374151; font-family: "Segoe UI", "Microsoft YaHei"; font-weight: 500; spacing: 6px; }
QListWidget { background-color: #F9FAFB; color: #1F2937; border: 1px solid #D1D5DB; border-radius: 8px; outline: none; }
QListWidget::item { padding: 10px 12px; border-radius: 6px; margin: 2px; }
QListWidget::item:hover { background-color: #EFF6FF; }
QListWidget::item:selected { background-color: #3B82F6; color: white; }
QLabel { font-size: 9pt; }
QDialog { background-color: #F9FAFB; }
"""
