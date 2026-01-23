"""Reusable checkbox-in-header implementation for QTableView.

Goal
----
Provide a *view-layer* header with a select-all checkbox in section 0, plus a small
controller that syncs the checkbox state <-> model row check states.

This deliberately avoids baking business logic into models.

Model contract (capability-based)
--------------------------------
A model is considered "checkable" when:
- Column 0 exposes Qt.CheckStateRole
- setData(index, state, Qt.CheckStateRole) updates that row

Optional (recommended) fast-path:
- model.set_all_checked(checked: bool) or model.select_all(checked: bool)

"""

from __future__ import annotations

from PyQt5 import QtCore, QtWidgets, QtGui


class CheckBoxHeaderView(QtWidgets.QHeaderView):
    """
    带复选框的表头视图。
    功能：
    1. 在第一列（section 0）绘制一个复选框和自定义标签。
    2. 处理点击事件：只有点击复选框或标签时才切换状态，点击其他区域保留默认行为（如排序）。
    3. 完全自定义绘制第一列，忽略 Model 返回的 headerData，避免重叠。
    """

    sig_check_toggled = QtCore.pyqtSignal(int)  # 信号：发射新的状态 (Qt.Checked / Qt.Unchecked)

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._check_state = QtCore.Qt.Unchecked
        self.setSectionsClickable(True)
        self._label = "全选"

    def setLabel(self, text: str):
        self._label = str(text or "")
        self.viewport().update()

    def setCheckState(self, state: int):
        if state == self._check_state:
            return
        self._check_state = state
        self.viewport().update()

    def checkState(self) -> int:
        return int(self._check_state)

    def _get_layout_rects(self, header_rect: QtCore.QRect, style, opt):
        """计算复选框和文本的绘制区域，水平居中"""
        indicator_w = style.pixelMetric(QtWidgets.QStyle.PM_IndicatorWidth, opt, self) or 16
        indicator_h = style.pixelMetric(QtWidgets.QStyle.PM_IndicatorHeight, opt, self) or 16
        gap = 6

        # 1. 计算文本宽度
        text_w = 0
        if self._label:
            fm = self.fontMetrics()
            text_w = fm.boundingRect(self._label).width()

        # 2. 计算总内容宽度
        total_w = indicator_w
        if text_w > 0:
            total_w += gap + text_w

        # 3. 计算起始X, 使得内容居中
        # 可用区域的中心x
        center_x = header_rect.x() + header_rect.width() // 2
        start_x = int(center_x - total_w / 2)

        # 保护：不要超出左边距太少，至少留点间距
        margin_left = 6
        if start_x < header_rect.x() + margin_left:
            start_x = header_rect.x() + margin_left

        # 4. 计算 Checkbox Rect
        check_y = header_rect.y() + (header_rect.height() - indicator_h) // 2
        check_rect = QtCore.QRect(start_x, check_y, indicator_w, indicator_h)

        # 5. 计算 Text Rect
        text_rect = QtCore.QRect()
        if text_w > 0:
            text_x = start_x + indicator_w + gap
            text_rect = QtCore.QRect(
                text_x,
                header_rect.y(),
                text_w + 4,  # slightly wider for safety
                header_rect.height()
            )

        return check_rect, text_rect

    def paintSection(self, painter: QtGui.QPainter, rect: QtCore.QRect, logicalIndex: int):
        # 如果不是第一列，直接调用父类方法绘制
        if logicalIndex != 0:
            super().paintSection(painter, rect, logicalIndex)
            return

        # 如果是第一列，完全接管绘制，以避免和 Model 的 headerData 内容重叠
        painter.save()

        # 1. 绘制 Header 背景 (CE_HeaderSection)
        # 我们需要构造一个 QStyleOptionHeader 并清空 text，以只绘制背景
        opt = QtWidgets.QStyleOptionHeader()
        opt.initFrom(self)
        opt.rect = rect
        opt.section = logicalIndex
        opt.textAlignment = QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter


        opt.text = ""
        opt.icon = QtGui.QIcon()

        # 设置状态
        state = QtWidgets.QStyle.State_None
        if self.isEnabled():
            state |= QtWidgets.QStyle.State_Enabled
        if self.window().isActiveWindow():
            state |= QtWidgets.QStyle.State_Active
        # (可选) 如果需要 hover 效果，可以判断 cursor 位置，但这里保持简单
        if self.sortIndicatorSection() == logicalIndex:
            if self.sortIndicatorOrder() == QtCore.Qt.AscendingOrder:
                opt.sortIndicator = QtWidgets.QStyleOptionHeader.SortUp
            else:
                opt.sortIndicator = QtWidgets.QStyleOptionHeader.SortDown

        opt.state |= state

        style = self.style() or QtWidgets.QApplication.style()
        # 绘制背景和边框
        style.drawControl(QtWidgets.QStyle.CE_HeaderSection, opt, painter, self)

        # 2. 绘制 Checkbox
        check_opt = QtWidgets.QStyleOptionButton()
        check_opt.initFrom(self)
        check_opt.state |= QtWidgets.QStyle.State_Enabled
        if self._check_state == QtCore.Qt.Checked:
            check_opt.state |= QtWidgets.QStyle.State_On
        else:
            check_opt.state |= QtWidgets.QStyle.State_Off

        check_rect, text_rect = self._get_layout_rects(rect, style, check_opt)
        check_opt.rect = check_rect

        style.drawPrimitive(QtWidgets.QStyle.PE_IndicatorCheckBox, check_opt, painter, self)

        # 3. 绘制文本 "全选" (或其他Label)
        if self._label and not text_rect.isEmpty():
            # 获取合适的文本颜色
            # 通常 Header 的文本颜色可能跟 ButtonText 不一样，保险起见用 WindowText 或 ButtonText
            # 也可以尝试从 opt.palette 获取
            color = opt.palette.color(QtGui.QPalette.ButtonText)
            painter.setPen(color)

            painter.drawText(text_rect, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, self._label)

        # 4. 如果有排序需求且当前是排序列，可以额外画排序箭头
        # QHeaderView 默认的 drawControl(CE_HeaderSection) 其实已经画了箭头（如果 opt.sortIndicator 被设置）
        # 所以只要上面的 opt 设置了 sortIndicator 即可。

        painter.restore()

    def mouseReleaseEvent(self, event):
        # 获取点击的列索引
        logicalIndex = self.logicalIndexAt(event.pos())

        if logicalIndex == 0:
            # 获取该列在 Viewport 中的视觉位置和大小
            # 注意：sectionViewportPosition 返回的是 header viewport 坐标系下的 x
            x = self.sectionViewportPosition(logicalIndex)
            y = 0
            w = self.sectionSize(logicalIndex)
            h = self.height()
            rect = QtCore.QRect(x, y, w, h)

            # 准备参数以计算热区
            style = self.style() or QtWidgets.QApplication.style()
            opt = QtWidgets.QStyleOptionButton()
            opt.initFrom(self)

            check_rect, text_rect = self._get_layout_rects(rect, style, opt)

            # 计算文字区域（粗略估计，为了让点文字也能勾选）
            click_area = check_rect
            if not text_rect.isEmpty():
                # 文字区域加宽一点便于点击
                expanded_text_rect = text_rect.adjusted(0, 0, 10, 0)
                click_area = check_rect.united(expanded_text_rect)

            # 判断点击点是否在复选框或文字区域内
            if click_area.contains(event.pos()):
                # 切换状态
                new_state = QtCore.Qt.Unchecked if self._check_state == QtCore.Qt.Checked else QtCore.Qt.Checked
                self.setCheckState(new_state)
                self.sig_check_toggled.emit(int(new_state))

                # 标记事件已处理，不再传递给父类（防止触发排序等）
                event.accept()
                return

        # 如果点的不是第一列，或者是第一列的空白处，则调用父类默认行为（如排序）
        super().mouseReleaseEvent(event)


class CheckableHeaderController(QtCore.QObject):
    """Binds CheckBoxHeaderView <-> a table model's row check states (col 0)."""

    def __init__(self, table: QtWidgets.QTableView, header: CheckBoxHeaderView, *, check_column: int = 0):
        super().__init__(table)
        self._table = table
        self._header = header
        self._check_column = check_column
        self._auto = False

        self._header.sig_check_toggled.connect(self._on_header_toggled)

    def bind_model(self, model: QtCore.QAbstractItemModel):
        # disconnect old
        try:
            self._table.model().dataChanged.disconnect(self._on_model_data_changed)
            self._table.model().modelReset.disconnect(self._sync_from_model)
            self._table.model().rowsInserted.disconnect(self._sync_from_model)
            self._table.model().rowsRemoved.disconnect(self._sync_from_model)
        except Exception:
            pass

        self._table.setModel(model)
        model.dataChanged.connect(self._on_model_data_changed)
        model.modelReset.connect(self._sync_from_model)
        model.rowsInserted.connect(self._sync_from_model)
        model.rowsRemoved.connect(self._sync_from_model)
        self._sync_from_model()

    def _iter_row_check_states(self, model: QtCore.QAbstractItemModel):
        for r in range(model.rowCount()):
            idx = model.index(r, self._check_column)
            yield idx.data(QtCore.Qt.CheckStateRole) == QtCore.Qt.Checked

    def _sync_from_model(self, *args):
        model = self._table.model()
        if model is None:
            return
        total = model.rowCount()
        if total <= 0:
            self._header.setCheckState(QtCore.Qt.Unchecked)
            return

        checked = sum(1 for v in self._iter_row_check_states(model) if v)
        self._header.setCheckState(QtCore.Qt.Checked if checked == total else QtCore.Qt.Unchecked)

    def _on_model_data_changed(self, top_left: QtCore.QModelIndex, bottom_right: QtCore.QModelIndex, roles=None):
        if self._auto:
            return
        if roles and QtCore.Qt.CheckStateRole not in roles:
            return
        if top_left.column() <= self._check_column <= bottom_right.column():
            self._sync_from_model()

    def _on_header_toggled(self, state: int):
        model = self._table.model()
        if model is None:
            return

        checked = (state == int(QtCore.Qt.Checked))

        self._auto = True
        try:
            # Fast-path if model provides a batch method
            if hasattr(model, "set_all_checked"):
                model.set_all_checked(bool(checked))
            elif hasattr(model, "select_all"):
                model.select_all(bool(checked))
            else:
                # Generic path: setData on each row
                for r in range(model.rowCount()):
                    model.setData(model.index(r, self._check_column), QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked, QtCore.Qt.CheckStateRole)
        finally:
            self._auto = False

        self._sync_from_model()

