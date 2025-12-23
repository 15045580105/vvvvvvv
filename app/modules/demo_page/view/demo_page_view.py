# -*- coding: utf-8 -*-
"""
纯 QWidget 版本的 PyQt5 全控件样式展示 Demo
移除了 QMainWindow 的菜单栏、工具栏、状态栏等部件
"""

import sys

from PyQt5.QtCore import Qt, QTimer, QDateTime, QDate, QTime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QGroupBox, QPushButton, QCheckBox, QRadioButton, QLabel, QLineEdit,
    QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QSlider, QDial,
    QProgressBar, QComboBox, QFontComboBox, QListWidget, QTreeWidget,
    QTableWidget, QTableWidgetItem, QDateEdit, QTimeEdit, QDateTimeEdit,
    QCalendarWidget, QScrollArea, QSplitter, QFrame, QTabWidget, QButtonGroup,
    QLCDNumber, QMessageBox, QInputDialog, QColorDialog, QFontDialog, QWizard,
    QWizardPage, QFileDialog, QScrollBar, QSizeGrip, QTreeWidgetItem
)

from app.common.ui.style import MODERN_STYLESHEET


class ControlGalleryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PyQt5 全控件样式展示 - QWidget版本")
        self.setGeometry(100, 100, 1200, 800)

        # 创建主布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)

        # 创建标题标签
        title_label = QLabel("PyQt5 全控件样式展示")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #007bff;")
        title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(title_label)

        # 创建标签页控件
        self.create_tab_widget()

        # 应用样式
        self.apply_custom_styles()

        # 启动定时器更新动态控件
        self.start_animation_timer()

    def create_tab_widget(self):
        """创建标签页控件"""
        self.tab_widget = QTabWidget()
        self.main_layout.addWidget(self.tab_widget)

        # 添加各个标签页
        self.tab_widget.addTab(self.create_basic_controls_tab(), "基础控件")
        self.tab_widget.addTab(self.create_buttons_tab(), "按钮类")
        self.tab_widget.addTab(self.create_input_controls_tab(), "输入控件")
        self.tab_widget.addTab(self.create_date_time_tab(), "日期时间")
        self.tab_widget.addTab(self.create_list_views_tab(), "列表视图")
        self.tab_widget.addTab(self.create_containers_tab(), "容器控件")
        self.tab_widget.addTab(self.create_progress_tab(), "进度与状态")
        self.tab_widget.addTab(self.create_dialogs_tab(), "对话框示例")
        self.tab_widget.addTab(self.create_advanced_controls_tab(), "高级控件")

    def create_basic_controls_tab(self):
        """基础控件标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 创建网格布局
        grid = QGridLayout()
        grid.setSpacing(15)

        # 标签控件
        group_label = QGroupBox("标签控件")
        label_layout = QVBoxLayout()
        label1 = QLabel("普通标签文本")
        label2 = QLabel("<b>粗体标签</b>")
        label3 = QLabel("<i>斜体标签</i>")
        label4 = QLabel("<font color='red'>彩色标签</font>")
        label5 = QLabel("<font color='#007bff'>蓝色标签 (Bootstrap主色)</font>")
        label_layout.addWidget(label1)
        label_layout.addWidget(label2)
        label_layout.addWidget(label3)
        label_layout.addWidget(label4)
        label_layout.addWidget(label5)
        group_label.setLayout(label_layout)
        grid.addWidget(group_label, 0, 0)

        # 复选框控件
        group_checkbox = QGroupBox("复选框控件")
        checkbox_layout = QVBoxLayout()
        self.checkbox1 = QCheckBox("复选框 1")
        self.checkbox2 = QCheckBox("复选框 2 (已选中)")
        self.checkbox2.setChecked(True)
        self.checkbox3 = QCheckBox("复选框 3 (三态)")
        self.checkbox3.setTristate(True)
        self.checkbox3.setCheckState(Qt.PartiallyChecked)
        self.checkbox4 = QCheckBox("复选框 4 (禁用)")
        self.checkbox4.setEnabled(False)
        self.checkbox1.stateChanged.connect(self.on_checkbox_changed)
        self.checkbox2.stateChanged.connect(self.on_checkbox_changed)
        self.checkbox3.stateChanged.connect(self.on_checkbox_changed)
        checkbox_layout.addWidget(self.checkbox1)
        checkbox_layout.addWidget(self.checkbox2)
        checkbox_layout.addWidget(self.checkbox3)
        checkbox_layout.addWidget(self.checkbox4)
        group_checkbox.setLayout(checkbox_layout)
        grid.addWidget(group_checkbox, 0, 1)

        # 单选按钮
        group_radio = QGroupBox("单选按钮")
        radio_layout = QVBoxLayout()
        self.radio_group = QButtonGroup(self)
        radio1 = QRadioButton("单选按钮 1")
        radio2 = QRadioButton("单选按钮 2 (默认)")
        radio3 = QRadioButton("单选按钮 3")
        radio2.setChecked(True)
        radio4 = QRadioButton("单选按钮 4 (禁用)")
        radio4.setEnabled(False)
        self.radio_group.addButton(radio1)
        self.radio_group.addButton(radio2)
        self.radio_group.addButton(radio3)
        self.radio_group.addButton(radio4)
        radio_layout.addWidget(radio1)
        radio_layout.addWidget(radio2)
        radio_layout.addWidget(radio3)
        radio_layout.addWidget(radio4)
        group_radio.setLayout(radio_layout)
        grid.addWidget(group_radio, 0, 2)

        # 行编辑器
        group_lineedit = QGroupBox("行编辑器")
        lineedit_layout = QFormLayout()
        line_edit1 = QLineEdit("普通文本")
        line_edit2 = QLineEdit()
        line_edit2.setPlaceholderText("占位符文本")
        line_edit3 = QLineEdit("密码模式")
        line_edit3.setEchoMode(QLineEdit.Password)
        line_edit4 = QLineEdit("只读文本")
        line_edit4.setReadOnly(True)
        line_edit5 = QLineEdit("禁用文本")
        line_edit5.setEnabled(False)
        combo_box = QComboBox()
        combo_box.addItems(["选项 1", "选项 2", "选项 3", "选项 4"])
        combo_box.setEditable(True)
        lineedit_layout.addRow("普通:", line_edit1)
        lineedit_layout.addRow("占位符:", line_edit2)
        lineedit_layout.addRow("密码:", line_edit3)
        lineedit_layout.addRow("只读:", line_edit4)
        lineedit_layout.addRow("禁用:", line_edit5)
        lineedit_layout.addRow("可编辑组合框:", combo_box)
        group_lineedit.setLayout(lineedit_layout)
        grid.addWidget(group_lineedit, 1, 0, 1, 2)

        # 字体组合框
        group_font = QGroupBox("字体选择")
        font_layout = QVBoxLayout()
        font_combo = QFontComboBox()
        font_combo.setCurrentText("Segoe UI")  # Windows 现代字体
        font_combo.currentFontChanged.connect(self.on_font_changed)
        font_layout.addWidget(font_combo)
        group_font.setLayout(font_layout)
        grid.addWidget(group_font, 1, 2)

        layout.addLayout(grid)
        return widget

    def create_buttons_tab(self):
        """按钮类控件标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 创建网格布局
        grid = QGridLayout()
        grid.setSpacing(15)

        # 普通按钮
        group_push = QGroupBox("普通按钮")
        push_layout = QVBoxLayout()
        btn1 = QPushButton("普通按钮")
        btn2 = QPushButton("主要操作按钮")
        btn3 = QPushButton("禁用按钮")
        btn4 = QPushButton("危险操作按钮")
        btn1.clicked.connect(self.on_button_clicked)
        btn2.clicked.connect(self.on_button_clicked)
        btn3.clicked.connect(self.on_button_clicked)
        btn4.clicked.connect(self.on_button_clicked)
        btn3.setEnabled(False)
        btn2.setStyleSheet("QPushButton { background-color: #007bff; color: white; border: none; padding: 8px 16px; }")
        btn4.setStyleSheet("QPushButton { background-color: #dc3545; color: white; border: none; padding: 8px 16px; }")
        push_layout.addWidget(btn1)
        push_layout.addWidget(btn2)
        push_layout.addWidget(btn3)
        push_layout.addWidget(btn4)
        group_push.setLayout(push_layout)
        grid.addWidget(group_push, 0, 0)

        # 切换按钮
        group_toggle = QGroupBox("切换按钮")
        toggle_layout = QVBoxLayout()
        toggle_btn1 = QPushButton("切换按钮 1")
        toggle_btn1.setCheckable(True)
        toggle_btn2 = QPushButton("切换按钮 2")
        toggle_btn2.setCheckable(True)
        toggle_btn2.setChecked(True)
        toggle_btn3 = QPushButton("切换按钮 3 (禁用)")
        toggle_btn3.setCheckable(True)
        toggle_btn3.setEnabled(False)
        toggle_layout.addWidget(toggle_btn1)
        toggle_layout.addWidget(toggle_btn2)
        toggle_layout.addWidget(toggle_btn3)
        group_toggle.setLayout(toggle_layout)
        grid.addWidget(group_toggle, 0, 1)

        # 按钮组
        group_btn_group = QGroupBox("按钮组 (互斥)")
        btn_group_layout = QVBoxLayout()
        btn_group = QButtonGroup(self)
        btn_group.setExclusive(True)
        for i in range(1, 5):
            btn = QPushButton(f"选项 {i}")
            btn.setCheckable(True)
            btn_group.addButton(btn)
            btn_group_layout.addWidget(btn)
        btn_group.buttons()[0].setChecked(True)
        group_btn_group.setLayout(btn_group_layout)
        grid.addWidget(group_btn_group, 0, 2)

        # 各种样式按钮
        group_styles = QGroupBox("不同样式按钮 (Bootstrap风格)")
        styles_grid = QGridLayout()
        styles = ["default", "primary", "success", "info", "warning", "danger", "link"]
        colors = ["#6c757d", "#007bff", "#28a745", "#17a2b8", "#ffc107", "#dc3545", "transparent"]
        for i, (style, color) in enumerate(zip(styles, colors)):
            btn = QPushButton(f"{style.capitalize()}")
            if style == "link":
                btn.setStyleSheet(
                    "QPushButton { color: #007bff; text-decoration: underline; border: none; padding: 8px 16px; }")
            else:
                text_color = "black" if style == "warning" else "white"
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {color}; color: {text_color}; border: none; padding: 8px 16px; border-radius: 4px; }} QPushButton:hover {{ background-color: #0056b3; }}")
            btn.clicked.connect(self.on_button_clicked)
            styles_grid.addWidget(btn, i // 2, i % 2)
        group_styles.setLayout(styles_grid)
        grid.addWidget(group_styles, 1, 0, 1, 2)

        # 不同尺寸的按钮
        group_sizes = QGroupBox("不同尺寸按钮")
        sizes_layout = QVBoxLayout()
        btn_large = QPushButton("大按钮")
        btn_large.setStyleSheet("QPushButton { padding: 12px 24px; font-size: 16px; }")
        btn_small = QPushButton("小按钮")
        btn_small.setStyleSheet("QPushButton { padding: 4px 8px; font-size: 12px; }")
        btn_default = QPushButton("默认尺寸")
        sizes_layout.addWidget(btn_large)
        sizes_layout.addWidget(btn_default)
        sizes_layout.addWidget(btn_small)
        group_sizes.setLayout(sizes_layout)
        grid.addWidget(group_sizes, 1, 2)

        layout.addLayout(grid)
        return widget

    def create_input_controls_tab(self):
        """输入控件标签页"""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # 左侧：数字输入
        left_panel = QVBoxLayout()

        # 整数旋转框
        group_spin = QGroupBox("数字旋转框")
        spin_layout = QFormLayout()
        spin_int = QSpinBox()
        spin_int.setRange(0, 100)
        spin_int.setValue(50)
        spin_int.setPrefix("值: ")
        spin_int.setSuffix(" 单位")
        spin_int.valueChanged.connect(self.on_spin_changed)
        spin_double = QDoubleSpinBox()
        spin_double.setRange(0, 1)
        spin_double.setSingleStep(0.01)
        spin_double.setValue(0.5)
        spin_double.setDecimals(3)
        spin_layout.addRow("整数:", spin_int)
        spin_layout.addRow("浮点数:", spin_double)
        group_spin.setLayout(spin_layout)
        left_panel.addWidget(group_spin)

        # 滑块
        group_slider = QGroupBox("滑块控件")
        slider_layout = QVBoxLayout()
        self.h_slider = QSlider(Qt.Horizontal)
        self.h_slider.setRange(0, 100)
        self.h_slider.setValue(50)
        self.h_slider.setTickPosition(QSlider.TicksBelow)
        self.h_slider.setTickInterval(10)
        self.h_slider.valueChanged.connect(self.on_slider_changed)
        self.v_slider = QSlider(Qt.Vertical)
        self.v_slider.setRange(0, 100)
        self.v_slider.setValue(50)
        self.v_slider.setTickPosition(QSlider.TicksBothSides)
        self.v_slider.valueChanged.connect(self.on_slider_changed)
        slider_h_layout = QHBoxLayout()
        slider_h_layout.addWidget(self.v_slider)
        slider_h_layout.addWidget(self.h_slider)
        slider_layout.addLayout(slider_h_layout)
        group_slider.setLayout(slider_layout)
        left_panel.addWidget(group_slider)

        # 转盘
        group_dial = QGroupBox("转盘控件")
        dial_layout = QVBoxLayout()
        self.dial = QDial()
        self.dial.setRange(0, 100)
        self.dial.setValue(50)
        self.dial.setNotchesVisible(True)
        self.dial.valueChanged.connect(self.on_dial_changed)
        dial_layout.addWidget(self.dial, alignment=Qt.AlignCenter)
        group_dial.setLayout(dial_layout)
        left_panel.addWidget(group_dial)

        # 进度条控制
        group_progress_control = QGroupBox("进度条控制")
        progress_layout = QVBoxLayout()
        self.control_progress = QProgressBar()
        self.control_progress.setRange(0, 100)
        self.control_progress.setValue(0)
        btn_increase = QPushButton("增加进度")
        btn_increase.clicked.connect(self.increase_progress)
        progress_layout.addWidget(self.control_progress)
        progress_layout.addWidget(btn_increase)
        group_progress_control.setLayout(progress_layout)
        left_panel.addWidget(group_progress_control)

        left_panel.addStretch()

        # 右侧：文本输入
        right_panel = QVBoxLayout()

        # 多行文本编辑器
        group_text = QGroupBox("富文本编辑器 QTextEdit")
        text_layout = QVBoxLayout()
        self.text_edit = QTextEdit()
        self.text_edit.setHtml("""
            <h3>富文本编辑器示例</h3>
            <p>支持<b>粗体</b>、<i>斜体</i>、<u>下划线</u>等格式</p>
            <ul>
                <li>项目符号 1</li>
                <li>项目符号 2</li>
            </ul>
            <ol>
                <li>编号列表 1</li>
                <li>编号列表 2</li>
            </ol>
            <p style="color: red;">彩色文字</p>
        """)
        self.text_edit.textChanged.connect(self.on_text_changed)
        text_layout.addWidget(self.text_edit)
        group_text.setLayout(text_layout)
        right_panel.addWidget(group_text)

        # 纯文本编辑器
        group_plain = QGroupBox("纯文本编辑器 QPlainTextEdit")
        plain_layout = QVBoxLayout()
        self.plain_text = QPlainTextEdit()
        self.plain_text.setPlaceholderText("这是 QPlainTextEdit 控件，用于纯文本编辑...\n适合代码编辑和大文本处理")
        sample_code = """def hello_world():
    print("Hello, World!")
    return True"""
        self.plain_text.setPlainText(sample_code)
        plain_layout.addWidget(self.plain_text)
        group_plain.setLayout(plain_layout)
        right_panel.addWidget(group_plain)

        # LCD数字显示
        group_lcd = QGroupBox("LCD 数字显示")
        lcd_layout = QGridLayout()
        lcd1 = QLCDNumber()
        lcd1.setDigitCount(8)
        lcd1.display("12:34:56")
        lcd2 = QLCDNumber()
        lcd2.setDigitCount(5)
        lcd2.display("99.99")
        lcd3 = QLCDNumber()
        lcd3.setDigitCount(10)
        lcd3.display(1234567890)
        lcd1.setStyleSheet("QLCDNumber { color: #007bff; }")
        lcd2.setStyleSheet("QLCDNumber { color: #28a745; }")
        lcd3.setStyleSheet("QLCDNumber { color: #dc3545; }")
        lcd_layout.addWidget(lcd1, 0, 0)
        lcd_layout.addWidget(lcd2, 0, 1)
        lcd_layout.addWidget(lcd3, 1, 0, 1, 2)
        group_lcd.setLayout(lcd_layout)
        right_panel.addWidget(group_lcd)

        # 文本显示标签
        self.input_status_label = QLabel("输入状态: 等待输入...")
        self.input_status_label.setStyleSheet(
            "padding: 8px; background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px;")
        right_panel.addWidget(self.input_status_label)

        right_panel.addStretch()

        # 添加到主布局
        layout.addLayout(left_panel, stretch=1)
        layout.addLayout(right_panel, stretch=2)

        return widget

    def create_date_time_tab(self):
        """日期时间标签页"""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # 左侧：日期时间编辑器
        left_panel = QVBoxLayout()

        group_date_edit = QGroupBox("日期时间编辑器")
        date_edit_layout = QFormLayout()
        date_edit = QDateEdit()
        date_edit.setDate(QDate.currentDate())
        date_edit.setCalendarPopup(True)
        time_edit = QTimeEdit()
        time_edit.setTime(QTime.currentTime())
        datetime_edit = QDateTimeEdit()
        datetime_edit.setDateTime(QDateTime.currentDateTime())
        date_edit_layout.addRow("日期编辑:", date_edit)
        date_edit_layout.addRow("时间编辑:", time_edit)
        date_edit_layout.addRow("日期时间:", datetime_edit)
        group_date_edit.setLayout(date_edit_layout)
        left_panel.addWidget(group_date_edit)

        # 日期时间显示
        group_datetime_display = QGroupBox("当前日期时间")
        datetime_display_layout = QVBoxLayout()
        self.datetime_label = QLabel()
        self.datetime_label.setText(QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss dddd"))
        self.datetime_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #007bff; padding: 10px; background-color: #f8f9fa; border-radius: 4px;")
        datetime_display_layout.addWidget(self.datetime_label)
        group_datetime_display.setLayout(datetime_display_layout)
        left_panel.addWidget(group_datetime_display)

        # 日历控件
        group_calendar = QGroupBox("日历控件 QCalendarWidget")
        calendar_layout = QVBoxLayout()
        calendar = QCalendarWidget()
        calendar.clicked.connect(self.on_calendar_clicked)
        calendar.setGridVisible(True)
        calendar.setStyleSheet("QCalendarWidget { font-size: 14px; }")
        calendar_layout.addWidget(calendar)
        group_calendar.setLayout(calendar_layout)
        left_panel.addWidget(group_calendar)

        left_panel.addStretch()

        # 右侧：时区和计时器
        right_panel = QVBoxLayout()

        group_timezone = QGroupBox("时区选择")
        timezone_layout = QVBoxLayout()
        timezone_combo = QComboBox()
        timezone_combo.addItems(["UTC", "Asia/Shanghai", "America/New_York", "Europe/London", "Tokyo/Japan"])
        timezone_combo.setCurrentText("Asia/Shanghai")
        timezone_layout.addWidget(timezone_combo)
        group_timezone.setLayout(timezone_layout)
        right_panel.addWidget(group_timezone)

        # 计时器/秒表
        group_timer = QGroupBox("秒表")
        timer_layout = QVBoxLayout()
        self.timer_display = QLabel("00:00:00")
        self.timer_display.setStyleSheet(
            "font-size: 32px; font-weight: bold; color: #28a745; padding: 20px; background-color: #f8f9fa; border-radius: 8px;")
        self.timer_display.setAlignment(Qt.AlignCenter)
        timer_layout.addWidget(self.timer_display)
        btn_timer_layout = QHBoxLayout()
        self.btn_start_timer = QPushButton("开始")
        self.btn_start_timer.clicked.connect(self.start_stop_timer)
        self.btn_reset_timer = QPushButton("重置")
        self.btn_reset_timer.clicked.connect(self.reset_timer)
        btn_timer_layout.addWidget(self.btn_start_timer)
        btn_timer_layout.addWidget(self.btn_reset_timer)
        timer_layout.addLayout(btn_timer_layout)
        group_timer.setLayout(timer_layout)
        right_panel.addWidget(group_timer)

        # 倒计时器
        group_countdown = QGroupBox("倒计时器")
        countdown_layout = QVBoxLayout()
        self.countdown_label = QLabel("05:00")
        self.countdown_label.setStyleSheet(
            "font-size: 24px; font-weight: bold; color: #dc3545; padding: 15px; background-color: #f8f9fa; border-radius: 6px;")
        self.countdown_label.setAlignment(Qt.AlignCenter)
        countdown_layout.addWidget(self.countdown_label)
        self.btn_start_countdown = QPushButton("开始倒计时")
        self.btn_start_countdown.clicked.connect(self.start_countdown)
        countdown_layout.addWidget(self.btn_start_countdown)
        group_countdown.setLayout(countdown_layout)
        right_panel.addWidget(group_countdown)

        right_panel.addStretch()

        layout.addLayout(left_panel, stretch=3)
        layout.addLayout(right_panel, stretch=1)

        return widget

    def create_list_views_tab(self):
        """列表视图标签页"""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # 列表控件
        group_list = QGroupBox("列表控件 QListWidget")
        list_layout = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.addItems([f"项目 {i}" for i in range(1, 16)])
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self.list_widget.itemSelectionChanged.connect(self.on_list_selection_changed)
        list_layout.addWidget(self.list_widget)
        list_btn_layout = QHBoxLayout()
        btn_add_item = QPushButton("添加")
        btn_add_item.clicked.connect(self.add_list_item)
        btn_remove_item = QPushButton("删除")
        btn_remove_item.clicked.connect(self.remove_list_item)
        btn_clear_list = QPushButton("清空")
        btn_clear_list.clicked.connect(self.list_widget.clear)
        list_btn_layout.addWidget(btn_add_item)
        list_btn_layout.addWidget(btn_remove_item)
        list_btn_layout.addWidget(btn_clear_list)
        list_layout.addLayout(list_btn_layout)
        group_list.setLayout(list_layout)
        layout.addWidget(group_list)

        # 树形控件
        group_tree = QGroupBox("树形控件 QTreeWidget")
        tree_layout = QVBoxLayout()
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["名称", "类型", "大小"])
        self.tree_widget.setColumnWidth(0, 150)
        root1 = QTreeWidgetItem(self.tree_widget, ["项目 1", "文件夹", ""])
        QTreeWidgetItem(root1, ["文件 1.doc", "文档", "10 KB"])
        QTreeWidgetItem(root1, ["文件 2.png", "图片", "50 KB"])
        root2 = QTreeWidgetItem(self.tree_widget, ["项目 2", "文件夹", ""])
        QTreeWidgetItem(root2, ["视频.mp4", "视频", "100 MB"])
        self.tree_widget.itemClicked.connect(self.on_tree_item_clicked)
        self.tree_widget.expandAll()
        tree_layout.addWidget(self.tree_widget)
        group_tree.setLayout(tree_layout)
        layout.addWidget(group_tree)

        # 表格控件
        group_table = QGroupBox("表格控件 QTableWidget")
        table_layout = QVBoxLayout()
        self.table_widget = QTableWidget(6, 4)
        self.table_widget.setHorizontalHeaderLabels(["姓名", "年龄", "城市", "职业"])
        self.table_widget.setColumnWidth(0, 100)
        self.table_widget.setColumnWidth(2, 100)
        data = [
            ["张三", "28", "北京", "软件工程师"],
            ["李四", "32", "上海", "UI设计师"],
            ["王五", "25", "深圳", "产品经理"],
            ["赵六", "29", "广州", "前端开发"],
            ["钱七", "35", "杭州", "架构师"],
            ["孙八", "27", "成都", "测试工程师"]
        ]
        for row, row_data in enumerate(data):
            for col, cell_data in enumerate(row_data):
                item = QTableWidgetItem(cell_data)
                if col == 1:  # 年龄列居中
                    item.setTextAlignment(Qt.AlignCenter)
                self.table_widget.setItem(row, col, item)
        self.table_widget.itemClicked.connect(self.on_table_item_clicked)
        table_layout.addWidget(self.table_widget)
        group_table.setLayout(table_layout)
        layout.addWidget(group_table)

        return widget

    def create_containers_tab(self):
        """容器控件标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #dee2e6; }")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # 分组框
        groupbox_layout = QHBoxLayout()
        for i in range(1, 4):
            group = QGroupBox(f"分组框 {i}")
            group.setStyleSheet("QGroupBox { font-weight: bold; }")
            group_layout = QVBoxLayout()
            for j in range(1, 4):
                group_layout.addWidget(QCheckBox(f"选项 {j}"))
            group.setLayout(group_layout)
            groupbox_layout.addWidget(group)
        scroll_layout.addLayout(groupbox_layout)

        # 标签页控件
        tab_widget_inner = QTabWidget()
        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)
        tab1_layout.addWidget(QLabel("标签页 1 的内容"))
        tab1_layout.addWidget(QPushButton("按钮 1"))
        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)
        tab2_layout.addWidget(QLabel("标签页 2 的内容"))
        tab2_layout.addWidget(QCheckBox("复选框 1"))
        tab3 = QWidget()
        tab3_layout = QVBoxLayout(tab3)
        tab3_layout.addWidget(QLabel("标签页 3 的内容"))
        line_edit_tab3 = QLineEdit("输入框 1")
        tab3_layout.addWidget(line_edit_tab3)
        tab_widget_inner.addTab(tab1, "标签 1")
        tab_widget_inner.addTab(tab2, "标签 2")
        tab_widget_inner.addTab(tab3, "标签 3")
        scroll_layout.addWidget(tab_widget_inner)

        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #dee2e6; }")
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("左侧窗口"))
        list_widget = QListWidget()
        list_widget.addItems(["项目 A", "项目 B", "项目 C"])
        left_layout.addWidget(list_widget)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.addWidget(QLabel("右侧窗口"))
        text_edit = QTextEdit("可以调整分割器大小")
        right_layout.addWidget(text_edit)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        scroll_layout.addWidget(splitter)

        # 框架
        frame_layout = QHBoxLayout()
        frame_styles = [
            (QFrame.Box, "Box", QFrame.Plain),
            (QFrame.Panel, "Panel", QFrame.Raised),
            (QFrame.WinPanel, "WinPanel", QFrame.Sunken),
            (QFrame.HLine, "HLine", QFrame.Plain),
            (QFrame.VLine, "VLine", QFrame.Plain)
        ]
        for shape, name, shadow in frame_styles:
            frame = QFrame()
            frame.setFrameShape(shape)
            frame.setFrameShadow(shadow)
            frame.setLineWidth(2)
            frame.setMidLineWidth(1)
            if shape in [QFrame.HLine, QFrame.VLine]:
                frame.setFixedSize(100 if shape == QFrame.VLine else 60, 20 if shape == QFrame.HLine else 60)
            else:
                frame.setFixedSize(100, 60)
            frame_layout.addWidget(frame)
        scroll_layout.addLayout(frame_layout)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        return widget

    def create_progress_tab(self):
        """进度和状态标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 进度条
        group_progress = QGroupBox("进度条控件 QProgressBar")
        progress_layout = QVBoxLayout()
        self.progress_bar1 = QProgressBar()
        self.progress_bar1.setRange(0, 100)
        self.progress_bar1.setValue(0)
        self.progress_bar1.setFormat("正在处理: %p%")
        self.progress_bar1.setStyleSheet("QProgressBar { text-align: center; }")
        self.progress_bar2 = QProgressBar()
        self.progress_bar2.setRange(0, 0)  # 忙碌指示器
        self.progress_bar2.setFormat("请稍候...")
        self.progress_bar3 = QProgressBar()
        self.progress_bar3.setRange(0, 100)
        self.progress_bar3.setValue(75)
        self.progress_bar3.setFormat("%v / %m")
        progress_layout.addWidget(self.progress_bar1)
        progress_layout.addWidget(self.progress_bar2)
        progress_layout.addWidget(self.progress_bar3)
        btn_start_progress = QPushButton("开始/停止 进度动画")
        btn_start_progress.clicked.connect(self.start_progress_animation)
        progress_layout.addWidget(btn_start_progress)
        group_progress.setLayout(progress_layout)
        layout.addWidget(group_progress)

        # 状态指示器
        group_status = QGroupBox("状态指示器")
        status_layout = QGridLayout()
        status_layout.setSpacing(10)
        for i in range(6):
            btn = QPushButton(f"状态 {i + 1}")
            btn.setCheckable(True)
            if i % 2 == 0:
                btn.setChecked(True)
                btn.setStyleSheet("QPushButton:checked { background-color: #28a745; color: white; border: none; }")
            else:
                btn.setStyleSheet(
                    "QPushButton { background-color: #6c757d; color: white; border: none; } QPushButton:checked { background-color: #dc3545; }")
            status_layout.addWidget(btn, i // 3, i % 3)
        group_status.setLayout(status_layout)
        layout.addWidget(group_status)

        # 水平和垂直滚动条
        group_scroll = QGroupBox("滚动条 QScrollBar")
        scroll_layout = QHBoxLayout()
        scroll_area = QScrollArea()
        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)
        for i in range(25):
            label = QLabel(f"滚动内容行 {i + 1:02d}")
            label.setStyleSheet("padding: 5px; border-bottom: 1px solid #eee;")
            scroll_content_layout.addWidget(label)
        scroll_content.setMinimumHeight(1000)
        scroll_area.setWidget(scroll_content)
        scroll_area.setFixedHeight(200)
        scroll_layout.addWidget(scroll_area)

        vertical_scrollbar = QScrollBar(Qt.Vertical)
        vertical_scrollbar.setRange(0, 100)
        vertical_scrollbar.setValue(50)
        vertical_scrollbar.setStyleSheet("QScrollBar { width: 20px; }")
        scroll_layout.addWidget(vertical_scrollbar)

        self.horizontal_scrollbar = QScrollBar(Qt.Horizontal)
        self.horizontal_scrollbar.setRange(0, 100)
        self.horizontal_scrollbar.setValue(30)
        self.horizontal_scrollbar.setStyleSheet("QScrollBar { height: 20px; }")

        group_scroll.setLayout(scroll_layout)
        layout.addWidget(group_scroll)
        layout.addWidget(self.horizontal_scrollbar)

        layout.addStretch()
        return widget

    def create_dialogs_tab(self):
        """对话框示例标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 标准对话框
        group_std_dialogs = QGroupBox("标准消息对话框")
        std_dialogs_layout = QGridLayout()
        btn_message = QPushButton("信息消息框")
        btn_message.clicked.connect(self.show_message_box)
        btn_input = QPushButton("输入对话框")
        btn_input.clicked.connect(self.show_input_dialog)
        btn_file = QPushButton("文件选择对话框")
        btn_file.clicked.connect(self.show_file_dialog)
        btn_color = QPushButton("颜色选择对话框")
        btn_color.clicked.connect(self.show_color_dialog)
        btn_font = QPushButton("字体选择对话框")
        btn_font.clicked.connect(self.show_font_dialog)
        for i, btn in enumerate([btn_message, btn_input, btn_file, btn_color, btn_font]):
            std_dialogs_layout.addWidget(btn, i // 2, i % 2)
        group_std_dialogs.setLayout(std_dialogs_layout)
        layout.addWidget(group_std_dialogs)

        # 自定义对话框
        group_custom_dialogs = QGroupBox("消息类型对话框")
        custom_dialogs_layout = QGridLayout()
        btn_about = QPushButton("关于对话框")
        btn_about.clicked.connect(self.show_about_dialog)
        btn_critical = QPushButton("错误对话框")
        btn_critical.clicked.connect(self.show_critical_dialog)
        btn_question = QPushButton("确认对话框")
        btn_question.clicked.connect(self.show_question_dialog)
        btn_warning = QPushButton("警告对话框")
        btn_warning.clicked.connect(self.show_warning_dialog)
        for i, btn in enumerate([btn_about, btn_critical, btn_question, btn_warning]):
            custom_dialogs_layout.addWidget(btn, i // 2, i % 2)
        group_custom_dialogs.setLayout(custom_dialogs_layout)
        layout.addWidget(group_custom_dialogs)

        # 向导对话框
        group_wizard = QGroupBox("向导对话框")
        wizard_layout = QVBoxLayout()
        btn_wizard = QPushButton("打开向导对话框")
        btn_wizard.clicked.connect(self.show_wizard_dialog)
        wizard_layout.addWidget(btn_wizard)
        group_wizard.setLayout(wizard_layout)
        layout.addWidget(group_wizard)

        # 自定义消息显示区域
        self.dialog_result_label = QLabel("对话框操作结果将显示在这里")
        self.dialog_result_label.setStyleSheet(
            "padding: 15px; background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; color: #495057;")
        self.dialog_result_label.setWordWrap(True)
        layout.addWidget(self.dialog_result_label)

        layout.addStretch()
        return widget

    def create_advanced_controls_tab(self):
        """高级控件标签页"""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # 左侧：高级编辑控件
        left_panel = QVBoxLayout()

        group_richtext = QGroupBox("富文本编辑器")
        richtext_layout = QVBoxLayout()
        self.richtext_edit = QTextEdit()
        self.richtext_edit.setHtml("""
            <h2>富文本编辑功能</h2>
            <p>支持完整的<b>富文本</b>编辑功能：</p>
            <ul>
                <li>文字格式化（<b>粗体</b>、<i>斜体</i>、<u>下划线</u>）</li>
                <li>颜色与字体设置</li>
                <li>列表和编号</li>
                <li>超链接</li>
                <li>段落对齐</li>
            </ul>
            <p style="color: #007bff; text-align: center;">居中的蓝色文字</p>
        """)
        richtext_layout.addWidget(self.richtext_edit)
        group_richtext.setLayout(richtext_layout)
        left_panel.addWidget(group_richtext)

        # 撤销/重做视图
        group_undo = QGroupBox("撤销/重做 视图 (QUndoView)")
        undo_layout = QVBoxLayout()
        self.undo_view = QTextEdit()
        self.undo_view.setPlainText("撤销/重做视图需要配合QUndoStack使用\n这里仅作展示...")
        self.undo_view.setReadOnly(True)
        undo_layout.addWidget(self.undo_view)
        group_undo.setLayout(undo_layout)
        left_panel.addWidget(group_undo)

        # 代码编辑器样式
        group_code = QGroupBox("代码编辑器样式 QPlainTextEdit")
        code_layout = QVBoxLayout()
        self.code_edit = QPlainTextEdit()
        self.code_edit.setPlaceholderText("// 代码编辑区域...")
        sample_python = '''# Python 示例代码
def fibonacci(n):
    """生成斐波那契数列"""
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b

# 使用示例
for num in fibonacci(10):
    print(num)'''
        self.code_edit.setPlainText(sample_python)
        code_layout.addWidget(self.code_edit)
        group_code.setLayout(code_layout)
        left_panel.addWidget(group_code)

        left_panel.addStretch()

        # 右侧：特殊控件
        right_panel = QVBoxLayout()

        # 图形视图占位
        group_graphics = QGroupBox("QGraphicsView 占位")
        graphics_layout = QVBoxLayout()
        graphics_label = QLabel("图形视图区域\n(QGraphicsView)")
        graphics_label.setAlignment(Qt.AlignCenter)
        graphics_label.setStyleSheet(
            "background-color: #f8f9fa; border: 2px dashed #dee2e6; padding: 40px; color: #6c757d;")
        graphics_layout.addWidget(graphics_label)
        group_graphics.setLayout(graphics_layout)
        right_panel.addWidget(group_graphics)

        # 其他高级控件示例
        group_other = QGroupBox("其他特殊控件")
        other_layout = QVBoxLayout()

        # 大小调整手柄
        size_grip_layout = QHBoxLayout()
        size_grip_label = QLabel("SizeGrip:")
        size_grip = QSizeGrip(widget)
        size_grip_layout.addWidget(size_grip_label)
        size_grip_layout.addWidget(size_grip, alignment=Qt.AlignRight)
        other_layout.addLayout(size_grip_layout)

        # 可展开区域
        collapse_btn = QPushButton("可折叠区域 ▼")
        collapse_btn.setCheckable(True)
        collapse_btn.setStyleSheet("QPushButton { text-align: left; padding: 8px; }")
        other_layout.addWidget(collapse_btn)

        # 提示信息
        other_layout.addWidget(QLabel("• QCompleter - 自动补全"))
        other_layout.addWidget(QLabel("• QKeySequenceEdit - 快捷键输入"))
        other_layout.addWidget(QLabel("• QSvgWidget - SVG显示"))
        other_layout.addWidget(QLabel("• QOpenGLWidget - OpenGL渲染"))

        group_other.setLayout(other_layout)
        right_panel.addWidget(group_other)

        # 快速操作按钮
        group_actions = QGroupBox("快速操作")
        actions_layout = QVBoxLayout()
        btn_clear_all = QPushButton("清空所有文本")
        btn_clear_all.clicked.connect(self.clear_all_text)
        btn_random_progress = QPushButton("随机进度")
        btn_random_progress.clicked.connect(self.random_progress)
        actions_layout.addWidget(btn_clear_all)
        actions_layout.addWidget(btn_random_progress)
        group_actions.setLayout(actions_layout)
        right_panel.addWidget(group_actions)

        right_panel.addStretch()

        layout.addLayout(left_panel, stretch=2)
        layout.addLayout(right_panel, stretch=1)

        return widget

    def apply_custom_styles(self):
        """应用自定义样式"""
        # 使用 Windows 或 Fusion 样式（跨平台）
        # QApplication.setStyle("Windows")
        # 不再设置全局样式，因为用户可能有自己的样式

        # 可选：应用 Bootstrap 风格的样式
        self.apply_bootstrap_like_styles()

    def apply_bootstrap_like_styles(self):
        """应用类似 Bootstrap 的样式"""
        self.setStyleSheet("""
            QWidget {
                font-family: "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                font-size: 14px;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #495057;
            }
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
            QPushButton:pressed {
                background-color: #545b62;
            }
            QPushButton:checked {
                background-color: #007bff;
            }
            QPushButton:disabled {
                background-color: #e9ecef;
                color: #6c757d;
            }
            QLineEdit, QTextEdit, QPlainTextEdit {
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 6px 12px;
                background-color: white;
                selection-background-color: #007bff;
            }
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
                border-color: #80bdff;
                outline: none;
            }
            QProgressBar {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #007bff;
            }
            QScrollBar:vertical {
                width: 14px;
                background: #f8f9fa;
            }
            QScrollBar:horizontal {
                height: 14px;
                background: #f8f9fa;
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
        """)

    def start_animation_timer(self):
        """启动动画定时器"""
        # 更新LCD时间显示
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.timer.start(1000)

        # 进度条动画
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.update_progress)

        self.animation_value = 0

        # 计时器状态
        self.timer_running = False
        self.timer_seconds = 0

        # 倒计时器状态
        self.countdown_running = False
        self.countdown_seconds = 300  # 5分钟

    def update_timer(self):
        """更新LCD显示的时间"""
        current_time = QDateTime.currentDateTime().toString("hh:mm:ss")
        current_datetime = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss dddd")
        # 这里可以更新任何需要显示当前时间的控件

    def update_progress(self):
        """更新进度条动画"""
        self.animation_value += 2
        if self.animation_value > 100:
            self.animation_value = 0
        self.progress_bar1.setValue(self.animation_value)

    def increase_progress(self):
        """手动增加进度"""
        value = self.control_progress.value()
        value = min(value + 10, 100)
        self.control_progress.setValue(value)

    def random_progress(self):
        """随机设置进度"""
        import random
        value = random.randint(0, 100)
        self.control_progress.setValue(value)

    def start_progress_animation(self):
        """启动/停止进度动画"""
        if self.progress_timer.isActive():
            self.progress_timer.stop()
        else:
            self.progress_timer.start(50)

    def start_stop_timer(self):
        """开始/停止秒表"""
        if not hasattr(self, 'timer_display_timer'):
            self.timer_display_timer = QTimer(self)
            self.timer_display_timer.timeout.connect(self.update_stopwatch)

        if self.timer_running:
            self.timer_display_timer.stop()
            self.btn_start_timer.setText("开始")
            self.timer_running = False
        else:
            self.timer_display_timer.start(1000)
            self.btn_start_timer.setText("停止")
            self.timer_running = True

    def reset_timer(self):
        """重置秒表"""
        self.timer_seconds = 0
        self.timer_display.setText("00:00:00")
        if self.timer_running:
            self.start_stop_timer()  # 停止计时

    def update_stopwatch(self):
        """更新秒表显示"""
        self.timer_seconds += 1
        hours = self.timer_seconds // 3600
        minutes = (self.timer_seconds % 3600) // 60
        seconds = self.timer_seconds % 60
        self.timer_display.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def start_countdown(self):
        """开始倒计时"""
        if not hasattr(self, 'countdown_timer'):
            self.countdown_timer = QTimer(self)
            self.countdown_timer.timeout.connect(self.update_countdown)

        if self.countdown_running:
            self.countdown_timer.stop()
            self.btn_start_countdown.setText("开始倒计时")
            self.countdown_running = False
        else:
            self.countdown_timer.start(1000)
            self.btn_start_countdown.setText("停止倒计时")
            self.countdown_running = True

    def update_countdown(self):
        """更新倒计时显示"""
        self.countdown_seconds -= 1
        if self.countdown_seconds <= 0:
            self.countdown_timer.stop()
            self.countdown_seconds = 300
            self.btn_start_countdown.setText("开始倒计时")
            self.countdown_running = False
            self.countdown_label.setText("00:00")
            QMessageBox.information(self, "倒计时结束", "倒计时已完成！")
            return

        minutes = self.countdown_seconds // 60
        seconds = self.countdown_seconds % 60
        self.countdown_label.setText(f"{minutes:02d}:{seconds:02d}")

    # 事件处理函数
    def on_checkbox_changed(self, state):
        """复选框状态改变"""
        sender = self.sender()
        self.input_status_label.setText(f"复选框 '{sender.text()}' 状态: {state}")

    def on_spin_changed(self, value):
        """旋转框值改变"""
        self.input_status_label.setText(f"数值改变: {value}")

    def on_slider_changed(self, value):
        """滑块值改变"""
        self.input_status_label.setText(f"滑块值: {value}")

    def on_dial_changed(self, value):
        """转盘值改变"""
        self.input_status_label.setText(f"转盘值: {value}")

    def on_text_changed(self):
        """文本改变"""
        self.input_status_label.setText("文本已修改")

    def on_font_changed(self, font):
        """字体改变"""
        self.input_status_label.setText(f"字体: {font.family()}")

    def on_button_clicked(self):
        """按钮点击"""
        sender = self.sender()
        self.dialog_result_label.setText(f"点击按钮: {sender.text()}")

    def on_list_selection_changed(self):
        """列表选择改变"""
        items = self.list_widget.selectedItems()
        if items:
            selected = [item.text() for item in items]
            self.input_status_label.setText(f"选择了: {', '.join(selected)}")

    def on_tree_item_clicked(self, item, column):
        """树项点击"""
        self.input_status_label.setText(f"点击: {item.text(0)}")

    def on_table_item_clicked(self, item):
        """表格项点击"""
        self.input_status_label.setText(f"单元格 ({item.row()}, {item.column()}) = {item.text()}")

    def on_calendar_clicked(self, date):
        """日历点击"""
        self.input_status_label.setText(f"选择日期: {date.toString('yyyy-MM-dd')}")

    def add_list_item(self):
        """添加列表项"""
        count = self.list_widget.count()
        self.list_widget.addItem(f"新项目 {count + 1}")
        self.list_widget.scrollToBottom()
        self.input_status_label.setText(f"添加新项目 {count + 1}")

    def remove_list_item(self):
        """删除选中的列表项"""
        items = self.list_widget.selectedItems()
        if not items:
            return
        for item in items:
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
        self.input_status_label.setText(f"删除了 {len(items)} 个项目")

    def clear_all_text(self):
        """清空所有文本编辑器"""
        self.text_edit.clear()
        self.plain_text.clear()
        self.richtext_edit.clear()
        self.code_edit.clear()
        self.input_status_label.setText("所有文本已清空")

    # 对话框函数
    def show_message_box(self):
        QMessageBox.information(self, "信息", "这是一条信息消息")
        self.dialog_result_label.setText("关闭了信息消息框")

    def show_input_dialog(self):
        text, ok = QInputDialog.getText(self, "输入对话框", "请输入您的姓名:")
        if ok:
            self.dialog_result_label.setText(f"您输入了: {text}")
        else:
            self.dialog_result_label.setText("取消了输入")

    def show_file_dialog(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "选择文件", "",
                                                   "所有文件 (*.*);;文本文件 (*.txt);;Python文件 (*.py)")
        if file_name:
            self.dialog_result_label.setText(f"选择文件: {file_name}")
        else:
            self.dialog_result_label.setText("未选择文件")

    def show_color_dialog(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.dialog_result_label.setText(
                f"选择颜色: {color.name()} (RGB: {color.red()}, {color.green()}, {color.blue()})")
        else:
            self.dialog_result_label.setText("未选择颜色")

    def show_font_dialog(self):
        font, ok = QFontDialog.getFont()
        if ok:
            self.dialog_result_label.setText(f"选择字体: {font.family()}, {font.pointSize()}pt")
        else:
            self.dialog_result_label.setText("未选择字体")

    def show_about_dialog(self):
        QMessageBox.about(self, "关于", "PyQt5 全控件样式展示 Widget\n版本: 1.0\n基于 QWidget 的纯控件展示")
        self.dialog_result_label.setText("关闭了关于对话框")

    def show_critical_dialog(self):
        QMessageBox.critical(self, "错误", "发生了一个错误！\n请检查您的操作是否正确。")
        self.dialog_result_label.setText("关闭了错误对话框")

    def show_question_dialog(self):
        reply = QMessageBox.question(self, "确认", "确定要继续执行此操作吗？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.dialog_result_label.setText("选择: 是")
        else:
            self.dialog_result_label.setText("选择: 否")

    def show_warning_dialog(self):
        QMessageBox.warning(self, "警告", "这是一个警告消息！\n请注意相关事项。")
        self.dialog_result_label.setText("关闭了警告对话框")

    def show_wizard_dialog(self):
        wizard = QWizard(self)
        wizard.setWindowTitle("向导对话框示例")
        wizard.setWizardStyle(QWizard.ModernStyle)

        # 第一页
        page1 = QWizardPage()
        page1.setTitle("欢迎使用向导")
        page1.setSubTitle("请按照向导完成设置")
        page1_layout = QVBoxLayout()
        page1_layout.addWidget(QLabel("这是一个向导对话框的示例，引导用户完成多步骤操作。"))
        page1_layout.addWidget(QCheckBox("我同意使用条款"))
        page1.setLayout(page1_layout)

        # 第二页
        page2 = QWizardPage()
        page2.setTitle("配置设置")
        page2.setSubTitle("请配置以下选项")
        page2_layout = QFormLayout()
        page2_layout.addRow("用户名:", QLineEdit())
        page2_layout.addRow("邮箱:", QLineEdit())
        page2.setLayout(page2_layout)

        # 第三页
        page3 = QWizardPage()
        page3.setTitle("完成")
        page3.setSubTitle("设置即将完成")
        page3_layout = QVBoxLayout()
        page3_layout.addWidget(QLabel("点击完成按钮结束向导。"))
        page3.setLayout(page3_layout)

        wizard.addPage(page1)
        wizard.addPage(page2)
        wizard.addPage(page3)
        wizard.exec()
        self.dialog_result_label.setText("向导对话框已完成")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName("PyQt5 全控件样式展示 - QWidget")
    app.setOrganizationName("PyQt5 Demo")

    # 设置应用样式 - 可选
    app.setStyle("Fusion")
    #app.setStyleSheet(MODERN_STYLESHEET)

    window = ControlGalleryWidget()
    window.show()

    sys.exit(app.exec())