# 自定义日期选择控件：将三角改为日历图标，且点击文本框也能弹出日历
from PyQt5 import QtWidgets, QtCore, QtGui


class CalendarDateEdit(QtWidgets.QDateTimeEdit):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)  # 去除原生上下箭头

        # Sentinel“未选择”时间
        self.null_date = QtCore.QDateTime(QtCore.QDate(2000, 1, 1), QtCore.QTime(0, 0, 0))
        self.setCalendarPopup(False)
        self.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.setMinimumDateTime(self.null_date)
        self.setSpecialValueText("请选择日期")
        self.setDateTime(self.null_date)

        # 允许键盘输入，并安装过滤器处理删除键
        self.lineEdit().installEventFilter(self)

        # 右侧按钮相关设置
        self._btn_w = 26

        # 定义日历按钮 (替代三角)
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
        self.calendar_btn.clicked.connect(self._open_picker)

        # 定义清除按钮
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
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        self.clear_btn.hide()

        # self.lineEdit().installEventFilter(self)  # 不需要拦截点击了
        self.dateTimeChanged.connect(self._on_date_changed)

        # 初始状态更新
        self._update_btn_state(self.dateTime() > self.null_date)

    def eventFilter(self, obj, event):
        if obj == self.lineEdit():
            # 点击输入框时，如果是空值(显示提示语状态)，自动填充当前时间并全选
            # 这样"请选择日期"字样消失，且无需手动删除，直接输入即可覆盖
            if event.type() == QtCore.QEvent.MouseButtonRelease and event.button() == QtCore.Qt.LeftButton:
                if self.dateTime() == self.null_date:
                    self.setDateTime(QtCore.QDateTime.currentDateTime())
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
                        # 只要选中的内容稍微多一点(比如选中了整个部分)，就认为是清空
                        if len(selected) > 0:
                            self.setDateTime(self.null_date)
                            return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        h = self.height()
        # 垂直居中
        y = max(0, (h - self._btn_w) // 2)

        # 按钮位置始终在最右边（因为只显示其中一个）
        x = self.width() - self._btn_w - 2

        if not self.calendar_btn.isHidden():
            self.calendar_btn.setGeometry(x, y, self._btn_w, self._btn_w)

        if not self.clear_btn.isHidden():
            self.clear_btn.setGeometry(x, y, self._btn_w, self._btn_w)

    def _on_date_changed(self, dt):
        self._update_btn_state(dt > self.null_date)

    def _update_btn_state(self, is_valid: bool):
        """有有效值时显示'✕'按钮，无效值时才显示日历图标。两互斥。"""
        if is_valid:
            self.clear_btn.show()
            self.calendar_btn.hide()
        else:
            self.clear_btn.hide()
            self.calendar_btn.show()

        # 无论显示哪个，都只占用一个按钮的宽度
        right_padding = self._btn_w + 6

        self.setStyleSheet(f"""
            QDateTimeEdit {{
                padding-right: {right_padding}px;
            }}
        """)

    def _on_clear_clicked(self):
        # 清空已选
        self.setDateTime(self.null_date)
        # self.setSpecialValueText("请选择日期") # 已在init设置

    # ===== Public helpers (for View/Controller) =====
    def is_valid(self) -> bool:
        """当前是否选择了有效日期（非 sentinel）。"""
        try:
            return self.dateTime() > self.null_date
        except Exception:
            return False

    def value_or_none(self):
        """返回 QDateTime 或 None：未选择时返回 None。"""
        return self.dateTime() if self.is_valid() else None

    def clear(self):
        """清空选择（回到 sentinel）。"""
        self._on_clear_clicked()

    def _open_picker(self):
        """弹出自定义日期+时间选择器。"""
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("选择日期时间")
        dlg.setWindowFlags(dlg.windowFlags() | QtCore.Qt.Popup)

        lay = QtWidgets.QVBoxLayout(dlg)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        cal = QtWidgets.QCalendarWidget(dlg)
        cal.setGridVisible(True)

        time_edit = QtWidgets.QTimeEdit(dlg)
        time_edit.setDisplayFormat("HH:mm:ss")
        time_edit.setKeyboardTracking(False)

        # 当前值为初始/未选，则默认为当前系统时间
        cur = self.dateTime()
        if cur and cur > self.null_date:
            cal.setSelectedDate(cur.date())
            time_edit.setTime(cur.time())
        else:
            now = QtCore.QDateTime.currentDateTime()
            cal.setSelectedDate(now.date())
            time_edit.setTime(now.time())

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        ok_btn = QtWidgets.QPushButton("确定", dlg)
        cancel_btn = QtWidgets.QPushButton("取消", dlg)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)

        lay.addWidget(cal)
        lay.addWidget(time_edit)
        lay.addLayout(btns)

        def on_ok():
            dt = QtCore.QDateTime(cal.selectedDate(), time_edit.time())
            self.setDateTime(dt)
            dlg.accept()

        ok_btn.clicked.connect(on_ok)
        cancel_btn.clicked.connect(dlg.reject)

        # 弹窗在控件正下方
        g = self.rect()
        pos = self.mapToGlobal(QtCore.QPoint(0, g.height()))
        dlg.move(pos)
        dlg.exec_()