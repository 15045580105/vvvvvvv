"""
@FileName：style.py
@Description：主题样式
@Author：QinHao
@Time：2025/11/26 10:26
@Department：PTV_AT
"""
APP_STYLE = """
QMainWindow {
    background-color: #F9FAFB;
}

QTreeWidget {
    background-color: #FFFFFF;
    color: #1F2937;
    border: none;
    outline: none;
    font-family: "Segoe UI", "Microsoft YaHei";
    font-size: 9.5pt;
}

QTreeWidget::item {
    padding: 10px 8px;
    border-radius: 6px;
    margin: 1px 0;
}

QTreeWidget::item:hover {
    background-color: #EFF6FF;
    color: #1E40AF;
}

QTreeWidget::item:selected {
    background-color: #3B82F6;
    color: white;
    font-weight: 600;
}

QToolBar {
    background-color: #FFFFFF;
    border: none;
    border-bottom: 2px solid #E5E7EB;
    padding: 8px;
    spacing: 10px;
}

QToolButton {
    background-color: #F9FAFB;
    color: #4B5563;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    padding: 8px 12px;
    font-family: "Segoe UI", "Microsoft YaHei";
    font-size: 9pt;
    font-weight: 500;
}

QToolButton:hover {
    background-color: #3B82F6;
    color: white;
    border: 1px solid #3B82F6;
}

QToolButton:checked {
    background-color: #1E40AF;
    color: white;
}

QTabWidget::pane {
    border: 1px solid #E5E7EB;
    background-color: #FFFFFF;
    border-radius: 8px;
}

QTabBar::tab {
    background-color: #F3F4F6;
    color: #6B7280;
    padding: 12px 20px 12px 20px;
    margin: 2px 2px;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    font: 200;
}

QTabBar::tab:selected {
    background-color: #3B82F6;
    color: white;
    border: 1px solid #3B82F6;
    padding: 12px 20px 12px 20px;
    margin: 2px 2px;
    font: 400;
}

QTabBar::close-button {
    subcontrol-position: right;
    subcontrol-origin: padding;
}

QTabBar::close-button:hover {
    background: #d3d3d3;
}

QTabBar::tab:hover:!selected {
    background-color: #E0E7FF;
    color: #3730A3;
}

QStatusBar {
    background-color: #FFFFFF;
    color: #4B5563;
    border-top: 2px solid #E5E7EB;
    padding: 8px;
    font-family: "Segoe UI", "Microsoft YaHei";
    font-weight: 500;
}

QStatusBar::item {
    border: none;
}

QTableWidget {
    background-color: #FFFFFF;
    color: #1F2937;
    gridline-color: #F3F4F6;
    border: 1px solid #D1D5DB;
    border-radius: 8px;
    outline: none;
    font-family: "Segoe UI", "Microsoft YaHei";
    font-size: 9pt;
}

QTableWidget::item {
    padding: 8px 10px;
    border-bottom: 1px solid #F3F4F6;
}

QTableWidget::item:hover {
    background-color: #EFF6FF;
}

QTableWidget::item:selected {
    background-color: #DBEAFE;
    color: #1E40AF;
    font-weight: 600;
}

QHeaderView::section {
    background-color: #F9FAFB;
    color: #374151;
    padding: 10px 8px;
    border: none;
    border-right: 1px solid #E5E7EB;
    border-bottom: 2px solid #D1D5DB;
    font-weight: 600;
    font-size: 9pt;
}

QPushButton {
    background-color: #3B82F6;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 6px;
    font-family: "Segoe UI", "Microsoft YaHei";
    font-size: 9pt;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #2563EB;
}

QPushButton:pressed {
    background-color: #1D4ED8;
}

QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QDateEdit, QTimeEdit {
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
QDoubleSpinBox:focus,
QTextEdit:focus,
QPlainTextEdit:focus,
QDateTimeEdit:focus,
QDateEdit:focus,
QTimeEdit:focus {
    border: 2px solid #3B82F6;
}

QComboBox::drop-down, QDateTimeEdit::drop-down, QDateEdit::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left-width: 0px;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background: transparent;
}

QComboBox::drop-down:hover, QDateTimeEdit::drop-down:hover, QDateEdit::drop-down:hover {
    background-color: #EFF6FF;
}

QComboBox::down-arrow {
    image: url(app/resources/images/arrow_down.svg);
    width: 12px;
    height: 12px;
}

QSpinBox::up-button, QDoubleSpinBox::up-button, QDateTimeEdit::up-button, QDateEdit::up-button, QTimeEdit::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    border: none;
    background: transparent;
    margin-top: 1px;
    margin-right: 1px;
    border-top-right-radius: 5px;
}

QSpinBox::down-button, QDoubleSpinBox::down-button, QDateTimeEdit::down-button, QDateEdit::down-button, QTimeEdit::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    border: none;
    background: transparent;
    margin-bottom: 1px;
    margin-right: 1px;
    border-bottom-right-radius: 5px;
}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QDateTimeEdit::up-arrow, QDateEdit::up-arrow, QTimeEdit::up-arrow {
    image: url(app/resources/images/arrow_up.svg);
    width: 10px;
    height: 10px;
}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QDateTimeEdit::down-arrow, QDateEdit::down-arrow, QTimeEdit::down-arrow {
    image: url(app/resources/images/arrow_down.svg);
    width: 10px;
    height: 10px;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QDateTimeEdit::up-button:hover, QDateEdit::up-button:hover, QTimeEdit::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover, QDateTimeEdit::down-button:hover, QDateEdit::down-button:hover, QTimeEdit::down-button:hover {
    background-color: #EFF6FF;
}

QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed, QDateTimeEdit::up-button:pressed, QDateEdit::up-button:pressed, QTimeEdit::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed, QDateTimeEdit::down-button:pressed, QDateEdit::down-button:pressed, QTimeEdit::down-button:pressed {
    background-color: #DBEAFE;
}


QGroupBox {
    color: #1F2937;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    margin-top: 12px;
    padding: 16px;
    font-family: "Segoe UI", "Microsoft YaHei";
    font-weight: 600;
    font-size: 10pt;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 6px 12px;
    color: #3B82F6;
    background-color: #F3F4F6;
    border-radius: 6px;
}

QProgressBar {
    border: 1px solid #dee2e6;
    border-radius: 4px;
    text-align: center;
}

QProgressBar::chunk {
    background-color: #007bff;
}

QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollBar:vertical {
    width: 14px;
    background: #f8f9fa;
    border-radius: 7px;
}

QScrollBar::handle:vertical {
    background: #dee2e6;
    min-height: 20px;
    border-radius: 7px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background: #adb5bd;
}

QScrollBar:horizontal {
    height: 14px;
    background: #f8f9fa;
    border-radius: 7px;
}

QScrollBar::handle:horizontal {
    background: #dee2e6;
    min-width: 20px;
    border-radius: 7px;
    margin: 2px;
}

QScrollBar::handle:horizontal:hover {
    background: #adb5bd;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    border: none;
    background: none;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}

QSlider::groove:horizontal {
    height: 6px;
    background: #dee2e6;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #007bff;
    width: 16px;
    height: 16px;
    border-radius: 8px;
    margin: -5px 0;
}

QSlider::groove:vertical {
    width: 6px;
    background: #dee2e6;
    border-radius: 3px;
}

QSlider::handle:vertical {
    background: #007bff;
    height: 16px;
    width: 16px;
    border-radius: 8px;
    margin: 0 -5px;
}

QCheckBox, QRadioButton {
    color: #374151;
    font-family: "Segoe UI", "Microsoft YaHei";
    font-weight: 500;
    spacing: 6px;
}

QListWidget {
    background-color: #F9FAFB;
    color: #1F2937;
    border: 1px solid #D1D5DB;
    border-radius: 8px;
    outline: none;
}

QListWidget::item {
    padding: 10px 12px;
    border-radius: 6px;
    margin: 2px;
}

QListWidget::item:hover {
    background-color: #EFF6FF;
}

QListWidget::item:selected {
    background-color: #3B82F6;
    color: white;
}

QLabel {
    font-size: 9pt;
}

QDialog {
    background-color: #F9FAFB;
}

QMenu {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 24px;
    border-radius: 4px;
    color: #1F2937;
}

QMenu::item:selected {
    background-color: #3B82F6;
    color: white;
}

QMenuBar {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E5E7EB;
}

QMenuBar::item {
    padding: 8px 12px;
    background: transparent;
    color: #1F2937;
}

QMenuBar::item:selected {
    background-color: #EFF6FF;
    color: #1E40AF;
}

QToolTip {
    background-color: #1F2937;
    color: white;
    border: 1px solid #1F2937;
    border-radius: 4px;
    padding: 4px;
    opacity: 230;
}

QSplitter::handle {
    background-color: #E5E7EB;
}

QSplitter::handle:hover {
    background-color: #3B82F6;
}

QCalendarWidget QToolButton {
    color: #1F2937;
}

QCalendarWidget QMenu {
    background-color: #FFFFFF;
}

QCalendarWidget QSpinBox {
    background-color: #FFFFFF;
    selection-background-color: #3B82F6;
}

QCalendarWidget QWidget#qt_calendar_navigationbar {
    background-color: #F9FAFB;
    border-bottom: 1px solid #E5E7EB;
}

QCalendarWidget QAbstractItemView:enabled {
    background-color: #FFFFFF;
    color: #1F2937;
    selection-background-color: #3B82F6;
    selection-color: white;
}

QTabWidget {
    background-color: transparent;
}

QComboBox QAbstractItemView {
    border: 1px solid #D1D5DB;
    selection-background-color: #3B82F6;
    selection-color: white;
    background-color: #FFFFFF;
    outline: none;
}

QTableCornerButton::section {
    background-color: #F9FAFB;
    border: 1px solid #E5E7EB;
    border-radius: 0px;
}
"""