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
from PyQt5.QtCore import Qt
import os
# 用于实现 ProgressAdapter（带信号，安全地从后台线程向主线程传递进度）
from app.services.file_manage.progress.adapter import ProgressAdapter


class BusDataDownloadController(BaseController):
    def __init__(self, parent=None):
        """初始化下载控制器"""
        # 1. 初始化核心组件
        self.model = BusDataDownloadModel(parent)
        self.table_model = BusDataTableModel(parent=parent)
        self.view = BusDataDownloadView(parent)
        self.manager = DownloadManager()

        # 2. 初始化状态变量
        self.workers = []
        self._path_to_worker = {}
        self.cancelled_files = set()
        self._tab_options = []
        self.download_queue = []
        self.current_downloading_count = 0
        self.MAX_PARALLEL_DOWNLOADS = 3

        # 3. 调用父类初始化 (必须在 model/view 创建之后)
        super().__init__(self.model, self.view, parent)

        # 4. 初始化信号连接和视图配置
        self._init_signals()
        self.view.set_table_model(self.table_model)

        # 5. 初始数据加载
        self.load_tab_options()

    def _init_signals(self):
        """连接所有信号与槽"""
        # Model 信号
        self.model.dataChanged.connect(self.on_model_changed)
        self.model.progressChanged.connect(self.on_file_progress_changed)

        # View 基础交互
        self.view.sig_search_clicked.connect(self.on_search)
        self.view.sig_refresh_clicked.connect(self.on_refresh)
        self.view.sig_page_changed.connect(self.on_page_changed)
        self.view.sig_page_size_changed.connect(self.on_page_size_changed)
        self.view.sig_view_shown.connect(self.on_view_shown)

        # 表头排序
        self.view.table.horizontalHeader().sectionClicked.connect(self.on_header_clicked)

        # 业务操作信号
        self.view.sig_download_clicked.connect(self.on_row_download_clicked)
        self.view.sig_cancel_clicked.connect(self.on_row_cancel_clicked)
        self.view.sig_batch_download_clicked.connect(self.on_batch_download)
        self.view.sig_batch_cancel_clicked.connect(self.on_batch_cancel)


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
        """执行获取Tab列表的后台任务"""
        return self.manager.fetch_bus_tabs(log_callback=log_cb)

    def _on_tabs_loaded(self, tabs):
        """Tab列表加载完成，更新UI"""
        self._tab_options = tabs or []
        labels = [t.get("label", "") for t in self._tab_options]
        values = [t.get("value", "") for t in self._tab_options]
        self.view.set_tab_options(labels, values)

    # ---- 数据加载流程 ----
    def load_data(self, from_refresh_btn=False):
        """加载数据"""
        # 1. 获取并应用过滤条件
        criteria = self.view.get_filter_criteria()
        self.model.set_filter(criteria)

        # 2. 决定是否需要同时拉取 Tab 列表
        # 点击刷新按钮时强制更新，否则只在为空时获取
        tab_path = criteria.get("tab_kw") or None
        need_tabs = True if from_refresh_btn else (not self._tab_options)

        # 4. 启动后台任务
        worker = Worker(self._do_fetch_task, tab_path, need_tabs)
        worker.result_signal.connect(lambda res: self._on_fetch_finished(res, from_refresh_btn))
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        self.workers.append(worker)
        worker.start()

    def _do_fetch_task(self, log_cb: Callable, tab_path: str, need_tabs: bool):
        """后台任务：拉取Tab（可选）和文件列表"""
        if not self.manager.is_connected():
            log_cb("⚠️ 设备未连接，无法获取文件列表。请先连接设备。")
            return None

        tabs = []
        if need_tabs:
            tabs = self.manager.fetch_bus_tabs(log_callback=log_cb)

        files = self.manager.fetch_bus_file_list(log_callback=log_cb, tab_path=tab_path)
        return (tabs, files)

    def _on_fetch_finished(self, result, from_refresh_btn):
        """数据拉取完成回调，更新UI"""
        # 1. 处理返回数据
        if result is not None:
            tabs, files = result
            if tabs:
                self._on_tabs_loaded(tabs)

            self.model.set_file_list(files)
            self._update_view_types()

    def _update_view_types(self):
        """更新下拉筛选框的 Type 选项"""
        types = self.model.get_unique_types()
        self.view.set_type_options(types)

    def _cleanup_worker(self, worker):
        """清理已完成的线程Worker"""
        if worker in self.workers:
            self.workers.remove(worker)
        # 清理 mapping，避免内存泄漏
        try:
            if hasattr(worker, '_adapter_path') and worker._adapter_path:
                self._path_to_worker.pop(worker._adapter_path, None)
        except Exception:
            pass

    # ---- 模型变化 -> 刷新视图 ----
    def on_model_changed(self):
        """模型数据变化响应，刷新表格显示"""
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
        """处理搜索按钮点击"""
        # 点击搜索后触发数据加载
        self.load_data(from_refresh_btn=False)

    def on_refresh(self):
        """处理刷新按钮点击"""
        self.load_data(from_refresh_btn=True)

    # ---- 分页 ----
    def on_page_changed(self, delta: int):
        """处理翻页操作"""
        current_page = self.model.page
        target_page = current_page + int(delta or 0)
        if target_page < 1:
            target_page = 1
        self.model.set_page(target_page)

    def on_page_size_changed(self, page_size: int):
        """处理每页显示条数变更"""
        self.model.set_page_size(page_size)

    # ---- 行级操作：下载/取消 ----
    def on_row_download_clicked(self, path: str):
        """点击下载按钮。"""
        if not self._require_connected():
            return

        # 使用 path 查找文件对象
        item = self.model.get_file_by_path(path)
        if not item:
            return

        # 只阻止正在下载的任务；允许对已下载文件重新下载
        if self._is_downloading(item):
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
        # 仅阻止正在下载的文件
        if status == "下载中":
            self.view.show_toast("任务正在进行中，请稍候...", 2)
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
            # 为该下载任务创建一个 ProgressAdapter 并传入 worker，确保 adapter 在 worker 生命周期内保持引用
            adapter = ProgressAdapter(remote_path)
            adapter.progress_sig.connect(self.model.update_file_status)
            worker = Worker(self._do_download_task, remote_path, local_path, adapter)
            self._start_download_worker(worker, remote_path)

    def _do_download_task(self, log_cb, remote_path, local_path, adapter=None):
        """实际下载线程任务，支持取消与进度回调"""
        if remote_path in self.cancelled_files:
            self.model.update_file_status(remote_path, "已取消", 0)
            return False, "Cancelled"

        # 确保 adapter 可用（若调用方未传入，则创建临时 adapter）
        if adapter is None:
            adapter = ProgressAdapter(remote_path)
            adapter.progress_sig.connect(self.model.update_file_status)

        # 统一回调，兼容 SFTP (transferred,total) 与 SCP (filename,size,sent) 两种签名
        progress_cb = adapter.make_unified_callback()

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
        """启动下载线程并绑定回调"""
        # Bind remote_path as default argument to avoid late-binding closure issue
        worker.result_signal.connect(lambda res, rp=remote_path: self._on_download_finished(res, rp))
        worker.finished.connect(lambda w=worker: self._cleanup_worker(w))

        # 如果 worker 的 args 中包含 adapter（第3个参数），把它绑定到 worker 上以保持引用
        try:
            if hasattr(worker, 'args') and len(worker.args) >= 3:
                setattr(worker, '_adapter', worker.args[2])
                # 记录 adapter 路径并注册到映射，方便快速定位
                try:
                    a_path = getattr(worker.args[2], 'path', None)
                    setattr(worker, '_adapter_path', a_path)
                    if a_path:
                        self._path_to_worker[a_path] = worker
                except Exception:
                    pass
        except Exception:
            pass

        self.workers.append(worker)
        worker.start()

    def _on_download_finished(self, result, remote_path):
        """下载任务完成回调"""
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
                self.view.show_toast("文件已下载到本地", 0)
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
        try:
            if hasattr(self.manager, 'cancel_download') and callable(getattr(self.manager, 'cancel_download')):
                try:
                    self.manager.cancel_download(path)
                except Exception:
                    # 仅记录/吞掉异常，继续尝试 adapter 层的取消
                    pass
        except Exception:
            pass

        # 如果有映射，直接定位并调用该 worker 的 adapter.cancel()
        try:
            w = self._path_to_worker.get(path)
            if w and hasattr(w, '_adapter'):
                try:
                    adapter = getattr(w, '_adapter')
                    if hasattr(adapter, 'cancel') and callable(getattr(adapter, 'cancel')):
                        adapter.cancel()
                except Exception:
                    pass
                return
        except Exception:
            pass

        # 兜底：遍历 workers（兼容老逻辑），并调用 adapter.cancel
        try:
            for w in list(self.workers):
                try:
                    if hasattr(w, '_adapter'):
                        adapter = getattr(w, '_adapter')
                        a_path = getattr(adapter, 'path', None)
                        if not a_path:
                            continue
                        if a_path == path or a_path.endswith(f"/{path}") or a_path.endswith(path):
                            try:
                                if hasattr(adapter, 'cancel') and callable(getattr(adapter, 'cancel')):
                                    adapter.cancel()
                            except Exception:
                                pass
                except Exception:
                    continue
        except Exception:
            pass

    def _collect_selected_paths(self) -> list:
        """收集表格中被勾选的文件路径，返回路径列表。
        优化: 直接使用 Model 提供的接口，避免 UI 遍历。
        """
        rows = self.table_model.get_checked_rows()
        # 兼容: 确保 path 字段存在 (column 3 logic in old code)
        return [r.get("path") for r in rows if r.get("path")]

    def _require_connected(self) -> bool:
        """检查 manager 是否连接，若未连接则提示并返回 False。"""
        if not self.manager.is_connected():
            self.view.show_toast("设备未连接，无法下载", 1)
            return False
        return True

    def on_batch_download(self):
        """批量下载"""
        if not self._require_connected():
            return

        paths_to_process = self._collect_selected_paths()
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
        paths_to_process = self._collect_selected_paths()

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
        """获取视图引用"""
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

    def _is_downloading(self, item: dict) -> bool:
        """检查 item 是否处于下载中，若是则提示并返回 True。"""
        if item.get("status") == "下载中":
            self.view.show_toast("任务正在进行中，请稍候...", 2)
            return True
        return False