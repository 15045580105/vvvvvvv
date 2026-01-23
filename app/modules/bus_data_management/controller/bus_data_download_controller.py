"""
@FileName：bus_data_download_controller.py
@Description：总线数据下载控制器
@Author：QinHao
@Time：2025/12/9 14:58
@Department：PTV_AT
"""
from typing import Callable
from app.core.base_controller import BaseController
from app.modules.bus_data_management.model.bus_data_download_model import (
    BusDataDownloadModel,
    BusDataTableModel,
    PageResult,
)
from app.modules.bus_data_management.view.bus_data_download_view import BusDataDownloadView
from app.services.file_manage.download_manager import DownloadManager
from app.common.utils.worker import Worker
from PyQt5 import QtWidgets
from PyQt5 import QtCore
import os
import time


class BusDataDownloadController(BaseController):
    def __init__(self, parent=None):
        self.model = BusDataDownloadModel(parent)
        self.table_model = BusDataTableModel([], parent) # 新建 TableModel
        self.view = BusDataDownloadView(parent)
        self.manager = DownloadManager()
        self.workers = []
        self.cancelled_files = set()
        # cache tab options
        self._tab_options = []

        # 下载队列相关
        self.download_queue = []
        self.current_downloading_count = 0
        self.MAX_PARALLEL_DOWNLOADS = 3  # 限制并发数，避免 SSH 通道耗尽

        super().__init__(self.model, self.view, parent)

        # 连接 Model 信号
        self.model.dataChanged.connect(self.on_model_changed)
        self.model.progressChanged.connect(self.on_file_progress_changed)

        # 连接 View 基本交互信号
        self.view.sig_search_clicked.connect(self.on_search)
        self.view.sig_refresh_clicked.connect(self.on_refresh)
        self.view.sig_page_changed.connect(self.on_page_changed)
        self.view.sig_page_size_changed.connect(self.on_page_size_changed)

        # 排序信号
        self.view.table.horizontalHeader().sectionClicked.connect(self.on_header_clicked)

        # 下载/取消按钮
        self.view.sig_download_clicked.connect(self.on_row_download_clicked)
        self.view.sig_cancel_clicked.connect(self.on_row_cancel_clicked)
        self.view.sig_batch_download_clicked.connect(self.on_batch_download)
        self.view.sig_batch_cancel_clicked.connect(self.on_batch_cancel)

        # 页面显示信号：处理连接后切回页面的加载逻辑
        self.view.sig_view_shown.connect(self.on_view_shown)

        # 设置 View 的模型
        self.view.set_table_model(self.table_model)

        # 首次加载
        # self.on_model_changed()
        self.load_tab_options()
        # self.load_data()

    def on_view_shown(self):
        """当页面显示时，如果 Tab 选项为空，尝试从新加载(可能刚连接了设备)"""
        if not self._tab_options:
            self.load_tab_options()

    def load_tab_options(self):
        """后台线程加载 TAB 下拉选项"""
        worker = Worker(self._do_fetch_tabs)
        worker.result_signal.connect(self._on_tabs_loaded)
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        self.workers.append(worker)
        worker.start()

    def _do_fetch_tabs(self, log_cb: Callable):
        return self.manager.fetch_bus_tabs(log_callback=log_cb)

    def _on_tabs_loaded(self, tabs):
        self._tab_options = tabs or []
        labels = [t.get("label", "") for t in self._tab_options]
        values = [t.get("value", "") for t in self._tab_options]
        self.view.set_tab_options(labels, values)

    def load_data(self, from_refresh_btn=False):
        """加载数据"""
        if from_refresh_btn:
            self.view.refresh_btn.setEnabled(False)
            self.view.refresh_btn.setText("加载中...")
        else:
            self.view.search_btn.setEnabled(False)
            self.view.search_btn.setText("搜索中...")

        # 在主线程获取 UI 参数，避免线程安全问题
        criteria = self.view.get_filter_criteria()
        # 无论是搜索还是刷新，都应该更新过滤条件
        self.model.set_filter(criteria)

        tab_path = criteria.get("tab_kw") or None

        # 如果是点击刷新按钮，强制请求更新 Tab 列表，否则仅在空的时候请求
        if from_refresh_btn:
            need_tabs = True
        else:
            need_tabs = not self._tab_options

        worker = Worker(self._do_fetch_task, tab_path, need_tabs)
        worker.result_signal.connect(lambda res: self._on_fetch_finished(res, from_refresh_btn))
        worker.finished.connect(lambda: self._cleanup_worker(worker))

        self.workers.append(worker)
        worker.start()

    def _do_fetch_task(self, log_cb: Callable, tab_path: str, need_tabs: bool):
        if not self.manager.is_connected():
            log_cb("⚠️ 设备未连接，无法获取文件列表。请先连接设备。")
            return None

        tabs = []
        if need_tabs:
            tabs = self.manager.fetch_bus_tabs(log_callback=log_cb)

        files = self.manager.fetch_bus_file_list(log_callback=log_cb, tab_path=tab_path)
        return (tabs, files)

    def _on_fetch_finished(self, result, from_refresh_btn):
        if from_refresh_btn:
            self.view.refresh_btn.setEnabled(True)
            self.view.refresh_btn.setText("刷新")
        else:
            self.view.search_btn.setEnabled(True)
            self.view.search_btn.setText("搜索")

        if result is not None:
            tabs, files = result
            if tabs:
                self._on_tabs_loaded(tabs)

            self.model.set_file_list(files)
            self._update_view_types()

    def _update_view_types(self):
        types = self.model.get_unique_types()
        self.view.set_type_options(types)

    def _cleanup_worker(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)

    # ---- 模型变化 -> 刷新视图 ----
    def on_model_changed(self):
        page_result: PageResult = self.model.get_page()

        # 注入全局序号 (Logic moved from View to Controller)
        start_seq = (page_result.page - 1) * page_result.page_size + 1
        for i, row in enumerate(page_result.rows):
            row["_seq_idx"] = start_seq + i

        # 更新 UI Model
        self.table_model.set_rows(page_result.rows)

        # 更新分页条
        self.view.update_pager(
            page=page_result.page,
            page_count=page_result.page_count,
            total=page_result.total
        )

    def on_file_progress_changed(self, path: str, status: str, progress: int, speed: str):
        """处理文件进度的局部更新"""
        # 查找该文件在当前页的行号 (Ask Model for row index in current page)
        row_idx = self.model.get_row_index_by_path(path)
        if row_idx >= 0:
            # Update Table Model directly
            self.table_model.update_row_progress(row_idx, status, progress, speed)

    # ---- 顶部过滤 / 刷新 ----
    def on_search(self, criteria: dict):
        # 点击搜索后触发数据加载
        self.load_data(from_refresh_btn=False)

    def on_refresh(self):
        self.load_data(from_refresh_btn=True)

    # ---- 分页 ----
    def on_page_changed(self, delta: int):
        current_page = self.model.page
        target_page = current_page + int(delta or 0)
        if target_page < 1:
            target_page = 1
        self.model.set_page(target_page)

    def on_page_size_changed(self, page_size: int):
        self.model.set_page_size(page_size)

    # ---- 行级操作：下载/取消 ----
    def on_row_download_clicked(self, path: str):
        """点击下载按钮。"""
        if not self.manager.is_connected():
            self.view.show_toast("设备未连接，无法下载", 1)
            return

        # 使用 path 查找文件对象
        item = self.model.get_file_by_path(path)
        if not item:
            return

        if item.get("status") in ("下载中", "已下载"):
            return

        local_dir = QtWidgets.QFileDialog.getExistingDirectory(self.view, "选择保存目录")
        if not local_dir:
            return

        self._execute_download(path, local_dir)

    def _execute_download(self, path: str, local_dir: str):
        """执行单文件下载，进入队列"""
        item = self.model.get_file_by_path(path)
        if not item:
            return

        status = item.get("status")
        if status in ("下载中", "已下载"):
            return

        filename = item.get("filename")
        remote_path = item.get("path")

        local_path = os.path.join(local_dir, filename)
        local_path = self._get_unique_local_path(local_path)

        # 立即反馈状态 (视觉上进入下载状态，实际上可能在排队)
        self.model.update_file_status(remote_path, "下载中", 0, "")
        if remote_path in self.cancelled_files:
            self.cancelled_files.remove(remote_path)

        # 加入队列并尝试处理
        self.download_queue.append((remote_path, local_path))
        self._process_download_queue()

    def _process_download_queue(self):
        """处理下载队列"""
        while self.current_downloading_count < self.MAX_PARALLEL_DOWNLOADS and self.download_queue:
            remote_path, local_path = self.download_queue.pop(0)

            # 如果已被取消，则跳过
            if remote_path in self.cancelled_files:
                self.model.update_file_status(remote_path, "已取消", 0)
                continue

            self.current_downloading_count += 1
            worker = Worker(self._do_download_task, remote_path, local_path)
            self._start_download_worker(worker, remote_path)

    def _do_download_task(self, log_cb, remote_path, local_path):
        """实际下载线程任务，支持取消与进度回调"""
        if remote_path in self.cancelled_files:
            self.model.update_file_status(remote_path, "已取消", 0)
            return False, "Cancelled"

        def progress_cb(transferred, total):
            if remote_path in self.cancelled_files:
                raise RuntimeError("Cancelled")
            try:
                now = time.time()
                state = progress_cb.__dict__.setdefault("state", {"last_time": now, "last_bytes": 0})
                dt = now - state["last_time"]
                if total and total > 0:
                    pct = int(transferred * 100 / total)
                else:
                    pct = 0
                if dt >= 0.5 or (total and transferred == total):
                    diff = transferred - state["last_bytes"]
                    speed = ""
                    if dt > 0 and diff >= 0:
                        speed_val = diff / dt
                        if speed_val < 1024:
                            speed = f"{speed_val:.1f} B/s"
                        elif speed_val < 1024 * 1024:
                            speed = f"{speed_val/1024:.1f} KB/s"
                        else:
                            speed = f"{speed_val/(1024*1024):.1f} MB/s"
                    self.model.update_file_status(remote_path, "下载中", pct, speed)
                    state["last_time"] = now
                    state["last_bytes"] = transferred
            except Exception:
                pass

        try:
            success, msg = self.manager.download_file(remote_path, local_path, progress_callback=progress_cb)
            if not success and "Cancelled" in str(msg):
                self.model.update_file_status(remote_path, "已取消", 0)
                return False, "Cancelled"
            return success, msg
        except Exception as e:
            if "Cancelled" in str(e):
                self.model.update_file_status(remote_path, "已取消", 0)
                return False, "Cancelled"
            return False, str(e)

    def _start_download_worker(self, worker, remote_path):
        worker.result_signal.connect(lambda res: self._on_download_finished(res, remote_path))
        worker.finished.connect(lambda w=worker: self._cleanup_worker(w))
        self.workers.append(worker)
        worker.start()

    def _on_download_finished(self, result, remote_path):
        self.current_downloading_count -= 1

        if not result:
            self.model.update_file_status(remote_path, "下载失败", 0)
        else:
            try:
                success, msg = result
            except Exception:
                success, msg = bool(result), ""
            if success:
                self.model.update_file_status(remote_path, "已下载", 100)
                # self.view.show_toast("文件已下载到本地", 0) # 批量下载时太吵了，也许可以去掉或改成 log
            else:
                if "Cancelled" not in str(msg):
                    self.model.update_file_status(remote_path, "下载失败", 0)
                    self.view.show_toast(f"下载失败: {msg}", 1)

        # 继续处理队列
        self._process_download_queue()

    def on_row_cancel_clicked(self, path: str):
        """点击取消按钮。"""
        # path 直接作为 id
        self.cancelled_files.add(path)
        self.model.update_file_status(path, "已取消", 0)

    def on_batch_download(self):
        """批量下载"""
        if not self.manager.is_connected():
            self.view.show_toast("设备未连接，无法下载", 1)
            return

        model = self.view.table.model()
        if not model:
            return

        paths_to_process = []
        for r in range(model.rowCount()):
            idx = model.index(r, 0)
            if model.data(idx, QtCore.Qt.CheckStateRole) == QtCore.Qt.Checked:
                # 获取 Path (列3)
                path_idx = model.index(r, 3)
                path = model.data(path_idx, QtCore.Qt.DisplayRole)
                if path:
                    paths_to_process.append(path)

        if not paths_to_process:
            self.view.show_toast("请先勾选需要下载的文件", 1)
            return

        local_dir = QtWidgets.QFileDialog.getExistingDirectory(self.view, "选择批量保存目录")
        if not local_dir:
            return

        for p in paths_to_process:
            self._execute_download(p, local_dir)

    def on_batch_cancel(self):
        """批量取消"""
        model = self.view.table.model()
        if not model:
            return

        paths_to_process = []
        for r in range(model.rowCount()):
            idx = model.index(r, 0)
            if model.data(idx, QtCore.Qt.CheckStateRole) == QtCore.Qt.Checked:
                # 获取 Path (列3)
                path_idx = model.index(r, 3)
                path = model.data(path_idx, QtCore.Qt.DisplayRole)
                if path:
                    paths_to_process.append(path)

        count = 0
        for p in paths_to_process:
            # 只取消未下载/下载中的任务
            item = self.model.get_file_by_path(p)
            if not item:
                continue
            status = item.get("status")
            if status in ("未下载", "下载中"):
                self.on_row_cancel_clicked(p)
                count += 1

        if count > 0:
            self.view.show_toast(f"已为您取消 {count} 个文件的下载任务", 2)
        else:
            self.view.show_toast("选中的文件中没有可取消的任务", 2)

    def on_header_clicked(self, index: int):
        """处理表头点击排序"""
        # 0: Checkbox, 1: Index, 10: Operations - 这些列不排序
        if index in (0, 1, 10):
            return

        current_idx = self.model.sort_column_idx
        current_order = self.model.sort_order

        if index != current_idx:
            # 首次点击 -> 降序 (符合用户需求)
            new_order = 1
        else:
            # 再次点击 -> 切换
            new_order = 1 - current_order

        # 更新 Model 排序
        self.model.set_sort(index, new_order)

        # 同步 View 的排序列指示器 (SortOrder: 0=Asc, 1=Desc)
        self.view.table.horizontalHeader().setSortIndicator(index, new_order)

    def get_view(self):
        return self.view

    def _get_unique_local_path(self, local_path):
        """如果文件已存在，添加 (1), (2), ... 后缀"""
        if not os.path.exists(local_path):
            return local_path
        base, ext = os.path.splitext(local_path)
        counter = 1
        while True:
            candidate = f"{base}({counter}){ext}"
            if not os.path.exists(candidate):
                return candidate
            counter += 1
