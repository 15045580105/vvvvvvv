from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, QPoint, pyqtSignal, QEvent
from PyQt5.QtCore import pyqtProperty
from PyQt5.QtGui import QColor, QPainter, QStandardItem, QStandardItemModel, QMouseEvent
from PyQt5.QtWidgets import QWidget, QFrame, QHBoxLayout, QLabel, QGraphicsDropShadowEffect, QDialog, QVBoxLayout, QPushButton, QLineEdit, QComboBox, QStyledItemDelegate, QListView, QAbstractItemView


class SmoothToggle(QWidget):
    """
    iOS 风格的平滑切换开关
    """
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 28)
        self.setCursor(Qt.PointingHandCursor)
        self._checked = False
        self._thumb_x = 3.0

        # 动画属性
        self._anim = QPropertyAnimation(self, b"thumb_x", self)
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    @pyqtProperty(float)
    def thumb_x(self):
        return self._thumb_x

    @thumb_x.setter
    def thumb_x(self, val):
        self._thumb_x = val
        self.update()

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        self._checked = checked
        self._thumb_x = self.width() - 25.0 if checked else 3.0
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._checked = not self._checked
            self._anim.setStartValue(self._thumb_x)
            self._anim.setEndValue(self.width() - 25.0 if self._checked else 3.0)
            self._anim.start()
            self.toggled.emit(self._checked)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # 绘制轨道
        # 开是绿色(#10B981)，关是红色(#EF4444)
        color = QColor("#10B981") if self._checked else QColor("#EF4444")
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 14, 14)

        # 绘制滑块
        p.setBrush(Qt.white)
        p.drawEllipse(int(self._thumb_x), 3, 22, 22)


class MessageToast(QWidget):
    """
    顶部浮动通知条，带圆角阴影和下落动画
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._click_handler = None

        # 布局 margin 给阴影留空间
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)

        # 实际的背景容器
        self.container = QFrame()
        self.container.setObjectName("ToastContainer")

        # 阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 5)
        self.container.setGraphicsEffect(shadow)

        # 内部内容
        cl = QHBoxLayout(self.container)
        cl.setContentsMargins(20, 10, 20, 10)

        self.icon_lbl = QLabel()
        self.icon_lbl.setStyleSheet("font-size: 13.5pt; background: transparent; border: none;")
        self.msg_lbl = QLabel()
        self.msg_lbl.setStyleSheet(
            "color: white; font-weight: bold; font-size: 10.5pt; background: transparent; border: none; margin-left: 5px;")

        cl.addWidget(self.icon_lbl)
        cl.addWidget(self.msg_lbl)
        self.layout.addWidget(self.container)
        for widget in (self.container, self.icon_lbl, self.msg_lbl):
            widget.installEventFilter(self)

        # 动画设置
        self.anim = QPropertyAnimation(self, b"pos")
        self.timer = QTimer()
        self.timer.timeout.connect(self.hide_anim)

    def show_toast(self, text, message_type=0, on_click=None):
        """
        显示通知
        type: 0:success, 1:error, info
        """
        self._click_handler = on_click if callable(on_click) else None
        self.msg_lbl.setText(text)

        if message_type == 0:
            self.icon_lbl.setText("✅")
            self.container.setStyleSheet("#ToastContainer { background-color: #10B981; border-radius: 20px; }")
        elif message_type == 1:
            self.icon_lbl.setText("❌")
            self.container.setStyleSheet("#ToastContainer { background-color: #EF4444; border-radius: 20px; }")
        else:
            self.icon_lbl.setText("ℹ️")
            self.container.setStyleSheet("#ToastContainer { background-color: #3B82F6; border-radius: 20px; }")

        cursor_shape = Qt.PointingHandCursor if self._click_handler else Qt.ArrowCursor
        self.setCursor(cursor_shape)
        self.container.setCursor(cursor_shape)
        self.icon_lbl.setCursor(cursor_shape)
        self.msg_lbl.setCursor(cursor_shape)

        self.adjustSize()

        # 居中逻辑
        if self.parent():
            pw = self.parent().width()
            x = (pw - self.width()) // 2
        else:
            x = 100

        self.show()

        # 下落动画
        self.anim.setDuration(500)
        self.anim.setEasingCurve(QEasingCurve.OutBack)
        self.anim.setStartValue(QPoint(x, -100))
        self.anim.setEndValue(QPoint(x, 40))
        self.anim.start()

        self.timer.start(2500)  # 显示时间

    def eventFilter(self, watched, event):
        if watched in (self.container, self.icon_lbl, self.msg_lbl) and event.type() == QEvent.MouseButtonRelease:
            if getattr(event, "button", lambda: None)() == Qt.LeftButton:
                self._handle_click()
                return True
        return super().eventFilter(watched, event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._handle_click()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _handle_click(self):
        handler = self._click_handler
        self._click_handler = None
        if self.timer.isActive():
            self.timer.stop()
        if callable(handler):
            try:
                handler()
            except Exception:
                pass
        self.close()

    def hide_anim(self):
        self.timer.stop()
        self.anim.setStartValue(self.pos())
        self.anim.setEndValue(QPoint(self.pos().x(), -100))
        self.anim.setEasingCurve(QEasingCurve.InBack)
        self.anim.finished.connect(self.close)
        self.anim.start()


class ModernConfirmDialog(QDialog):
    """
    现代风格的确认对话框，带遮罩和动画
    """
    def __init__(self, parent, title, content, confirm_text="确定", cancel_text="取消", is_danger=False):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(400, 200)

        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # 容器
        self.container = QFrame()
        self.container.setObjectName("ConfirmContainer")
        self.container.setStyleSheet("""
            #ConfirmContainer {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #E5E7EB;
            }
        """)

        # 阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 5)
        self.container.setGraphicsEffect(shadow)

        layout.addWidget(self.container)

        # 内容布局
        vbox = QVBoxLayout(self.container)
        vbox.setContentsMargins(24, 24, 24, 24)
        vbox.setSpacing(16)

        # 标题
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #111827;")
        vbox.addWidget(self.title_lbl)

        # 内容
        self.content_lbl = QLabel(content)
        self.content_lbl.setWordWrap(True)
        self.content_lbl.setStyleSheet("font-size: 14px; color: #4B5563;")
        vbox.addWidget(self.content_lbl)

        vbox.addStretch()

        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        # 取消按钮
        self.cancel_btn = QPushButton(cancel_text)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setFixedSize(80, 36)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: white;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                color: #374151;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        # 确定按钮
        self.confirm_btn = QPushButton(confirm_text)
        self.confirm_btn.setCursor(Qt.PointingHandCursor)
        self.confirm_btn.setFixedSize(80, 36)

        if is_danger:
            # 危险操作（如删除）用红色
            self.confirm_btn.setStyleSheet("""
                QPushButton {
                    background-color: #EF4444;
                    border: none;
                    border-radius: 6px;
                    color: white;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #DC2626;
                }
            """)
        else:
            # 普通操作用蓝色
            self.confirm_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3B82F6;
                    border: none;
                    border-radius: 6px;
                    color: white;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #2563EB;
                }
            """)

        self.confirm_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.confirm_btn)

        vbox.addLayout(btn_layout)

    def paintEvent(self, event):
        # 绘制半透明遮罩背景
        # 注意：由于是 Dialog，parent 可能是整个窗口，这里简单绘制自身背景
        # 如果想要全屏遮罩，需要更复杂的实现。这里仅做 Dialog 自身的圆角背景。
        # 但为了模拟遮罩，通常 Dialog 是模态的，Qt 会自动处理窗口模态。
        # 这里我们只负责画 Dialog 内部。
        pass


class ModernAboutDialog(QDialog):
    """
    现代风格的关于对话框
    """
    def __init__(self, parent, title, content):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(400, 250)

        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # 容器
        self.container = QFrame()
        self.container.setObjectName("AboutContainer")
        self.container.setStyleSheet("""
            #AboutContainer {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #E5E7EB;
            }
        """)

        # 阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 5)
        self.container.setGraphicsEffect(shadow)

        layout.addWidget(self.container)

        # 内容布局
        vbox = QVBoxLayout(self.container)
        vbox.setContentsMargins(24, 24, 24, 24)
        vbox.setSpacing(16)

        # 标题
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #111827;")
        self.title_lbl.setAlignment(Qt.AlignCenter)
        vbox.addWidget(self.title_lbl)

        # 内容
        self.content_lbl = QLabel(content)
        self.content_lbl.setWordWrap(True)
        self.content_lbl.setStyleSheet("font-size: 14px; color: #4B5563;")
        self.content_lbl.setAlignment(Qt.AlignCenter)
        vbox.addWidget(self.content_lbl)

        vbox.addStretch()

        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        # 确定按钮
        self.confirm_btn = QPushButton("确定")
        self.confirm_btn.setCursor(Qt.PointingHandCursor)
        self.confirm_btn.setFixedSize(100, 36)
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6;
                border: none;
                border-radius: 6px;
                color: white;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #2563EB;
            }
        """)
        self.confirm_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.confirm_btn)
        btn_layout.addStretch()

        vbox.addLayout(btn_layout)


class ModernInputDialog(QDialog):
    """
    现代风格的输入对话框
    """
    def __init__(self, parent, title, label_text, default_text=""):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(400, 220)
        self.text_value = None

        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # 容器
        self.container = QFrame()
        self.container.setObjectName("InputContainer")
        self.container.setStyleSheet("""
            #InputContainer {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #E5E7EB;
            }
        """)

        # 阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 5)
        self.container.setGraphicsEffect(shadow)

        layout.addWidget(self.container)

        # 内容布局
        vbox = QVBoxLayout(self.container)
        vbox.setContentsMargins(24, 24, 24, 24)
        vbox.setSpacing(16)

        # 标题
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #111827;")
        vbox.addWidget(self.title_lbl)

        # 标签
        self.label_lbl = QLabel(label_text)
        self.label_lbl.setStyleSheet("font-size: 14px; color: #4B5563;")
        vbox.addWidget(self.label_lbl)

        # 输入框
        self.input_edit = QLineEdit(default_text)
        self.input_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
                color: #111827;
            }
            QLineEdit:focus {
                border: 1px solid #3B82F6;
            }
        """)
        vbox.addWidget(self.input_edit)

        vbox.addStretch()

        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        # 取消按钮
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setFixedSize(80, 36)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: white;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                color: #374151;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        # 确定按钮
        self.confirm_btn = QPushButton("确定")
        self.confirm_btn.setCursor(Qt.PointingHandCursor)
        self.confirm_btn.setFixedSize(80, 36)
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6;
                border: none;
                border-radius: 6px;
                color: white;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #2563EB;
            }
        """)
        self.confirm_btn.clicked.connect(self.on_confirm)
        btn_layout.addWidget(self.confirm_btn)

        vbox.addLayout(btn_layout)

    def on_confirm(self):
        self.text_value = self.input_edit.text()
        self.accept()

    @staticmethod
    def get_text(parent, title, label, default=""):
        dialog = ModernInputDialog(parent, title, label, default)
        result = dialog.exec_()
        return dialog.text_value, result == QDialog.Accepted


