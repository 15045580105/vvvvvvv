# 自定义日期选择控件：将三角改为日历图标，且点击文本框也能弹出日历
from PyQt5 import QtWidgets, QtCore, QtGui


class CalendarDateEdit(QtWidgets.QDateTimeEdit):
    def __init__(self, parent=None):
        """初始化自定义日期选择控件。"""
        # 1. 调用父类初始化
        super().__init__(parent)

        # 2. 去除原生上下箭头按钮
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)  # 去除原生上下箭头

        # 3. 初始化 Sentinel“未选择”时间
        self.null_date = QtCore.QDateTime(QtCore.QDate(2000, 1, 1), QtCore.QTime(0, 0, 0))
        # 4. 禁用原生弹窗，设置显示格式和最小值
        self.setCalendarPopup(False)
        self.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.setMinimumDateTime(self.null_date)
        # 5. 设置空值占位文本
        self.setSpecialValueText("请选择日期")
        self.setDateTime(self.null_date)

        # 6. 允许键盘输入，并安装过滤器处理删除键
        self.lineEdit().installEventFilter(self)

        # 7. 右侧按钮相关设置
        self._btn_w = 26

        # 8. 定义日历按钮
        self.calendar_btn = QtWidgets.QToolButton(self)
        self.calendar_btn.setText("📅")  # Calendar Emoji
        self.calendar_btn.setCursor(QtGui.QCursor(QtCore.Qt.ArrowCursor))
        self.calendar_btn.setStyleSheet(f"""
            QToolButton {{
                border: none;
                background: transparent;
                padding: 0px;
                margin: 0px;
                font-size: 16px;
            }}
            QToolButton:hover {{
                background: #F3F4F6;
                border-radius: 4px;
            }}
        """)
        # 9. 连接日历按钮点击信号
        self.calendar_btn.clicked.connect(self._open_picker)

        # 10. 定义清除按钮
        self.clear_btn = QtWidgets.QToolButton(self)
        self.clear_btn.setText("✕")
        self.clear_btn.setToolTip("清空")
        self.clear_btn.setCursor(QtGui.QCursor(QtCore.Qt.ArrowCursor))
        self.clear_btn.setStyleSheet(f"""
            QToolButton {{
                border: none;
                background: transparent;
                padding: 0px;
                margin: 0px;
                font-size: 16px;
                color: #6B7280;
            }}
            QToolButton:hover {{
                color: #111827;
                background: #F3F4F6;
                border-radius: 4px;
            }}
        """)
        # 11. 连接清除按钮点击信号并默认隐藏
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        self.clear_btn.hide()

        # self.lineEdit().installEventFilter(self)  # 不需要拦截点击了
        # 12. 连接日期变更信号
        self.dateTimeChanged.connect(self._on_date_changed)

        # 13. 初始状态更新（根据当前值决定显示哪个按钮）
        self._update_btn_state(self.dateTime() > self.null_date)

    def eventFilter(self, obj, event):
        """事件过滤器：处理点击输入框自动填充和键盘删除键清除功能。"""
        if obj == self.lineEdit():
            # 点击输入框时，如果是空值(显示提示语状态)，自动填充当前时间并全选
            # 这样"请选择日期"字样消失，且无需手动删除，直接输入即可覆盖
            if event.type() == QtCore.QEvent.MouseButtonRelease and event.button() == QtCore.Qt.LeftButton:
                # 1. 如果当前是空值状态，点击自动填充当前时间
                if self.dateTime() == self.null_date:
                    self.setDateTime(QtCore.QDateTime.currentDateTime())
                    # 2. 异步全选文本方便直接输入
                    QtCore.QTimer.singleShot(0, self.lineEdit().selectAll)

            elif event.type() == QtCore.QEvent.KeyPress:
                # 处理删除/退格键，实现“即使有掩码也能一键清除”
                if event.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
                    # 如果全选了文本，或者当前已经是可清除状态
                    if obj.hasSelectedText():
                        # 简单判断：如果选中的文本长度接近总长度，或者用户想删内容 -> 重置
                        # QDateTimeEdit 的 selectedText 往往包含格式符，比较复杂
                        # 这里只要有选中操作并按了删除，我们就视为用户想清空
                        text = obj.text()
                        selected = obj.selectedText()
                        # 3. 只要选中的内容稍微多一点(比如选中了整个部分)，就认为是清空
                        if len(selected) > 0:
                            self.setDateTime(self.null_date)
                            return True
        # 4. 其他事件交给父类处理
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        """处理大小调整事件，保持右侧按钮位置正确。"""
        # 1. 调用父类处理
        super().resizeEvent(event)
        h = self.height()
        # 2. 计算垂直居中位置
        y = max(0, (h - self._btn_w) // 2)

        # 3. 计算水平位置（始终在最右边，因为只显示其中一个）
        x = self.width() - self._btn_w - 2

        # 4. 更新日历按钮几何位置
        if not self.calendar_btn.isHidden():
            self.calendar_btn.setGeometry(x, y, self._btn_w, self._btn_w)

        # 5. 更新清除按钮几何位置
        if not self.clear_btn.isHidden():
            self.clear_btn.setGeometry(x, y, self._btn_w, self._btn_w)

    def _on_date_changed(self, dt):
        """日期值变更时的槽函数。"""
        # 1. 根据日期是否有效更新按钮状态
        self._update_btn_state(dt > self.null_date)

    def _update_btn_state(self, is_valid: bool):
        """有有效值时显示'✕'按钮，无效值时才显示日历图标。两互斥。"""
        # 1. 切换按钮显隐
        if is_valid:
            self.clear_btn.show()
            self.calendar_btn.hide()
        else:
            self.clear_btn.hide()
            self.calendar_btn.show()

        # 2. 计算右侧内边距，无论显示哪个，都只占用一个按钮的宽度
        right_padding = self._btn_w + 6

        # 3. 应用样式表调整 padding，防止文字被按钮遮挡
        self.setStyleSheet(f"""
            QDateTimeEdit {{
                padding-right: {right_padding}px;
            }}
        """)

    def _on_clear_clicked(self):
        """清除按钮点击处理。"""
        # 1. 清空已选，重置为 Sentinel 值
        self.setDateTime(self.null_date)
        # self.setSpecialValueText("请选择日期") # 已在init设置

    # ===== Public helpers (for View/Controller) =====
    def is_valid(self) -> bool:
        """判断当前是否选择了有效日期（非 sentinel）。"""
        try:
            # 1. 比较当前值是否大于空值标记
            return self.dateTime() > self.null_date
        except Exception:
            return False

    def value_or_none(self):
        """返回 QDateTime 或 None：未选择时返回 None。"""
        # 1. 如果有效返回 QDateTime，否则返回 None
        return self.dateTime() if self.is_valid() else None

    def clear(self):
        """清空当前选择，重置为未选中状态。"""
        # 1. 调用内部清除逻辑
        self._on_clear_clicked()

    def _open_picker(self):
        """弹出自定义日期+时间选择器对话框。"""
        # 1. 创建对话框
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("选择日期时间")
        dlg.setWindowFlags(dlg.windowFlags() | QtCore.Qt.Popup)

        # 2. 设置布局
        lay = QtWidgets.QVBoxLayout(dlg)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # 3. 创建日历控件
        cal = QtWidgets.QCalendarWidget(dlg)
        cal.setGridVisible(True)

        # 4. 创建时间编辑控件
        time_edit = QtWidgets.QTimeEdit(dlg)
        time_edit.setDisplayFormat("HH:mm:ss")
        time_edit.setKeyboardTracking(False)

        # 5. 初始化控件值
        # 当前值为初始/未选，则默认为当前系统时间
        cur = self.dateTime()
        if cur and cur > self.null_date:
            cal.setSelectedDate(cur.date())
            time_edit.setTime(cur.time())
        else:
            now = QtCore.QDateTime.currentDateTime()
            cal.setSelectedDate(now.date())
            time_edit.setTime(now.time())

        # 6. 创建底部按钮
        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        ok_btn = QtWidgets.QPushButton("确定", dlg)
        cancel_btn = QtWidgets.QPushButton("取消", dlg)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)

        # 7. 添加控件到布局
        lay.addWidget(cal)
        lay.addWidget(time_edit)
        lay.addLayout(btns)

        # 8. 定义确认回调
        def on_ok():
            dt = QtCore.QDateTime(cal.selectedDate(), time_edit.time())
            self.setDateTime(dt)
            dlg.accept()

        # 9. 连接按钮信号
        ok_btn.clicked.connect(on_ok)
        cancel_btn.clicked.connect(dlg.reject)

        # 10. 计算弹窗位置（在控件正下方）
        g = self.rect()
        pos = self.mapToGlobal(QtCore.QPoint(0, g.height()))
        dlg.move(pos)

        # 11. 显示对话框
        dlg.exec_()