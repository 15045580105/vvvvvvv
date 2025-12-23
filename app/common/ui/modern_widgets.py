from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, QPoint, pyqtSignal
from PyQt5.QtCore import pyqtProperty
from PyQt5.QtGui import QColor
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QWidget, QFrame, QHBoxLayout, QLabel, QGraphicsDropShadowEffect


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
        self.icon_lbl.setStyleSheet("font-size: 18px; background: transparent; border: none;")
        self.msg_lbl = QLabel()
        self.msg_lbl.setStyleSheet(
            "color: white; font-weight: bold; font-size: 14px; background: transparent; border: none; margin-left: 5px;")

        cl.addWidget(self.icon_lbl)
        cl.addWidget(self.msg_lbl)
        self.layout.addWidget(self.container)

        # 动画设置
        self.anim = QPropertyAnimation(self, b"pos")
        self.timer = QTimer()
        self.timer.timeout.connect(self.hide_anim)

    def show_toast(self, text, message_type=0):
        """
        显示通知
        type: 0:success, 1:error, info
        """
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

    def hide_anim(self):
        self.timer.stop()
        self.anim.setStartValue(self.pos())
        self.anim.setEndValue(QPoint(self.pos().x(), -100))
        self.anim.setEasingCurve(QEasingCurve.InBack)
        self.anim.finished.connect(self.close)
        self.anim.start()
