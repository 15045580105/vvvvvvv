# 自定义日期选择控件：将三角改为日历图标，且点击文本框也能弹出日历
from PyQt5 import QtWidgets, QtCore


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

        # 只能通过弹窗交互
        self.lineEdit().setReadOnly(True)

        # 右侧按钮相关设置
        self._btn_w = 26
        self.setStyleSheet(f"""
            QDateTimeEdit {{
                padding-right: {self._btn_w + 6}px;
            }}
        """)

        self.tool_btn = QtWidgets.QToolButton(self)
        self.tool_btn.setObjectName("dt_tool_btn")
        self.tool_btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.tool_btn.setAutoRaise(True)
        self.tool_btn.setIconSize(QtCore.QSize(self._btn_w, self._btn_w))
        self.tool_btn.setStyleSheet(f"""
            QToolButton#dt_tool_btn {{
                border: none;
                background: transparent;
                min-width: {self._btn_w}px;
                max-width: {self._btn_w}px;
                min-height: {self._btn_w}px;
                max-height: {self._btn_w}px;
                padding: 0px;
                margin: 0px;
                font-size: 16px;
                color: #6B7280;
            }}
            QToolButton#dt_tool_btn:hover {{
                color: #111827;
            }}
        """)
        self.tool_btn.clicked.connect(self._on_tool_btn_clicked)
        self.tool_btn.hide()  # 初始未选时隐藏按钮

        self.lineEdit().installEventFilter(self)  # 拦截(readOnly后失去鼠标事件)实现点击弹窗
        self.dateTimeChanged.connect(self._on_date_changed)
        self._update_btn_state(self.dateTime() > self.null_date)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 工具按钮保持右边正方形并垂直居中
        h = self.height()
        y = max(0, (h - self._btn_w) // 2)
        self.tool_btn.setGeometry(self.width() - self._btn_w - 2, y, self._btn_w, self._btn_w)
        self.tool_btn.raise_()

    def eventFilter(self, obj, event):
        # 只读下也能点击输入框弹窗
        if obj == self.lineEdit() and event.type() == QtCore.QEvent.Type.MouseButtonRelease:
            if not self.tool_btn.underMouse():
                self._open_picker()
            return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        # 点击整个控件区域也触发弹窗
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            if not self.tool_btn.underMouse():
                self._open_picker()
                return
        super().mousePressEvent(event)

    def _on_date_changed(self, dt):
        self._update_btn_state(dt > self.null_date)

    def _update_btn_state(self, is_valid: bool):
        """有有效值时显示'✕'按钮，无效值时隐藏。"""
        if is_valid:
            self.tool_btn.setText("✕")
            self.tool_btn.setToolTip("清空")
            self.tool_btn.show()
        else:
            self.tool_btn.hide()

    def _on_tool_btn_clicked(self):
        # 清空已选
        self.setDateTime(self.null_date)
        self.setSpecialValueText("请选择日期")

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
        self._on_tool_btn_clicked()

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