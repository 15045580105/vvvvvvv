from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt as _Qt


__all__ = ["ModernButton", "create_icon", "TableButton", "LoadingSpinner", "CheckableComboBox", "ResponsiveButtonFlowPanel"]

# Qt compatibility constants for linters/type checkers
QT_TRANSPARENT = getattr(_Qt, "transparent", 0)
QT_NO_PEN = getattr(_Qt, "NoPen", 0)
QT_ALIGN_CENTER = getattr(_Qt, "AlignCenter", 0)
QT_CURSOR_POINTING = getattr(_Qt, "PointingHandCursor", 13)
QT_CURSOR_ARROW = getattr(_Qt, "ArrowCursor", 0)
QT_WINDOW_POPUP = getattr(_Qt, "Popup", 0)
QT_WINDOW_FRAMELESS = getattr(_Qt, "FramelessWindowHint", 0)
QT_WINDOW_NO_SHADOW = getattr(_Qt, "NoDropShadowWindowHint", 0)
QT_ATTR_TRANSLUCENT_BG = getattr(_Qt, "WA_TranslucentBackground", 0)
QT_ITEM_IS_ENABLED = getattr(_Qt, "ItemIsEnabled", 1 << 5)
QT_ITEM_IS_USER_CHECKABLE = getattr(_Qt, "ItemIsUserCheckable", 1 << 4)
QT_CHECKSTATE_ROLE = getattr(_Qt, "CheckStateRole", 10)
QT_CHECKED = getattr(_Qt, "Checked", 2)
QT_UNCHECKED = getattr(_Qt, "Unchecked", 0)
QT_EVENT_MOUSE_BUTTON_PRESS = getattr(QtCore.QEvent, "MouseButtonPress", 2)
QT_EVENT_MOUSE_BUTTON_RELEASE = getattr(QtCore.QEvent, "MouseButtonRelease", 3)


def create_icon(emoji: str, color: str):
    pixmap = QtGui.QPixmap(20, 20)
    pixmap.fill(QT_TRANSPARENT)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setPen(QT_NO_PEN)
    painter.setBrush(QtGui.QColor(color))
    painter.drawEllipse(pixmap.rect().adjusted(1, 1, -1, -1))
    painter.setPen(QtGui.QColor("white"))
    painter.setFont(QtGui.QFont("Segoe UI Emoji", 10))
    painter.drawText(pixmap.rect(), QT_ALIGN_CENTER, emoji)
    painter.end()
    return QtGui.QIcon(pixmap)


class ModernButton(QtWidgets.QPushButton):
    def __init__(self, text: str, color: str = "#3B82F6", icon_emoji: str = "", *, dense: bool = False):
        super().__init__()
        self.color = QtGui.QColor(color)
        self.dense = dense
        self.setCursor(QT_CURSOR_POINTING)
        # 高度根据密集模式调整
        self.setMinimumHeight(26 if self.dense else 32)
        font = QtGui.QFont("Segoe UI", 9)
        font.setStyleStrategy(QtGui.QFont.PreferAntialias)
        self.setFont(font)
        if icon_emoji:
            self.setText(f"{icon_emoji} {text}")
        else:
            self.setText(text)
        self.update_style()

    def update_style(self):
        hover_color = self.color.lighter(110).name()
        pressed_color = self.color.darker(110).name()
        # 密集模式下使用更小的内边距与圆角；移除最小宽度
        padding_v, padding_h = (4, 10) if self.dense else (8, 16)
        radius = 4 if self.dense else 6
        min_width = "0" if self.dense else "90px"
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.color.name()};
                color: white;
                border: none;
                padding: {padding_v}px {padding_h}px;
                border-radius: {radius}px;
                font-weight: 500;
                min-width: {min_width};
                font-family: "Segoe UI", "Microsoft YaHei";
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {pressed_color};
            }}
            QPushButton:disabled {{
                background-color: #E5E7EB;
                color: #9CA3AF;
            }}
            QToolTip {{
                background-color: #1F2937;
                color: white;
                border: 1px solid #1F2937;
                border-radius: 4px;
                padding: 4px;
                opacity: 230;
            }}
        """)


class TableButton(QtWidgets.QPushButton):
    """紧凑型按钮：用于表格单元格内，固定高度、无最小宽度，避免随列宽拉伸。"""

    def __init__(self, text: str, color: str = "#3B82F6", icon_emoji: str = ""):
        super().__init__()
        self._base_color = QtGui.QColor(color)
        self.setCursor(QT_CURSOR_POINTING)
        # 表格内按钮固定高度，小内边距，无最小宽度，固定尺寸策略
        self.setFixedHeight(28)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        font = QtGui.QFont("Segoe UI", 9)
        font.setStyleStrategy(QtGui.QFont.PreferAntialias)
        self.setFont(font)
        self.setText(f"{icon_emoji} {text}" if icon_emoji else text)
        self._apply_style()

    def _apply_style(self):
        hover = self._base_color.lighter(110).name()
        pressed = self._base_color.darker(110).name()
        base = self._base_color.name()
        # 注意：min-width: 0 以确保不会被拉伸；更小的 padding 和圆角
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {base};
                color: white;
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: 500;
                min-width: 0;
                font-family: "Segoe UI", "Microsoft YaHei";
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {pressed};
            }}
        """)


class ResponsiveButtonFlowPanel(QtWidgets.QWidget):
    """表格单元格内的响应式按钮面板：空间不足时自动换行，避免按钮挤压重叠。"""

    heightChanged = QtCore.pyqtSignal()

    def __init__(self, parent=None, *, spacing: int = 8, margins=(4, 4, 4, 4), row_spacing: int = 6):
        super().__init__(parent)
        self._buttons = []
        self._spacing = spacing
        self._row_spacing = row_spacing
        self._margins = margins
        self._last_height = 0
        self._compact_mode = False
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.setMinimumHeight(36)

    def add_button(self, button: QtWidgets.QAbstractButton):
        button.setParent(self)
        button.show()
        self._buttons.append(button)
        self._relayout_buttons()

    def buttons(self):
        return list(self._buttons)

    def set_compact_mode(self, compact: bool):
        compact = bool(compact)
        if self._compact_mode == compact:
            return
        self._compact_mode = compact
        self._spacing = 4 if compact else 8
        self._row_spacing = 4 if compact else 6
        self._margins = (2, 2, 2, 2) if compact else (4, 4, 4, 4)
        for btn in self._buttons:
            if hasattr(btn, "setText"):
                full_text = btn.property("full_text")
                compact_text = btn.property("compact_text")
                if compact and compact_text:
                    btn.setText(compact_text)
                elif full_text:
                    btn.setText(full_text)
            btn.updateGeometry()
        self._relayout_buttons()

    def is_compact_mode(self):
        return self._compact_mode

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout_buttons()

    def showEvent(self, event):
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._relayout_buttons)

    def minimumSizeHint(self):
        return QtCore.QSize(220, self._estimate_height(max(220, self.width())))

    def sizeHint(self):
        return QtCore.QSize(420, self._estimate_height(max(420, self.width())))

    def _estimate_height(self, available_width: int) -> int:
        left, top, right, bottom = self._margins
        usable_width = max(80, available_width - left - right)
        line_width = 0
        line_height = 0
        total_height = top + bottom
        line_count = 0
        visible_buttons = [btn for btn in self._buttons if btn.isVisible()]
        if not visible_buttons:
            return max(36, total_height)
        for btn in visible_buttons:
            hint = btn.sizeHint()
            bw = hint.width()
            bh = hint.height()
            next_width = bw if line_width == 0 else line_width + self._spacing + bw
            if line_width and next_width > usable_width:
                total_height += line_height
                line_count += 1
                line_width = bw
                line_height = bh
            else:
                line_width = next_width
                line_height = max(line_height, bh)
        total_height += line_height
        line_count += 1
        total_height += max(0, line_count - 1) * self._row_spacing
        return max(36, total_height)

    def _relayout_buttons(self):
        left, top, right, bottom = self._margins
        available_width = max(80, self.width() - left - right)
        x = left
        y = top
        line_height = 0
        visible_buttons = [btn for btn in self._buttons if btn.isVisible()]
        for btn in visible_buttons:
            hint = btn.sizeHint()
            bw = hint.width()
            bh = hint.height()
            if x > left and (x + bw) > (self.width() - right):
                x = left
                y += line_height + self._row_spacing
                line_height = 0
            btn.setGeometry(x, y, bw, bh)
            x += bw + self._spacing
            line_height = max(line_height, bh)
        total_height = max(36, y + line_height + bottom)
        self.setMinimumHeight(total_height)
        if self._last_height != total_height:
            self._last_height = total_height
            self.heightChanged.emit()
        self.updateGeometry()

# 加载动画控件
class LoadingSpinner(QtWidgets.QWidget):
    def __init__(self, parent=None, size=16, color="#3B82F6"):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._color = QtGui.QColor(color)
        self._angle = 0
        self._timer =  QtCore.QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(50)  # 20 FPS

    def _rotate(self):
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        rect = self.rect().adjusted(2, 2, -2, -2)
        pen = QtGui.QPen(self._color)
        pen.setWidth(2)
        painter.setPen(pen)

        # Draw a spinning arc (approx 270 degrees)
        start_angle = -self._angle * 16
        span_angle = 270 * 16
        painter.drawArc(rect, start_angle, span_angle)
        painter.end()

    def set_color(self, color):
        self._color = QtGui.QColor(color)
        self.update()

#多选下拉框
class CheckableComboBox(QtWidgets.QComboBox):
    checkedItemsChanged = QtCore.pyqtSignal(list, str)

    def __init__(self, parent=None):
        # 这两个标记必须在 super().__init__() 之前初始化，
        # 因为 QComboBox.__init__ 可能间接触发 hidePopup/showPopup。
        self._is_updating = False
        self._toggling = False
        super(CheckableComboBox, self).__init__(parent)

        self.setView(QtWidgets.QListView())
        # 关键改动：使用 Qt.Tool 替代 Qt.Popup。
        # Qt.Popup 会抢夺全局鼠标事件，导致点击 lineEdit 时先关闭 popup 再到达
        # lineEdit 的 eventFilter，无法实现 toggle（点一次展开、再点一次收起）。
        # Qt.Tool 不抢夺鼠标，点击 lineEdit 时 popup 仍然可见，toggle 逻辑可以正确判断。
        # 点击外部区域的关闭行为由 eventFilter 中的全局事件检测手动实现。
        popup_flags = getattr(QtCore.Qt, "Tool", 0)
        frameless = getattr(QtCore.Qt, "FramelessWindowHint", 0)
        no_shadow = getattr(QtCore.Qt, "NoDropShadowWindowHint", 0)
        self.view().window().setWindowFlags(popup_flags | frameless | no_shadow)
        self.view().window().setAttribute(QT_ATTR_TRANSLUCENT_BG)

        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText("请选择选项...")
        self.lineEdit().setCursor(QT_CURSOR_POINTING)

        self.model = QtGui.QStandardItemModel(self)
        self.setModel(self.model)

        self.model.itemChanged.connect(self.onItemChanged)
        self.lineEdit().installEventFilter(self)
        self.view().viewport().installEventFilter(self)
        self.installEventFilter(self)  # 拦截 combobox 自身（边框/箭头区域）的点击

        # Add Select All item
        self.selectAllItem = QtGui.QStandardItem("(全选)")
        self.selectAllItem.setFlags(QT_ITEM_IS_ENABLED | QT_ITEM_IS_USER_CHECKABLE)
        self.selectAllItem.setData(QT_UNCHECKED, QT_CHECKSTATE_ROLE)
        self.model.appendRow(self.selectAllItem)

        # Clear text initially
        self.setCurrentIndex(-1)
        self.lineEdit().setText("")

    def _checked_items(self):
        texts = []
        for i in range(1, self.model.rowCount()):
            item = self.model.item(i)
            if item.checkState() == QT_CHECKED:
                texts.append(item.text())
        return texts

    def _compose_display_text(self, texts):
        if len(texts) == 0:
            return "---"
        return ", ".join(texts)

    def _sync_line_edit_text(self):
        texts = self._checked_items()
        text_str = self._compose_display_text(texts)
        self.blockSignals(True)
        self.setCurrentIndex(-1)
        self.blockSignals(False)
        self.lineEdit().blockSignals(True)
        self.lineEdit().setText(text_str)
        self.lineEdit().blockSignals(False)
        self.checkedItemsChanged.emit(texts, text_str)

    def setCheckedItems(self, texts):
        normalized = {str(text).strip() for text in (texts or []) if str(text).strip()}
        self._is_updating = True
        try:
            for i in range(1, self.model.rowCount()):
                item = self.model.item(i)
                state = QT_CHECKED if item.text() in normalized else QT_UNCHECKED
                item.setCheckState(state)
            self.checkSelectAllState()
        finally:
            self._is_updating = False
        self._sync_line_edit_text()

    def setEnabled(self, enabled):
        super(CheckableComboBox, self).setEnabled(enabled)
        if self.lineEdit() is not None:
            self.lineEdit().setEnabled(enabled)
            cursor_shape = QT_CURSOR_POINTING if enabled else QT_CURSOR_ARROW
            self.lineEdit().setCursor(cursor_shape)
        if self.view() is not None:
            self.view().setEnabled(enabled)

    def showPopup(self):
        if not self.isEnabled():
            return
        super(CheckableComboBox, self).showPopup()
        # 安装全局事件过滤器：因为 Qt.Tool 不像 Qt.Popup 那样自动在点击外部时关闭，
        # 所以需要手动检测外部点击来关闭弹出层。
        app = QtWidgets.QApplication.instance()
        if app:
            app.removeEventFilter(self)
            app.installEventFilter(self)

    def hidePopup(self):
        super(CheckableComboBox, self).hidePopup()
        # 弹出层关闭后移除全局事件过滤器，避免不必要的事件拦截。
        app = QtWidgets.QApplication.instance()
        if app:
            app.removeEventFilter(self)

    def onItemChanged(self, item):
        if self._is_updating:
            return

        self._is_updating = True
        try:
            if item == self.selectAllItem:
                state = item.checkState()
                for i in range(1, self.model.rowCount()):
                    child = self.model.item(i)
                    if child.checkState() != state:
                        child.setCheckState(state)
            else:
                self.checkSelectAllState()
            self.updateText()
        finally:
            self._is_updating = False

    def checkSelectAllState(self):
        # Determine if all items are checked
        total_items = self.model.rowCount() - 1
        if total_items <= 0:
            return

        checked_count = 0
        for i in range(1, self.model.rowCount()):
            if self.model.item(i).checkState() == QT_CHECKED:
                checked_count += 1

        all_checked = (checked_count == total_items)
        if self.selectAllItem.checkState() == QT_CHECKED and not all_checked:
             self.selectAllItem.setCheckState(QT_UNCHECKED)
        elif self.selectAllItem.checkState() == QT_UNCHECKED and all_checked:
             self.selectAllItem.setCheckState(QT_CHECKED)

    def updateText(self):
        self._sync_line_edit_text()

    def addItem(self, text, data=None):
        item = QtGui.QStandardItem(text)
        item.setData(data)
        item.setFlags(QT_ITEM_IS_ENABLED | QT_ITEM_IS_USER_CHECKABLE)
        item.setData(QT_UNCHECKED, QT_CHECKSTATE_ROLE)
        self.model.appendRow(item)
        # Manually trigger update text just in case, but usually checkSelectAllState handles logic
        # Adding an unchecked item while 'Select All' is checked should uncheck 'Select All'
        if self.selectAllItem.checkState() == QT_CHECKED:
            self.selectAllItem.setCheckState(QT_UNCHECKED)
        else:
            self.updateText()

    def addItems(self, texts):
        for text in texts:
            self.addItem(text)

    def getCheckedItems(self):
        checkedItems = []
        for i in range(1, self.model.rowCount()):
            item = self.model.item(i)
            if item.checkState() == QT_CHECKED:
                checkedItems.append(item.text())
        return checkedItems

    def getCheckedData(self):
        checkedData = []
        for i in range(1, self.model.rowCount()):
            item = self.model.item(i)
            if item.checkState() == QT_CHECKED:
                checkedData.append(item.data())
        return checkedData

    def eventFilter(self, widget, event):
        if not self.isEnabled():
            return False
        if widget == self.lineEdit():
            if event.type() == QT_EVENT_MOUSE_BUTTON_PRESS:
                # 因为 popup 窗口使用 Qt.Tool（不抢夺鼠标），点击 lineEdit 时
                # popup 仍然可见，_toggle_popup 能正确判断展开/收起。
                self._toggle_popup()
                # 清除点击产生的文本选中高亮（蓝色填充）
                self.lineEdit().deselect()
                QtCore.QTimer.singleShot(0, self.lineEdit().deselect)
                return True
        elif widget == self:
            # 点击 combobox 边框/箭头区域时也 toggle 弹出层
            if event.type() == QT_EVENT_MOUSE_BUTTON_PRESS:
                line_edit = self.lineEdit()
                if line_edit and line_edit.geometry().contains(event.pos()):
                    return False  # lineEdit 区域由它自己的 eventFilter 处理
                self._toggle_popup()
                return True
        elif widget == self.view().viewport():
            if event.type() == QT_EVENT_MOUSE_BUTTON_RELEASE:
                index = self.view().indexAt(event.pos())
                if index.isValid():
                    item = self.model.itemFromIndex(index)
                    if item.flags() & QT_ITEM_IS_USER_CHECKABLE:
                        new_state = QT_UNCHECKED if item.checkState() == QT_CHECKED else QT_CHECKED
                        item.setCheckState(new_state)
                        QtCore.QTimer.singleShot(0, self._sync_line_edit_text)
                        return True
        # 当通过 app.installEventFilter 安装到全局时，检测外部点击以关闭弹出层
        # （替代 Qt.Popup 自带的“点击外部自动关闭”机制）
        elif isinstance(widget, QtWidgets.QWidget) and widget not in (
            self.lineEdit(), self, self.view().viewport()
        ):
            if event.type() == QtCore.QEvent.MouseButtonPress and self.view().isVisible():
                popup_window = self.view().window()
                global_pos = event.globalPos()
                popup_rect = QtCore.QRect(popup_window.pos(), popup_window.size())
                combo_rect = QtCore.QRect(self.mapToGlobal(QtCore.QPoint(0, 0)), self.size())
                if not popup_rect.contains(global_pos) and not combo_rect.contains(global_pos):
                    self.hidePopup()
        return super(CheckableComboBox, self).eventFilter(widget, event)

    def _toggle_popup(self):
        """统一切换弹出层：已展开则收起，未展开则弹出。

        由于 popup 窗口使用 Qt.Tool 而非 Qt.Popup，点击 lineEdit 时 Qt 不会
        自动关闭弹出层，因此 view().isVisible() 能准确反映弹出层的当前状态，
        实现"点一次展开、再点一次收起"的 toggle 行为。
        """
        self._toggling = True
        try:
            if self.view().isVisible():
                self.hidePopup()
            else:
                self.showPopup()
        finally:
            self._toggling = False


class TagWidget(QtWidgets.QFrame):
    removed = QtCore.pyqtSignal(str)

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        self.setStyleSheet("""
            TagWidget {
                background-color: #E0E7FF;
                border-radius: 4px;
                border: 1px solid #C7D2FE;
            }
        """)

        label = QtWidgets.QLabel(text)
        label.setStyleSheet("color: #3730A3; font-weight: 500;")
        layout.addWidget(label)

        close_btn = QtWidgets.QPushButton("×")
        close_btn.setFixedSize(16, 16)
        close_btn.setCursor(QT_CURSOR_POINTING)
        close_btn.setStyleSheet("""
            QPushButton {
                border: none;
                color: #6B7280;
                font-weight: bold;
                background: transparent;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                color: #EF4444;
            }
        """)
        close_btn.clicked.connect(lambda: self.removed.emit(self.text))
        layout.addWidget(close_btn)

class MultiSelectComboBox(QtWidgets.QWidget):
    selectionChanged = QtCore.pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.selected_items = []

        # 使用水平布局，模拟一个输入框
        self.layout = QtWidgets.QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 主容器，包含标签和下拉箭头
        self.container = QtWidgets.QFrame()
        self.container.setObjectName("MultiSelectContainer")
        self.container.setStyleSheet("""
            #MultiSelectContainer {
                background-color: white;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
            }
        """)
        self.container_layout = QtWidgets.QHBoxLayout(self.container)
        self.container_layout.setContentsMargins(2, 2, 2, 2)
        self.container_layout.setSpacing(4)

        # 标签区域
        self.tags_widget = QtWidgets.QWidget()
        self.tags_layout = QtWidgets.QHBoxLayout(self.tags_widget)
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_layout.setSpacing(4)
        self.container_layout.addWidget(self.tags_widget)

        # 占位符文本（当没有选择时显示）
        self.placeholder_label = QtWidgets.QLabel("请选择...")
        self.placeholder_label.setStyleSheet("color: #9CA3AF;")
        self.container_layout.addWidget(self.placeholder_label)

        self.container_layout.addStretch()

        # 下拉按钮（模拟 ComboBox 的箭头）
        self.arrow_btn = QtWidgets.QPushButton("▼")
        self.arrow_btn.setFixedSize(20, 20)
        self.arrow_btn.setCursor(QT_CURSOR_POINTING)
        self.arrow_btn.setStyleSheet("""
            QPushButton {
                border: none;
                color: #6B7280;
                background: transparent;
                font-size: 10px;
            }
        """)
        self.arrow_btn.clicked.connect(self._show_popup)
        self.container_layout.addWidget(self.arrow_btn)

        self.layout.addWidget(self.container)

        # 弹出菜单
        self.popup_menu = QtWidgets.QMenu(self)
        self.popup_menu.setStyleSheet("""
            QMenu {
                background-color: white;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 2px;
            }
            QMenu::item:selected {
                background-color: #F3F4F6;
                color: #111827;
            }
        """)

    def addItems(self, items):
        self.items = items
        self._update_popup_menu()

    def _update_popup_menu(self):
        self.popup_menu.clear()
        for item in self.items:
            if item not in self.selected_items:
                action = self.popup_menu.addAction(item)
                action.triggered.connect(lambda checked, txt=item: self._on_item_selected(txt))

        if not self.items or len(self.selected_items) == len(self.items):
             disabled_action = self.popup_menu.addAction("无更多选项")
             disabled_action.setEnabled(False)

    def _show_popup(self):
        self._update_popup_menu()
        # 在容器下方显示菜单
        pos = self.mapToGlobal(self.container.geometry().bottomLeft())
        self.popup_menu.setMinimumWidth(self.container.width())
        self.popup_menu.exec_(pos)

    def _on_item_selected(self, text):
        if text in self.selected_items:
            return

        self.selected_items.append(text)
        self._add_tag(text)
        self._update_placeholder()
        self.selectionChanged.emit(self.selected_items)

    def _add_tag(self, text):
        tag = TagWidget(text)
        tag.removed.connect(self._on_tag_removed)
        self.tags_layout.addWidget(tag)

    def _on_tag_removed(self, text):
        if text in self.selected_items:
            self.selected_items.remove(text)

            # Remove widget
            for i in range(self.tags_layout.count()):
                item = self.tags_layout.itemAt(i)
                widget = item.widget()
                if isinstance(widget, TagWidget) and widget.text == text:
                    widget.deleteLater()
                    break

            self._update_placeholder()
            self.selectionChanged.emit(self.selected_items)

    def _update_placeholder(self):
        if self.selected_items:
            self.placeholder_label.hide()
        else:
            self.placeholder_label.show()

    def currentSelection(self):
        return self.selected_items

    def setSelection(self, items):
        # Clear existing
        self.selected_items = []
        # Remove all tag widgets
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for item in items:
            if item in self.items:
                self.selected_items.append(item)
                self._add_tag(item)

        self._update_placeholder()
