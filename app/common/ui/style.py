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

QLineEdit, QComboBox, QTextEdit, QSpinBox {
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

QTextEdit:focus { border: 2px solid #3B82F6; }
QDateTimeEdit {
    background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 8px; padding: 8px;
    selection-background-color: #4F46E5;
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


# 现代 UI 样式表
MODERN_STYLESHEET = """
/* === 全局 === */
QWidget {
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    font-size: 14px;
    color: #334155; /* Slate 700 */
    outline: none;
}

/* === 主容器背景 === */
QFrame#MainFrame {
    background-color: #F8FAFC; 
    border-radius: 24px; 
    border: 1px solid #CBD5E1;
}

/* === 侧边栏 === */
QFrame#SideMenu {
    background-color: #FFFFFF;
    border-top-left-radius: 24px;
    border-bottom-left-radius: 24px;
    border-right: 1px solid #E2E8F0;
}

/* === 内容区 === */
QWidget#ContentArea {
    background-color: #F8FAFC; 
    border-top-right-radius: 24px;
    border-bottom-right-radius: 24px;
}

/* === 滚动区透明 === */
QScrollArea { background: transparent; border: none; }
QWidget#ScrollContent { background: transparent; }

/* === 滚动条 === */
QScrollBar:vertical {
    border: none; background: transparent; width: 6px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #CBD5E1; min-height: 20px; border-radius: 3px;
}
QScrollBar::handle:vertical:hover { background: #94A3B8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* === 常用控件 === */
QFrame[class="card"] {
    background-color: #FFFFFF; border-radius: 16px; border: 1px solid #E2E8F0;
}
QLabel[class="h1"] { font-size: 26px; font-weight: 800; color: #0F172A; margin-bottom: 8px;}
QLabel[class="h2"] { font-size: 18px; font-weight: 700; color: #1E293B; margin-bottom: 6px;}
QLabel[class="label"] { font-size: 13px; font-weight: 600; color: #64748B; margin-bottom: 4px; }

/* 按钮 */
QPushButton { border-radius: 8px; padding: 8px 16px; font-weight: 600; }
QPushButton[class="menu-btn"] {
    background: transparent; border: none; text-align: left; 
    color: #64748B; padding: 12px 20px; border-radius: 12px; margin: 2px 10px;
}
QPushButton[class="menu-btn"]:hover { background: #F1F5F9; color: #4F46E5; }
QPushButton[class="menu-btn"]:checked { background: #EEF2FF; color: #4F46E5; font-weight: bold; }

QPushButton[class="btn-primary"] { background: #4F46E5; color: white; border: none; }
QPushButton[class="btn-primary"]:hover { background: #4338CA; }
QPushButton[class="btn-outline"] { background: white; border: 1px solid #CBD5E1; color: #475569; }
QPushButton[class="btn-outline"]:hover { background: #F8FAFC; border-color: #94A3B8; color: #1E293B; }

/* 输入类 */
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {
    background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 8px; padding: 8px;
    selection-background-color: #4F46E5;
}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDateEdit:focus { border: 2px solid #6366F1; }

/* 下拉框 */
QComboBox { border: 1px solid #CBD5E1; border-radius: 8px; padding: 6px 10px; background: white; }
QComboBox:focus { border: 2px solid #6366F1; }
QComboBox::drop-down { border: none; width: 20px; }

/* 日历 */
QCalendarWidget QWidget { alternate-background-color: #F8FAFC; }
QCalendarWidget QToolButton { color: #334155; icon-size: 20px; font-weight: bold; }
QCalendarWidget QMenu { background-color: white; }
QCalendarWidget QSpinBox { border: none; background: transparent; }
QCalendarWidget QAbstractItemView:enabled {
    font-size: 13px; color: #333; selection-background-color: #4F46E5; selection-color: white;
}

/* LCD */
QLCDNumber { border: none; color: #4F46E5; }

/* 表格 */
QTableWidget { border: none; gridline-color: #F1F5F9; background: white; border-radius: 12px;}
QHeaderView::section { background: #F8FAFC; padding: 8px; border: none; border-bottom: 2px solid #E2E8F0; font-weight: 600; color: #475569; }
QTableWidget::item:selected { background: #EEF2FF; color: #1E293B; }

/* Slider */
QSlider::groove:horizontal { border: 1px solid #E2E8F0; height: 6px; background: #E2E8F0; border-radius: 3px; }
QSlider::handle:horizontal { background: #4F46E5; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }
"""