"""
可复用的 Table Delegates 模块（放在 app/modules/bus_data_management/view 下，供团队内已有视图复用）
- 提供：CenteredCheckBoxDelegate, ProgressDelegate, StatusDelegate, ActionDelegate
- 目的：把多个 view 中重复的 delegate 抽取为共享组件，减少重复代码，统一样式与行为。
"""
from PyQt5 import QtWidgets, QtCore, QtGui

# 控件尺寸常量（与视图中原始实现一致）
ACTION_BTN_W = 84
ACTION_BTN_H = 30
ACTION_BTN_SPACING = 10
ACTION_COL_HMARGIN = 10
ACTION_COL_WIDTH = ACTION_BTN_W * 2 + ACTION_BTN_SPACING + ACTION_COL_HMARGIN * 2


class CenteredCheckBoxDelegate(QtWidgets.QStyledItemDelegate):
    """在单元格中心绘制复选框并处理点击切换（使用 Qt 的 CheckStateRole）。

    说明:
    - 将复选框绘制在单元格中央，去掉焦点高亮。
    - editorEvent 响应鼠标释放事件，切换 CheckStateRole 的布尔状态。

    兼容性:
    - 依赖模型正确实现对 Qt.CheckStateRole 的读取和写入（model.setData）。
    """
    def paint(self, painter, option, index):
        """绘制复选框。

        参数:
        - painter: QPainter 对象，用于绘制。
        - option: QStyleOptionViewItem，包含单元格绘制选项（矩形、状态等）。
        - index: QModelIndex，指向要绘制的单元格。

        返回: 无。若 index 无效直接返回以跳过绘制。
        """
        if not index.isValid():
            return
        painter.save()
        opt = QtWidgets.QStyleOptionViewItem(option)
        # 去掉聚焦高亮以便绘制更干净
        opt.state &= ~QtWidgets.QStyle.State_HasFocus
        style = opt.widget.style() if opt.widget else QtWidgets.QApplication.style()
        check_state = index.data(QtCore.Qt.CheckStateRole)
        cb_opt = QtWidgets.QStyleOptionButton()
        cb_opt.state |= QtWidgets.QStyle.State_Enabled
        cb_opt.state |= QtWidgets.QStyle.State_On if check_state == QtCore.Qt.Checked else QtWidgets.QStyle.State_Off
        indicator_w = style.pixelMetric(QtWidgets.QStyle.PM_IndicatorWidth, None, opt.widget)
        indicator_h = style.pixelMetric(QtWidgets.QStyle.PM_IndicatorHeight, None, opt.widget)
        r = opt.rect
        x = r.x() + (r.width() - indicator_w) // 2
        y = r.y() + (r.height() - indicator_h) // 2
        cb_opt.rect = QtCore.QRect(x, y, indicator_w, indicator_h)
        style.drawPrimitive(QtWidgets.QStyle.PE_IndicatorCheckBox, cb_opt, painter, opt.widget)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        """处理用户交互事件以切换复选框状态。

        行为:
        - 仅响应鼠标左键释放事件。
        - 从 model 中读取当前的 CheckStateRole 并取反后调用 model.setData 写回。

        参数:
        - event: QEvent（通常是 QMouseEvent）。
        - model: QAbstractItemModel，当前视图关联的模型。
        - option: QStyleOptionViewItem，绘制/事件上下文（未直接使用）。
        - index: QModelIndex，事件发生的单元格索引。

        返回:
        - True 当模型数据已被修改并处理了事件；否则 False。
        """
        if not index.isValid():
            return False
        # 响应鼠标释放事件切换状态
        if event.type() == QtCore.QEvent.MouseButtonRelease and getattr(event, 'button', None) and event.button() == QtCore.Qt.LeftButton:
            state = index.data(QtCore.Qt.CheckStateRole)
            new_state = QtCore.Qt.Unchecked if state == QtCore.Qt.Checked else QtCore.Qt.Checked
            return model.setData(index, new_state, QtCore.Qt.CheckStateRole)
        return False


class ProgressDelegate(QtWidgets.QStyledItemDelegate):
    """绘制自定义进度条（支持从 DisplayRole 中读取像 "12%" 的文本）。

    说明:
    - 从 DisplayRole 中读取文本，解析出百分比数值（容错处理），并在单元格中央绘制带有渐变填充的进度条。
    - 选中行会绘制高亮背景并调整文字颜色。
    """
    def paint(self, painter, option, index):
        """绘制进度条样式的单元格。

        参数:
        - painter: QPainter
        - option: QStyleOptionViewItem
        - index: QModelIndex

        返回: 无。若 index 无效直接返回。
        """
        if not index.isValid():
            return
        if option.state & QtWidgets.QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        text = (index.data(QtCore.Qt.DisplayRole) or "0%").strip()
        pct = 0
        try:
            pct_part = text.split("%", 1)[0]
            pct = int("".join(ch for ch in pct_part if ch.isdigit()) or "0")
        except Exception:
            pct = 0
        pct = max(0, min(100, pct))
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = option.rect.adjusted(8, 12, -8, -12)
        if rect.height() < 12:
            rect = option.rect.adjusted(6, 6, -6, -6)
        radius = max(6, rect.height() // 2)
        track_color = QtGui.QColor("#EEF2FF") if not (option.state & QtWidgets.QStyle.State_Selected) else QtGui.QColor("#DDE7FF")
        track_pen = QtGui.QPen(QtGui.QColor("#CBD5E1"))
        track_pen.setWidth(1)
        painter.setPen(track_pen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(rect, radius, radius)
        if pct > 0:
            fill_w = int(rect.width() * pct / 100)
            fill_rect = QtCore.QRect(rect.x(), rect.y(), fill_w, rect.height())
            fill_path = QtGui.QPainterPath()
            fill_path.addRoundedRect(QtCore.QRectF(fill_rect), radius, radius)
            grad = QtGui.QLinearGradient(fill_rect.topLeft(), fill_rect.topRight())
            grad.setColorAt(0.0, QtGui.QColor("#3B82F6"))
            grad.setColorAt(1.0, QtGui.QColor("#06B6D4"))
            painter.setPen(QtCore.Qt.NoPen)
            painter.fillPath(fill_path, grad)
        painter.setPen(QtGui.QColor("#0F172A") if not (option.state & QtWidgets.QStyle.State_Selected) else option.palette.highlightedText().color())
        font = option.font
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(option.rect, QtCore.Qt.AlignCenter, text)
        painter.restore()


class StatusDelegate(QtWidgets.QStyledItemDelegate):
    """绘制状态 pill（颜色根据状态映射）。

    使用说明:
    - color_map 可以在构造时传入自定义映射表，键为状态文本，值为 (text_color, bg_color) 的元组。
    - paint 会把状态文本绘制在一个圆角的 pill 中心。
    """
    def __init__(self, parent=None, color_map=None):
        """初始化 StatusDelegate。

        参数:
        - parent: 委托的父对象（可选）。
        - color_map: 可选的状态到颜色的映射字典，格式：{"状态": ("#文本色", "#背景色")}
        """
        super().__init__(parent)
        self.color_map = color_map or {
            "未下载": ("#6B7280", "#F3F4F6"),
            "下载中": ("#3B82F6", "#DBEAFE"),
            "已下载": ("#10B981", "#D1FAE5"),
            "下载失败": ("#EF4444", "#FEE2E2"),
            "已取消": ("#F97316", "#FFEDD5"),
        }

    def paint(self, painter, option, index):
        """绘制状态 pill。

        参数:
        - painter: QPainter
        - option: QStyleOptionViewItem
        - index: QModelIndex

        行为:
        - 根据 index 的 DisplayRole 文本从 color_map 中选择颜色，不存在则使用默认灰色样式。
        - 把文本绘制在一个固定大小的圆角矩形中并居中。
        """
        if not index.isValid():
            return
        status = index.data(QtCore.Qt.DisplayRole)
        text_color, bg_color = self.color_map.get(status, ("#6B7280", "#F3F4F6"))
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = option.rect
        pill_rect = QtCore.QRect(0, 0, 80, 24)
        pill_rect.moveCenter(rect.center())
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(pill_rect), 12, 12)
        painter.fillPath(path, QtGui.QColor(bg_color))
        painter.setPen(QtGui.QColor(text_color))
        painter.drawText(pill_rect, QtCore.Qt.AlignCenter, status)
        painter.restore()


class ActionDelegate(QtWidgets.QStyledItemDelegate):
    """渲染两按钮（下载/取消）并通过信号把操作转发出去（携带 path 字符串）。

    特性:
    - 通过 sig_download 和 sig_cancel 发出对应路径的字符串参数，用于视图外部处理下载/取消逻辑。
    - 构造器中可指定 path_col 和 status_col 来适配不同表格列索引布局。
    """
    sig_download = QtCore.pyqtSignal(str)
    sig_cancel = QtCore.pyqtSignal(str)

    def __init__(self, parent=None, path_col=3, status_col=9):
        """初始化 ActionDelegate。

        参数:
        - parent: 父对象（可选）。
        - path_col: 整数，表示包含资源路径的列索引（默认 3）。
        - status_col: 整数，表示包含状态文本的列索引（默认 9）。
        """
        super().__init__(parent)
        self.path_col = path_col
        self.status_col = status_col

    def paint(self, painter, option, index):
        """在单元格内居中绘制两个按钮的外观（不创建实际 QPushButton）。

        参数:
        - painter: QPainter
        - option: QStyleOptionViewItem
        - index: QModelIndex

        行为:
        - 根据状态列判断是否处于下载中，从而决定取消按钮是否可用。
        - 调用内部的 _paint_modern_btn 绘制按钮外观。
        """
        if not index.isValid():
            return
        status_idx = index.sibling(index.row(), self.status_col)
        status = status_idx.data(QtCore.Qt.DisplayRole)
        is_downloading = (status == "下载中")
        spacing = ACTION_BTN_SPACING
        btn_w = ACTION_BTN_W
        btn_h = ACTION_BTN_H
        total_w = 2 * btn_w + spacing
        start_x = option.rect.left() + (option.rect.width() - total_w) // 2
        y = option.rect.top() + (option.rect.height() - btn_h) // 2
        rect_down = QtCore.QRect(start_x, y, btn_w, btn_h)
        rect_cancel = QtCore.QRect(start_x + btn_w + spacing, y, btn_w, btn_h)
        self._paint_modern_btn(painter, rect_down, "#10B981", "⬇️ 下载", True)
        self._paint_modern_btn(painter, rect_cancel, "#EF4444", "✕ 取消", is_downloading)

    def _paint_modern_btn(self, painter, rect, base_color, text, enabled):
        """绘制一个扁平、圆角的按钮外观。

        参数:
        - painter: QPainter
        - rect: QRect 按钮的绘制��形
        - base_color: 字符串，按钮启用时的背景色（例如 "#10B981"）
        - text: 按钮文本
        - enabled: 布尔，是否启用（决定配色）
        """
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        bg = QtGui.QColor(base_color) if enabled else QtGui.QColor("#E5E7EB")
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(rect), 4, 4)
        painter.fillPath(path, bg)
        painter.setPen(QtGui.QColor("white") if enabled else QtGui.QColor("#9CA3AF"))
        painter.drawText(rect, QtCore.Qt.AlignCenter, text)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        """处理按钮点击事件并通过信号转发路径字符串。

        行为:
        - 当用户在下载按钮区域点击时，读取 path_col 列的 DisplayRole 并发出 sig_download(path)。
        - 当用户在取消按钮区域点击且当前状态为 "下载中" 时，发出 sig_cancel(path)。

        参数:
        - event: QEvent
        - model: QAbstractItemModel
        - option: QStyleOptionViewItem
        - index: QModelIndex

        返回:
        - True 如果事件被处理（点击命中某个按钮区域）；否则 False。
        """
        if event.type() == QtCore.QEvent.MouseButtonRelease:
            spacing = ACTION_BTN_SPACING
            btn_w = ACTION_BTN_W
            btn_h = ACTION_BTN_H
            total_w = 2 * btn_w + spacing
            start_x = option.rect.left() + (option.rect.width() - total_w) // 2
            y = option.rect.top() + (option.rect.height() - btn_h) // 2
            rect_down = QtCore.QRect(start_x, y, btn_w, btn_h)
            rect_cancel = QtCore.QRect(start_x + btn_w + spacing, y, btn_w, btn_h)
            pos = event.pos()
            if rect_down.contains(pos):
                path = index.sibling(index.row(), self.path_col).data(QtCore.Qt.DisplayRole)
                self.sig_download.emit(path)
                return True
            elif rect_cancel.contains(pos):
                status_idx = index.sibling(index.row(), self.status_col)
                status = status_idx.data(QtCore.Qt.DisplayRole)
                if status == "下载中":
                    path = index.sibling(index.row(), self.path_col).data(QtCore.Qt.DisplayRole)
                    self.sig_cancel.emit(path)
                return True
        return False
