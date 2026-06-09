from PyQt5 import QtWidgets, QtCore, QtGui


class SplashScreen(QtWidgets.QWidget):
    IMAGE_SCALE_RATIO = 0.5

    def __init__(self, image_path: str):
        super().__init__()
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.SplashScreen)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        source_pixmap = QtGui.QPixmap(image_path)
        if source_pixmap.isNull():
            # Fallback: use screen-dependent size instead of fixed pixels.
            screen = QtWidgets.QApplication.primaryScreen()
            screen_geo = screen.availableGeometry() if screen else QtCore.QRect(0, 0, 1280, 720)
            fallback_w = max(360, int(screen_geo.width() * self.IMAGE_SCALE_RATIO))
            fallback_h = max(220, int(screen_geo.height() * self.IMAGE_SCALE_RATIO))
            self.pixmap = QtGui.QPixmap(fallback_w, fallback_h)
            self.pixmap.fill(QtCore.Qt.white)
        else:
            # Always keep a fixed ratio based on the original image size.
            scaled_w = max(1, int(source_pixmap.width() * self.IMAGE_SCALE_RATIO))
            scaled_h = max(1, int(source_pixmap.height() * self.IMAGE_SCALE_RATIO))
            self.pixmap = source_pixmap.scaled(
                scaled_w,
                scaled_h,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )

        self.resize(self.pixmap.width(), self.pixmap.height())

        self.progress = 0
        self.target_progress = 0

        # dynamic animation timer
        self.animation_timer = QtCore.QTimer(self)
        self.animation_timer.timeout.connect(self._animate_progress)
        self.animation_timer.start(16)  # ~60fps

    def set_progress(self, value: int):
        self.target_progress = min(max(value, 0), 100)

    def _animate_progress(self):
        if self.progress < self.target_progress:
            # simple easing
            step = max(1.0, (self.target_progress - self.progress) * 0.1)
            self.progress = min(self.progress + step, self.target_progress)
            self.update()

    def paintEvent(self, event: QtGui.QPaintEvent):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # 页面边框圆角
        path = QtGui.QPainterPath()
        rect = QtCore.QRectF(self.rect())
        radius = 15.0
        path.addRoundedRect(rect, radius, radius)
        painter.setClipPath(path)

        # 绘制背景图片
        painter.drawPixmap(self.rect(), self.pixmap)

        # 绘制底部进度条 (留出边距)
        bar_height = 16
        margin_x = 30
        margin_b = 30
        bar_width = self.width() - 2 * margin_x
        x = margin_x
        y = self.height() - margin_b - bar_height

        # 进度条背景
        painter.setPen(QtCore.Qt.NoPen)
        bg_color = QtGui.QColor(220, 220, 220, 150)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(x, y, bar_width, bar_height, bar_height / 2, bar_height / 2)

        # 进度条前景
        if self.progress > 0:
            fg_width = bar_width * (self.progress / 100.0)
            fg_color = QtGui.QColor(61,140,202)  # 蓝色跑马条
            painter.setBrush(fg_color)
            painter.drawRoundedRect(x, y, int(fg_width), bar_height, bar_height / 2, bar_height / 2)

    def finish(self, main_window):
        if self.animation_timer.isActive():
            self.animation_timer.stop()
        if main_window is not None:
            main_window.raise_()
            main_window.activateWindow()
        self.hide()
        self.close()
        self.deleteLater()
