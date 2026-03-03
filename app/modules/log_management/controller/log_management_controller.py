from typing import Callable
import os
from PyQt5 import QtWidgets, QtCore
from app.core.base_controller import BaseController
from app.modules.log_management.model.log_management_model import LogDownloadModel, PageResult, LogTableModel
from app.modules.log_management.view.log_management_view import LogDownloadView
from app.services.file_manage.download_manager import DownloadManager
from app.common.utils.worker import Worker
from app.services.file_manage.progress.adapter import ProgressAdapter


class LogDownloadController(BaseController):
    def __init__(self, parent=None):
        """初始化控制器，设置 Model、View、下载管理器及信号连接。"""
        # 1. 初始化 Model 和 View
        self.model = LogDownloadModel(parent)
        self.table_model = LogTableModel([], parent) # UI Model
        self.view = LogDownloadView(parent)
        # 2. 初始化下载管理器
        self.manager = DownloadManager()
        self.manager.log_signal.connect(self._on_worker_log)
        self.workers = [] # Keep references to prevent GC
        # 3. 初始化状态变量
        # 记录被用户请求取消的文件路径集合
        self.cancelled_files = set()

        # 维护“字段 -> 当前排序顺序”，用于实现稳定的点击循环：首次=降序，再次=升序，第三次=降序...
        self._sort_state_by_field = {}

        # 4. 调用父类初始化
        super().__init__(self.model, self.view, parent)

        # 5. 连接 Model 信号
        self.model.dataChanged.connect(self.on_model_changed)
        # 连接新信号，处理局部进度更新
        self.model.progressChanged.connect(self.on_progress_changed)

        # 6. 连接 View 信号
        self.view.sig_search_clicked.connect(self.on_search)
        self.view.sig_refresh_clicked.connect(self.on_refresh)
        self.view.sig_page_changed.connect(self.on_page_changed)
        self.view.sig_page_size_changed.connect(self.on_page_size_changed)
        self.view.sig_download_clicked.connect(self.on_download)
        self.view.sig_cancel_clicked.connect(self.on_cancel)
        # 绑定批量信号
        self.view.sig_batch_download_clicked.connect(self.on_batch_download)
        self.view.sig_batch_cancel_clicked.connect(self.on_batch_cancel)

        # 绑定排序信号
        self.view.sig_sort_requested.connect(self.on_sort_requested)
        # 绑定显示信号，自动获取 Path 列表
        self.view.sig_view_shown.connect(self.on_view_shown)

        # 7. 设置 View 的模型
        self.view.set_table_model(self.table_model)

        # 8. 首次加载第一页
        self.on_model_changed()

    def on_view_shown(self):
        """视图显示时触发，用于初始化加载日志目录列表。"""
        # 1. 获取日志目录列表
        self._fetch_log_paths()

    def _fetch_log_paths(self):
        """启动后台 Worker 获取远程日志目录列表。"""
        # 1. 创建 Worker 执行获取路径任务
        worker = Worker(self._do_fetch_paths_task)
        # 2. 连接结果信号
        worker.result_signal.connect(self._on_paths_fetched)
        # log signal if needed
        # 3. 启动 Worker 并保存引用
        worker.start()
        self.workers.append(worker)

    def _do_fetch_paths_task(self):
        """[子线程] 执行远程日志目录获取任务。"""
        # 1. 尝试从 /log 获取子目录结构
        return self.manager.fetch_remote_path_options("/log")

    def _on_paths_fetched(self, result):
        """处理日志目录列表获取结果，更新界面下拉框。"""
        # 1. 检查结果有效性
        if result:
            # 2. 提取 label (路径) 列表
            paths = [item["label"] for item in result]
            # 3. 更新 View 的选项
            self.view.set_path_options(paths)

    # ---- Controller 槽函数 --
    def on_model_changed(self):
        """模型数据变更时，根据当前过滤和分页状态刷新视图。"""
        # 1. 获取当前页数据
        page_result: PageResult = self.model.get_page()
        # 2. 注入全局序号 (Logic moved from View to Controller)
        start_seq = (page_result.page - 1) * page_result.page_size + 1
        for i, row in enumerate(page_result.rows):
            row["_seq_idx"] = start_seq + i

        # 3. 更新 UI Model 数据
        self.table_model.set_rows(page_result.rows)

        # 4. 更新 View 分页条状态
        self.view.update_pager(
            page=page_result.page,
            page_count=page_result.page_count,
            total=page_result.total
        )

    def on_progress_changed(self, path: str, status: str, progress: int, speed: str):
        """处理下载进度信号，仅更新对应行的状态以避免视图重绘。"""
        # 1. 获取当前 UI Model 显示的所有行
        rows = self.table_model.get_rows()
        target_row_idx = -1
        # 2. 遍历查找匹配 path 的行索引
        for i, row_data in enumerate(rows):
            if row_data.get("path") == path:
                target_row_idx = i
                break

        # 3. 如果找到对应行，更新该行的进度信息
        if target_row_idx >= 0:
            self.table_model.update_row_progress(target_row_idx, status, progress, speed)

    def _update_view_appids(self):
        """根据当前文件列表提取 AppID，并更新视图的筛选下拉框。"""
        # 1. 从 Model 获取唯一的 AppID 列表
        appids = self.model.get_unique_appids()
        # 2. 更新 View 的 AppID 下拉选项
        self.view.set_appid_options(appids)

    def on_search(self, criteria: dict):
        """处理搜索按钮点击，根据条件执行本地过滤或远程扫描。"""
        # 1. 从搜索条件中获取 path 关键字
        path_kw = (criteria.get("path_kw") or "").strip()
        # 2. 判断是否为远程目录扫描（以 / 开头）
        if path_kw.startswith("/"):
            # 3. 若是远程目录，执行远程扫描
            self._start_remote_scan(path_kw, criteria)
        else:
            # 4. 否则，执行本地过滤
            self._apply_local_filter(criteria)

    def _start_remote_scan(self, path_kw: str, criteria: dict):
        """启动远程目录扫描的后台任务。"""
        # 1. 创建后台 Worker 执行扫描任务
        worker = Worker(self._do_refresh_task, path_kw)
        # 2. 连接结果信号，处理扫描完成逻辑
        worker.result_signal.connect(lambda res: self._on_search_fetch_finished(res, criteria))
        # 3. 连接日志信号，用于调试
        worker.log_signal.connect(self._on_worker_log)
        # 4. 连接结束信号，清理 Worker 引用
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        # 5. 保存引用并启动 Worker
        self.workers.append(worker)
        worker.start()

    def _on_worker_log(self, msg: str):
        """接收并打印后台线程的调试日志。"""
        # 1. 打印日志
        # print(f"🧵 [Worker线程]: {msg}")
        pass

    def _apply_local_filter(self, criteria: dict):
        """将搜索条件应用到模型进行本地数据过滤。"""
        # 1. 更新 Model 的过滤条件
        self.model.set_filter(criteria)

    def _on_search_fetch_finished(self, result, criteria):
        """远程搜索任务完成回调，更新数据并应用筛选条件。"""

        if result is not None:
             # 1. 更新完整文件列表
             self.model.set_file_list(result, notify=False)
             # 2. 更新下拉框中的 AppID 选项
             self._update_view_appids()
             # 3. 应用过滤条件
             self.model.set_filter(criteria)

        else:
             # 4. 扫描失败提示
             self.view.show_toast("扫描失败: 无法获取文件列表或目录不存在", 1)


    def on_refresh(self):
        """处理刷新按钮点击，重新从设备获取文件列表。"""

        # 1. 获取当前的过滤条件和路径
        criteria = self.view.get_filter_criteria()
        path_kw = (criteria.get("path_kw") or "").strip()

        # 连接管理器信号
        try:
            self.manager.log_signal.disconnect()
        except:
            pass
        self.manager.log_signal.connect(self._on_worker_log)

        # 2. 创建 Worker 执行刷新任务
        worker = Worker(self._do_refresh_task, path_kw)
        # 3. 连接结果信号，刷新完成后恢复状态
        worker.result_signal.connect(lambda res: self._on_refresh_finished(res, criteria))
        worker.log_signal.connect(self._on_worker_log)
        worker.finished.connect(lambda: self._cleanup_worker(worker))

        # 4. 保存引用并启动
        self.workers.append(worker)
        worker.start()

    def _do_refresh_task(self, custom_path: str = None):
        """[子线程] 执行从设备获取日志文件列表的任务。"""
        # log_cb(f"开始执行刷新任务... 参数 custom_path={custom_path}")

        # 1. 检查设备连接状态
        if not self.manager.is_connected():
            # log_cb("⚠️ 设备未连接，无法获取文件列表。请先连接设备。")
            return None

        # 2. 调用 Manager 获取业务对象列表
        # log_cb("正在调用 Manager fetch_log_list...")
        raw_list = self.manager.fetch_log_list(custom_path=custom_path)
        # log_cb(f"Manager 返回原始数据条数: {len(raw_list) if raw_list else 0}")

        # 3. 在子线程中进行数据归一化
        if raw_list:
            normalized_list = []
            for item in raw_list:
                # 使用 Model 的静态方法进行处理
                normalized_list.append(LogDownloadModel.static_normalize(item))
            # log_cb(f"数据归一化完成. 第一条数据示例: {normalized_list[0].get('filename', 'Unknown')}")
            return normalized_list

        return raw_list

    def _on_refresh_finished(self, result, criteria=None):
        """刷新任务完成回调，更新模型数据和视图状态。"""
        # 1. 检查刷新结果
        if result is not None:
             # 2. 更新 Model 的文件列表
             self.model.set_file_list(result, notify=False)
             # 3. 更新下拉过滤选项
             self._update_view_appids()
             # 4. 恢复之前的过滤状态或应用当前过滤
             if criteria:
                 self.model.set_filter(criteria)
             else:
                 # 兜底：如果没有 criteria（比如初始化加载），应用当前界面上的
                 self.model.set_filter(self.view.get_filter_criteria())
        else:
             # 5. 失败处理
             self.view.show_toast("刷新失败: 无法获取文件列表", 1)

        if result is not None:
             # 6. (重复逻辑) 更新 Model 文件列表
             self.model.set_file_list(result, notify=False)
             self._update_view_appids()
             # 7. (重复逻辑) 重新应用过滤
             if criteria:
                 self.model.set_filter(criteria)
             else:
                 self.model.dataChanged.emit()
        else:
             # 8. (重复逻辑) 失败提示
             self.view.show_toast("刷新失败: 无法连接设备或获取文件列表", 1)

    def on_download(self, path: str):
        """处理单文件下载请求。"""
        # 1. 获取文件信息
        file_info = self.model.get_file_by_path(path)
        if not file_info:
            return
        # 2. 发起单文件下载
        self._initiate_download([(file_info["path"], file_info["filename"])])

    def on_batch_download(self):
        """处理批量下载按钮点击，获取选中文件并启动下载。"""
        # 1. 获取用户勾选的行索引
        rows = self.view.get_checked_rows()
        if not rows:
            self.view.show_toast("请先选择要下载的文件", 2)
            return

        file_pairs = []
        # 2. 从 table_model 获取数据，确保所见即所得
        current_rows = self.table_model.get_rows()
        for r in rows:
            if 0 <= r < len(current_rows):
                fi = current_rows[r]
                file_pairs.append((fi["path"], fi["filename"]))

        # 3. 发起批量下载
        self._initiate_download(file_pairs)

    def _initiate_download(self, file_pairs: list):
        """初始化下载流程：选择目录、设置状态并启动下载线程。"""
        # 1. 检查文件列表是否为空
        if not file_pairs:
            self.view.show_toast("未找到可下载的文件", 1)
            return

        # 2. 询问用户保存目录
        local_dir = QtWidgets.QFileDialog.getExistingDirectory(self.view, "选择保存目录")
        if not local_dir:
            return

        # 3. 更新状态并启动 Worker
        for remote_path, _ in file_pairs:
            self.model.update_file_status(remote_path, "下载中", 0)
            if remote_path in self.cancelled_files:
                self.cancelled_files.remove(remote_path)

        # 4. 创建 Worker 执行下载
        worker = Worker(self._do_download_items, file_pairs, local_dir)
        worker.result_signal.connect(lambda res: self._on_download_finished_unified(res))
        worker.log_signal.connect(self._on_worker_log)
        worker.finished.connect(lambda: self._cleanup_worker(worker))

        # 5. 保存并启动
        self.workers.append(worker)
        worker.start()

    def _do_download_items(self, file_pairs, local_dir):
        """[子线程] 顺序执行文件下载任务。"""
        # log_cb(f"开始批量下载任务, 总数: {len(file_pairs)}")
        results = []
        for index, (remote_path, filename) in enumerate(file_pairs):
            # log_cb(f"正在处理第 {index+1}/{len(file_pairs)} 个: {remote_path}")

            # 1. 下载前检查是否取消
            if remote_path in self.cancelled_files:
                self.model.update_file_status(remote_path, "已取消", 0)
                results.append((remote_path, False, "User Cancelled"))
                # log_cb(f"文件已取消: {filename}")
                continue

            # 2. 准备本地路径，处理重名
            local_path = os.path.join(local_dir, filename)
            local_path = self._get_unique_local_path(local_path)

            # 3. 更新状态为下载中
            self.model.update_file_status(remote_path, "下载中", 0)

            # 4. 创建进度适配器
            adapter = ProgressAdapter(remote_path)
            adapter.progress_sig.connect(self.model.update_file_status)
            progress_cb = adapter.make_unified_callback()

            # 5. 执行下载
            try:
                success, msg = self.manager.download_file(remote_path, local_path, progress_callback=progress_cb)

                # 6. 检查是否因取消导致失败
                if not success and "Cancelled" in str(msg):
                    self.model.update_file_status(remote_path, "已取消", 0)
                    results.append((remote_path, False, "Cancelled"))
                else:
                    results.append((remote_path, success, msg))
                    # 7. 更新最终状态
                    if success:
                        self.model.update_file_status(remote_path, "已下载", 100)
                    else:
                        self.model.update_file_status(remote_path, "下载失败", 0)
            except Exception as e:
                # 8. 异常处理
                if "Cancelled" in str(e):
                    self.model.update_file_status(remote_path, "已取消", 0)
                    results.append((remote_path, False, "Cancelled"))
                else:
                    results.append((remote_path, False, str(e)))
                    self.model.update_file_status(remote_path, "下载失败", 0)

        return results

    def _on_download_finished_unified(self, results):
        """下载任务组完成后的统一回调，显示结果提示。"""
        # 1. 检查结果
        if not results: return
        # results: list of (remote_path, success(bool), msg)
        success_count = sum(1 for (_, ok, _) in results if ok)
        total = len(results)

        # 2. 根据结果数量显示不同提示
        if total == 1:
            _, success, msg = results[0]
            if success:
                self.view.show_toast("文件已下载到本地", 0)
            elif "Cancelled" not in str(msg):
                self.view.show_toast(f"下载失败: {msg}", 1)
        else:
             self.view.show_toast(f"批量下载完成: 已完成 {success_count}/{total} 个文件", 0)


    def on_bulk_cancel(self, paths: list):
        """执行批量取消逻辑，更新文件状态。"""
        # 1. 检查路径列表
        if not paths:
            self.view.show_toast("请先选择要取消的文件（可使用 Ctrl 或 Shift 多选）", 2)
            return

        count = 0
        for p in paths:
            # 2. 获取文件信息
            file_info = self.model.get_file_by_path(p)
            if not file_info:
                continue

            # 3. 校验当前状态
            status = file_info.get("status", "未下载")

            # 4. 仅允许取消“未下载”或“下载中”的文件
            if status not in ["未下载", "下载中"]:
                continue

            # 5. 更新状态为已取消
            self.cancelled_files.add(p)
            self.model.update_file_status(p, "已取消", 0)
            count += 1

        # 6. 显示结果提示
        if count > 0:
            self.view.show_toast(f"已标记 {count} 个文件取消下载", 2)
        else:
             self.view.show_toast("所选文件中没有可取消的任务（仅未下载或下载中的文件可取消）", 2)

    def on_cancel(self, path: str):
        """处理单文件取消请求。"""
        # 1. 标记单个文件为取消状态
        self.cancelled_files.add(path)
        self.model.update_file_status(path, "已取消", 0)

    def on_page_changed(self, delta: int):
        """处理分页切换请求（上一页/下一页）。"""
        # 1. 计算目标页码
        current_page = self.model.page
        target_page = current_page + int(delta or 0)
        if target_page < 1:
            target_page = 1
        # 2. 更新 Model 页码
        self.model.set_page(target_page)

    def on_page_size_changed(self, page_size: int):
        """处理每页显示条数变更请求，重置为第一页。"""
        # 1. 更新 Model 每页条数
        self.model.set_page_size(page_size)

    def _cleanup_worker(self, worker):
        """清理已结束的 Worker 线程引用。"""
        # 1. 移除 Worker 引用
        if worker in self.workers:
            self.workers.remove(worker)



    def get_view(self):
        """获取控制器管理的视图实例。"""
        # 1. 返回 View 实例
        return self.view

    def _get_unique_local_path(self, local_path):
        """检查本地路径是否存在，若存在则自动添加序号后缀。"""
        # 1. 检查是否存在
        if not os.path.exists(local_path):
            return local_path

        # 2. 循环查找可用文件名
        base, ext = os.path.splitext(local_path)
        counter = 1
        while True:
            new_path = f"{base}({counter}){ext}"
            if not os.path.exists(new_path):
                return new_path
            counter += 1


    # def on_sort_changed(self, column: str, order: int):
    #     # 已废弃：View 不再负责字段映射/顺序推断。
    #     # 为兼容旧连接保留空实现，但不再使用。
    #     return

    def on_sort_requested(self, logical_index: int):
        """处理表格表头点击，执行排序逻辑。"""
        logical_index = int(logical_index)

        # 1. 定义列索引到字段的映射
        col_map = {
            2: "filename",
            3: "path",
            4: "appid",
            5: "size_kb",
            6: "create_time",
            7: "modified_time",
        }
        field = col_map.get(logical_index)
        if not field:
            return

        # 2. 确定排序顺序（循环：降序 -> 升序 -> 降序）
        prev = self._sort_state_by_field.get(field)
        # Qt.AscendingOrder = 0, Qt.DescendingOrder = 1
        if prev is None:
            next_order = 1 # Descending
        else:
            next_order = 0 if int(prev) == 1 else 1

        self._sort_state_by_field[field] = next_order

        # 3. 更新模型排序
        self.model.set_sort(field, QtCore.Qt.SortOrder(next_order))

        # 4. 更新 UI 表头指示器
        try:
            self.view.table.horizontalHeader().setSortIndicator(logical_index, QtCore.Qt.SortOrder(next_order))
        except Exception:
            pass

    # 新增：批量取消入口
    def on_batch_cancel(self):
        """处理批量取消按钮点击，获取选中项并调用取消逻辑。"""
        # 1. 获取选中的行
        rows = self.view.get_checked_rows()
        if not rows:
            self.view.show_toast("请先选择要取消的文件", 2)
            return

        # 2. 获取对应文件路径
        paths = []
        current_rows = self.table_model.get_rows()
        for r in rows:
            if 0 <= r < len(current_rows):
                fi = current_rows[r]
                paths.append(fi["path"])

        # 3. 调用批量取消逻辑
        self.on_bulk_cancel(paths)
