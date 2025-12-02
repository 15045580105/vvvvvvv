import logging
from typing import Optional, Type
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtCore import Qt, QEvent

from app.common.ui.constants import PAGE_TEXT_TO_KEY, NAV_STRUCTURE, TAB_PAGES, DIALOG_PAGES
from app.common.ui.style import APP_STYLE
from app.core.base_controller import BaseController
from app.presentation.model.main_window_model import MainModel
from app.presentation.views.main_window_view import MainView

logger = logging.getLogger(__name__)


class MainController(BaseController):

    SEARCH_DEBOUNCE_MS = 300

    def __init__(self) -> None:
        self.model: MainModel = MainModel()
        self.view: MainView = MainView()
        super().__init__(self.model, self.view)
        self._page_text_to_key = PAGE_TEXT_TO_KEY
        self._dialog_keys = {name for name, *_ in DIALOG_PAGES}
        self._search_timer: Optional[QtCore.QTimer] = None
        self._pending_search_text: str = ""
        self._search_result_shown: bool = False
        self._init_ui()
        self._init_search()
        self._init_navigation()

    # ----------------- UI初始化 -----------------
    def _init_ui(self) -> None:
        self.view.setStyleSheet(APP_STYLE)
        self.view.workspace.tabCloseRequested.connect(self.close_tab)
        self._build_pages()

    # ----------------- 搜索相关初始化 -----------------
    def _init_search(self) -> None:
        self.view.search_edit.textChanged.connect(self.on_search_text_changed)
        self.view.search_result_list.itemClicked.connect(self.on_search_result_clicked)
        self.view.search_edit.installEventFilter(self)
        self.view.search_result_list.installEventFilter(self)
        self._search_timer = QtCore.QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(self.SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._do_search)
        QtWidgets.QApplication.instance().focusChanged.connect(self.on_focus_changed)  # type: ignore[attr-defined]

    # ----------------- 导航相关初始化 -----------------
    def _init_navigation(self) -> None:
        self._build_navigation()
        self.view.nav_tree.itemClicked.connect(self.on_nav_item_clicked)

    # ----------------- 页面与Tab构建 -----------------
    def _build_pages(self) -> None:
        for reg_name, tab_name, ctrl_cls in TAB_PAGES:
            ctrl = self._safe_instantiate(ctrl_cls)
            if ctrl is not None:
                self.model.register(reg_name, ctrl)
                try:
                    view_widget = getattr(ctrl, 'get_view', None)
                    if callable(view_widget):
                        self.view.workspace.addTab(view_widget(), tab_name)
                except Exception:
                    logger.exception(f"Add tab failed: {reg_name}")
        for reg_name, ctrl_cls in DIALOG_PAGES:
            ctrl = self._safe_instantiate(ctrl_cls)
            if ctrl is not None:
                self.model.register(reg_name, ctrl)

    def _safe_instantiate(self, ctrl_cls: Type) -> Optional[object]:
        try:
            return ctrl_cls(self.view)
        except Exception as exc:
            logger.exception(f"Instantiate controller failed: {ctrl_cls}: {exc}")
            return None

    # ----------------- 导航树构建 -----------------
    def _build_navigation(self) -> None:
        self.view.build_navigation(NAV_STRUCTURE)

    # ----------------- 导航点击 -----------------
    def on_nav_item_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        if item.data(0, Qt.UserRole) != "function":
            return
        display_text = item.text(0)
        reg_key = self._page_text_to_key.get(display_text)
        controller = self.model.get(reg_key) if reg_key else None
        if reg_key in self._dialog_keys and controller is not None:
            try:
                controller.show_dialog()
            except Exception:
                logger.exception(f"Show dialog failed: {reg_key}")
            return
        idx = self._find_tab_index_by_text(display_text)
        if idx is not None:
            self.view.workspace.setCurrentIndex(idx)
            return
        if controller and hasattr(controller, "get_view"):
            self._open_tab_for_controller(controller, display_text)

    def _find_tab_index_by_text(self, display_text: str) -> Optional[int]:
        for i in range(self.view.workspace.count()):
            if self.view.workspace.tabText(i) == display_text:
                return i
        return None

    def _open_tab_for_controller(self, controller: object, display_text: str) -> None:
        try:
            view_widget = getattr(controller, 'get_view', None)
            if callable(view_widget):
                self.view.workspace.addTab(view_widget(), display_text)
                self.view.workspace.setCurrentIndex(self.view.workspace.count() - 1)
        except Exception:
            logger.exception(f"Open tab failed: {display_text}")

    # ----------------- Tab管理 -----------------
    def close_tab(self, index: int) -> None:
        if self.view.workspace.count() > 1:
            self.view.workspace.removeTab(index)

    # ----------------- 搜索逻辑 -----------------
    def on_search_text_changed(self, text: str) -> None:
        if self._search_timer is None:
            return
        self._pending_search_text = text
        self._search_timer.stop()
        self._search_timer.start()

    def _do_search(self) -> None:
        text = self._pending_search_text.strip()
        if not text:
            self.view.hide_search_results()
            self._search_result_shown = False
            return
        results = [t for t in self._page_text_to_key.keys() if
                   text in t or text in (self._page_text_to_key.get(t) or "")]
        self.view.show_search_results(results)
        self._search_result_shown = bool(results)

    def on_search_result_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        display_text = item.text()
        fake_item = QtWidgets.QTreeWidgetItem([display_text])
        fake_item.setData(0, Qt.UserRole, "function")
        self.on_nav_item_clicked(fake_item, 0)
        self.view.hide_search_results()
        self._search_result_shown = False

    # ----------------- 事件过滤 -----------------
    def eventFilter(self, obj: object, event: QtCore.QEvent) -> bool:
        # 只在QKeyEvent时才处理key()
        if obj == self.view.search_edit and event.type() == QEvent.KeyPress:
            if isinstance(event, QtGui.QKeyEvent):
                return self._handle_search_edit_key(event)
        if obj == self.view.search_result_list and event.type() == QEvent.KeyPress:
            if isinstance(event, QtGui.QKeyEvent):
                if event.key() == Qt.Key_Return:
                    current = self.view.search_result_list.currentItem()
                    if current:
                        self.on_search_result_clicked(current)
                        return True
                if event.key() == Qt.Key_Escape:
                    self.view.hide_search_results()
                    self._search_result_shown = False
                    self.view.search_edit.setFocus()
                    return True
        # 不处理则返回False
        return False

    def _handle_search_edit_key(self, event: QtGui.QKeyEvent) -> bool:
        key = event.key()
        if key in (Qt.Key_Down, Qt.Key_Up):
            self.view.search_result_list.setFocus()
            self.view.search_result_list.setCurrentRow(0)
            return True
        if key == Qt.Key_Return and self._search_result_shown:
            current = self.view.search_result_list.currentItem()
            if current:
                self.on_search_result_clicked(current)
                return True
        return False

    # ----------------- 焦点处理 -----------------
    def on_focus_changed(self, old: object, now: object) -> None:
        if not self.view.search_result_list.isVisible():
            return
        if now not in (self.view.search_edit, self.view.search_result_list):
            self.view.hide_search_results()
            self._search_result_shown = False

    # ----------------- 工具方法 -----------------
    def get_view(self) -> MainView:
        return self.view
