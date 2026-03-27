from PyQt5 import QtWidgets, QtGui, QtCore


class FloatingLogSearchBar(QtWidgets.QFrame):
    def __init__(self, text_widget, trailing_widgets=None, parent=None):
        super().__init__(parent or text_widget)
        self.text_widget = text_widget
        self.matches = []
        self.current_index = -1
        self._extra_selections = []
        self._trailing_widgets = []
        self._settings_key = f"log_search_state::{self.text_widget.objectName() or self.text_widget.__class__.__name__}::{id(self.text_widget)}"

        self.setObjectName("floatingLogSearchBar")
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setStyleSheet(
            "#floatingLogSearchBar {"
            "background: rgba(255, 255, 255, 245);"
            "border: 1px solid #CBD5E1;"
            "border-radius: 8px;"
            "}"
        )
        self.setWindowFlags(QtCore.Qt.SubWindow)
        self.hide()

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("搜索日志...")
        self.search_edit.setFixedWidth(180)
        self.result_label = QtWidgets.QLabel("0/0")
        self.match_case_check = QtWidgets.QCheckBox("Aa")
        self.match_case_check.setToolTip("区分大小写")
        self.whole_word_check = QtWidgets.QCheckBox("W")
        self.whole_word_check.setToolTip("全字匹配")
        self.prev_btn = QtWidgets.QToolButton()
        self.prev_btn.setText("↑")
        self.next_btn = QtWidgets.QToolButton()
        self.next_btn.setText("↓")
        self.close_btn = QtWidgets.QToolButton()
        self.close_btn.setText("✕")

        for btn in (self.prev_btn, self.next_btn, self.close_btn):
            btn.setAutoRaise(False)
            btn.setFixedSize(28, 28)

        for check in (self.match_case_check, self.whole_word_check):
            check.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))

        layout.addWidget(self.search_edit)
        layout.addWidget(self.result_label)
        layout.addWidget(self.match_case_check)
        layout.addWidget(self.whole_word_check)
        layout.addWidget(self.prev_btn)
        layout.addWidget(self.next_btn)
        for widget in trailing_widgets or []:
            widget.setParent(self)
            layout.addWidget(widget)
            self._trailing_widgets.append(widget)
        layout.addWidget(self.close_btn)

        self.search_edit.textChanged.connect(self.refresh_matches)
        self.search_edit.returnPressed.connect(self.goto_next)
        self.match_case_check.toggled.connect(self.refresh_matches)
        self.whole_word_check.toggled.connect(self.refresh_matches)
        self.prev_btn.clicked.connect(self.goto_prev)
        self.next_btn.clicked.connect(self.goto_next)
        self.close_btn.clicked.connect(self.hide_search)
        self._restore_state()

    def _document(self):
        return self.text_widget.document()

    def show_search(self):
        self._reposition()
        self.show()
        self.raise_()
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def hide_search(self):
        self._save_state()
        self.hide()
        self.text_widget.setFocus()

    def _reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 12
        self.adjustSize()
        x = max(margin, parent.width() - self.width() - margin)
        y = margin
        self.move(x, y)

    def resize_with_parent(self):
        if self.isVisible():
            self._reposition()

    def clear_highlights(self):
        self.matches = []
        self.current_index = -1
        self._extra_selections = []
        self._apply_highlights()
        self.result_label.setText("0/0")
        self._save_state()

    def _find_flags(self):
        flags = QtGui.QTextDocument.FindFlags()
        if self.match_case_check.isChecked():
            flags |= QtGui.QTextDocument.FindCaseSensitively
        if self.whole_word_check.isChecked():
            flags |= QtGui.QTextDocument.FindWholeWords
        return flags

    def _save_state(self):
        settings = QtCore.QSettings("oneboxforgac", "log_search")
        settings.setValue(f"{self._settings_key}/query", self.search_edit.text())
        settings.setValue(f"{self._settings_key}/match_case", self.match_case_check.isChecked())
        settings.setValue(f"{self._settings_key}/whole_word", self.whole_word_check.isChecked())
        settings.setValue(f"{self._settings_key}/visible", self.isVisible())

    def _restore_state(self):
        settings = QtCore.QSettings("oneboxforgac", "log_search")
        query = settings.value(f"{self._settings_key}/query", "", type=str)
        match_case = settings.value(f"{self._settings_key}/match_case", False, type=bool)
        whole_word = settings.value(f"{self._settings_key}/whole_word", False, type=bool)
        self.match_case_check.setChecked(match_case)
        self.whole_word_check.setChecked(whole_word)
        self.search_edit.setText(query)
        if query:
            self.refresh_matches()

    def refresh_matches(self):
        query = self.search_edit.text()
        self.matches = []
        self.current_index = -1
        self._extra_selections = []

        if not query:
            self.clear_highlights()
            return

        doc = self._document()
        cursor = QtGui.QTextCursor(doc)
        fmt = QtGui.QTextCharFormat()
        fmt.setBackground(QtGui.QColor("#FDE68A"))
        fmt.setForeground(QtGui.QColor("#111827"))
        flags = self._find_flags()

        while True:
            cursor = doc.find(query, cursor, flags)
            if cursor.isNull():
                break
            self.matches.append(QtGui.QTextCursor(cursor))
            sel = QtWidgets.QTextEdit.ExtraSelection()
            sel.cursor = QtGui.QTextCursor(cursor)
            sel.format = fmt
            self._extra_selections.append(sel)

        if self.matches:
            self.current_index = 0
        self._apply_highlights()
        self._scroll_to_current()
        self._update_label()
        self._save_state()

    def _apply_highlights(self):
        selections = list(self._extra_selections)
        if self.matches and 0 <= self.current_index < len(self.matches):
            current = QtWidgets.QTextEdit.ExtraSelection()
            current.cursor = QtGui.QTextCursor(self.matches[self.current_index])
            current.format.setBackground(QtGui.QColor("#F59E0B"))
            current.format.setForeground(QtGui.QColor("white"))
            selections.append(current)
        if hasattr(self.text_widget, "setExtraSelections"):
            self.text_widget.setExtraSelections(selections)

    def _scroll_to_current(self):
        if not self.matches or self.current_index < 0:
            return
        cursor = QtGui.QTextCursor(self.matches[self.current_index])
        self.text_widget.setTextCursor(cursor)
        self.text_widget.ensureCursorVisible()

    def _update_label(self):
        total = len(self.matches)
        current = self.current_index + 1 if total and self.current_index >= 0 else 0
        self.result_label.setText(f"{current}/{total}")

    def goto_next(self):
        if not self.matches:
            return
        self.current_index = (self.current_index + 1) % len(self.matches)
        self._apply_highlights()
        self._scroll_to_current()
        self._update_label()

    def goto_prev(self):
        if not self.matches:
            return
        self.current_index = (self.current_index - 1) % len(self.matches)
        self._apply_highlights()
        self._scroll_to_current()
        self._update_label()


class _LogTextEditProxy(QtCore.QObject):
    def __init__(self, text_widget, floating_bar):
        super().__init__(text_widget)
        self.text_widget = text_widget
        self.floating_bar = floating_bar
        self._original_context_menu_policy = text_widget.contextMenuPolicy()
        self._shortcut = QtWidgets.QShortcut(QtGui.QKeySequence.Find, text_widget)
        self._shortcut.activated.connect(self.show_search)
        text_widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        text_widget.customContextMenuRequested.connect(self._show_context_menu)
        text_widget.installEventFilter(self)
        viewport = getattr(text_widget, "viewport", lambda: None)()
        if viewport is not None:
            viewport.installEventFilter(self)

    def show_search(self):
        self.floating_bar.show_search()
        self.floating_bar.refresh_matches()

    def _show_context_menu(self, pos):
        if hasattr(self.text_widget, "createStandardContextMenu"):
            menu = self.text_widget.createStandardContextMenu()
        else:
            menu = QtWidgets.QMenu(self.text_widget)
        menu.addSeparator()
        find_action = menu.addAction("Find\tCtrl+F")
        find_action.triggered.connect(self.show_search)
        menu.exec_(self.text_widget.mapToGlobal(pos))

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Resize:
            self.floating_bar.resize_with_parent()
        elif event.type() == QtCore.QEvent.Show:
            self.floating_bar.resize_with_parent()
            if self.floating_bar.search_edit.text():
                self.floating_bar.refresh_matches()
        elif event.type() == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Escape and self.floating_bar.isVisible():
            self.floating_bar.hide_search()
            return True
        return super().eventFilter(obj, event)


class LogPanelBuilder:
    @staticmethod
    def attach_search(layout, text_widget, trailing_widgets=None):
        floating_bar = FloatingLogSearchBar(text_widget, trailing_widgets=trailing_widgets)
        proxy = _LogTextEditProxy(text_widget, floating_bar)
        text_widget._floating_log_search_bar = floating_bar
        text_widget._floating_log_search_proxy = proxy
        return floating_bar
