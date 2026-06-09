from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt


class LogAreaSplitter(QtWidgets.QSplitter):
    """垂直分割布局：上方主内容，下方操作日志，限制日志高度范围。"""

    def __init__(self, parent=None, min_log_height=150, max_log_ratio=0.8, handle_width=8):
        super().__init__(Qt.Vertical, parent)
        self._min_log_height = max(40, int(min_log_height))
        self._max_log_ratio = max(0.1, min(float(max_log_ratio), 0.9))
        self._updating_sizes = False
        self._content_widget = None
        self._log_widget = None
        self._initial_log_height = None
        self._initial_sizes_applied = False

        self.setChildrenCollapsible(False)
        self.setOpaqueResize(True)
        self.setHandleWidth(handle_width)
        self.splitterMoved.connect(self._on_splitter_moved)

        handle = self.handle(1)
        if handle is not None:
            handle.setCursor(Qt.SizeVerCursor)
            handle.setToolTip("上下拖动可调整操作日志区域高度")
            handle.setStyleSheet(
                "QSplitterHandle {"
                "background-color: #E2E8F0;"
                "border-top: 1px solid #CBD5E1;"
                "border-bottom: 1px solid #CBD5E1;"
                "margin: 1px 0;"
                "}"
                "QSplitterHandle:hover { background-color: #CBD5E1; }"
            )

    def set_panels(self, content_widget, log_widget, initial_log_height=150):
        self._content_widget = content_widget
        self._log_widget = log_widget

        self.addWidget(content_widget)
        self.addWidget(log_widget)

        try:
            log_widget.setMinimumHeight(self._min_log_height)
        except Exception:
            pass

        try:
            margins = log_widget.contentsMargins()
            bottom_margin = max(margins.bottom(), 8)
            log_widget.setContentsMargins(margins.left(), margins.top(), margins.right(), bottom_margin)
        except Exception:
            pass

        self.setStretchFactor(0, 1)
        self.setStretchFactor(1, 0)
        
        self._initial_log_height_val = initial_log_height
        if isinstance(initial_log_height, str) and initial_log_height.endswith('%'):
            self._initial_log_height = self._min_log_height # Will be computed in _apply_sizes
        else:
            self._initial_log_height = max(self._min_log_height, int(initial_log_height))
            
        self._initial_sizes_applied = False
        self._apply_initial_sizes(initial_log_height)

    def _total_available_height(self):
        total = self.height()
        if total <= 0:
            total = self.sizeHint().height()
        if total <= 0 and self.parentWidget() is not None:
            total = self.parentWidget().height()
        return max(total, self._min_log_height * 2)

    def _handle_total_height(self):
        return max(0, self.handleWidth())

    def _content_min_height(self):
        if self._content_widget is None:
            return 0
        candidates = []
        try:
            min_height = int(self._content_widget.minimumHeight())
            if min_height > 0:
                candidates.append(min_height)
        except Exception:
            pass
        try:
            min_size = self._content_widget.minimumSizeHint()
            min_size_height = int(min_size.height())
            if min_size_height > 0:
                candidates.append(min_size_height)
        except Exception:
            pass
        return max(0, max(candidates) if candidates else 0)

    def _max_log_height(self):
        total = self._total_available_height()
        max_by_ratio = int(total * self._max_log_ratio)
        available_after_content_min = total - self._content_min_height() - self._handle_total_height()
        available_after_content_min = max(self._min_log_height, available_after_content_min)
        return max(self._min_log_height, min(max_by_ratio, available_after_content_min))

    def _clamp_log_height(self, desired_height):
        total = self._total_available_height()
        usable_total = max(1, total - self._handle_total_height())
        min_log = min(self._min_log_height, usable_total)
        max_log = min(self._max_log_height(), usable_total)
        if max_log < min_log:
            max_log = min_log
        return max(min_log, min(int(desired_height), max_log))

    def _apply_sizes(self, log_height):
        if self.count() < 2:
            return
        total = self._total_available_height()

        if isinstance(log_height, str) and log_height.endswith('%'):
            try:
                ratio = float(log_height[:-1]) / 100.0
                log_height = int(total * ratio)
            except ValueError:
                log_height = self._min_log_height

        handle_total = self._handle_total_height()
        usable_total = max(1, total - handle_total)
        log_height = self._clamp_log_height(log_height)
        content_height = max(1, usable_total - log_height)
        self._updating_sizes = True
        self.setSizes([content_height, log_height])
        self._updating_sizes = False

    def _apply_initial_sizes(self, initial_log_height):
        self._apply_sizes(initial_log_height)

    def _current_log_height(self):
        if self.count() < 2:
            return self._min_log_height
        sizes = self.sizes()
        if len(sizes) >= 2:
            return sizes[1]
        return self._min_log_height

    def _on_splitter_moved(self, pos, index):
        if self._updating_sizes or index != 1:
            return
        self._apply_sizes(self._current_log_height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.count() < 2 or self._updating_sizes:
            return
        if not self._initial_sizes_applied:
            QtCore.QTimer.singleShot(0, self._ensure_initial_sizes)
            return
        QtCore.QTimer.singleShot(0, lambda: self._apply_sizes(self._current_log_height()))

    def _ensure_initial_sizes(self):
        if self.count() < 2:
            return
        if self._initial_sizes_applied:
            return
        val = getattr(self, '_initial_log_height_val', self._initial_log_height)
        self._apply_sizes(val if val else self._min_log_height)
        self._initial_sizes_applied = True

    def set_initial_log_height(self, height):
        self._initial_log_height_val = height
        if isinstance(height, str) and height.endswith('%'):
            self._initial_log_height = self._min_log_height
        else:
            self._initial_log_height = max(self._min_log_height, int(height))
        self._initial_sizes_applied = False
        QtCore.QTimer.singleShot(0, self._ensure_initial_sizes)
