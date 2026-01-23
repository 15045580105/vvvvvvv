from typing import Callable
import os
import time
from PyQt5 import QtWidgets, QtCore
from app.core.base_controller import BaseController
from app.modules.log_management.model.log_management_model import LogDownloadModel, PageResult, LogTableModel
from app.modules.log_management.view.log_management_view import LogDownloadView
from app.services.file_manage.download_manager import DownloadManager
from app.common.utils.worker import Worker


class LogDownloadController(BaseController):
    def __init__(self, parent=None):
        self.model = LogDownloadModel(parent)
        self.table_model = LogTableModel([], parent) # UI Model
        self.view = LogDownloadView(parent)
        # Initialize manager
        self.manager = DownloadManager()
        self.workers = [] # Keep references to prevent GC
        # 记录被用户请求取消的文件路径集合
        self.cancelled_files = set()

        # 维护“字段 -> 当前排序顺序”，用于实现稳定的点击循环：首次=降序，再次=升序，第三次=降序...
        self._sort_state_by_field = {}

        super().__init__(self.model, self.view, parent)

        # 连接 Model 信号
        self.model.dataChanged.connect(self.on_model_changed)
        # 连接新信号，处理局部进度更新
        self.model.progressChanged.connect(self.on_progress_changed)

        # 连接 View 信号
        self.view.sig_search_clicked.connect(self.on_search)
        self.view.sig_refresh_clicked.connect(self.on_refresh)
        self.view.sig_page_changed.connect(self.on_page_changed)
        self.view.sig_page_size_changed.connect(self.on_page_size_changed)
        self.view.sig_download_clicked.connect(self.on_download)
        self.view.sig_cancel_clicked.connect(self.on_cancel)
        # 绑定批量信号
        self.view.sig_batch_download_clicked.connect(self.on_batch_download)
        self.view.sig_batch_cancel_clicked.connect(self.on_batch_cancel)

        # 绑定排序信号（View 只发 logical_index）
        self.view.sig_sort_requested.connect(self.on_sort_requested)

        # 设置 View 的模型
        self.view.set_table_model(self.table_model)

        # 首次加载第一页
        self.on_model_changed()

        # 打开页面后自动刷新列表
        QtCore.QTimer.singleShot(0, self.on_refresh)

    # ---- Controller 槽函数 ----
    def on_model_changed(self):
        """模型数据变更时，根据当前过滤和分页状态刷新视图。"""
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

        # Original: self.view.render_rows(...) - REMOVED

    def on_progress_changed(self, path: str, status: str, progress: int, speed: str):
        """专门处理下载进度/状态变化，只刷新对应行，避免全量重置导致勾选丢失"""
        # 在 UI Model 中查找这一行的索引
        # 注意：LogTableModel 只包含当前页的数据，所以我们要遍历的是当前页
        rows = self.table_model.get_rows()
        target_row_idx = -1
        for i, row_data in enumerate(rows):
            if row_data.get("path") == path:
                target_row_idx = i
                break

        if target_row_idx >= 0:
            self.table_model.update_row_progress(target_row_idx, status, progress, speed)

    def _update_view_appids(self):
        appids = self.model.get_unique_appids()
        self.view.set_appid_options(appids)

    def on_search(self, criteria: dict):
        """用户点击搜索按钮后的处理。"""
        # 从 criteria 中取出 path 关键字并去掉首尾空白
        path_kw = (criteria.get("path_kw") or "").strip()
        # 若用户输入以 '/' 开头，认为这是一个目录路径，需要执行一次扫描
        if path_kw.startswith("/"):
            # 先把数据拿到手，再应用过滤
            self._start_remote_scan(path_kw, criteria)
        else:
            # 非以 '/' 开头：认为只是基于关键字的本地过滤
            self._apply_local_filter(criteria)

    def _start_remote_scan(self, path_kw: str, criteria: dict):
        """执行远程目录扫描"""
        self.view.search_btn.setEnabled(False)
        self.view.search_btn.setText("扫描中...")

        # 创建一个后台 Worker 执行实际的扫描任务
        # 构造一个后台任务线程，任务函数为 self._do_refresh_task，传入 path_kw 作为参数
        worker = Worker(self._do_refresh_task, path_kw)
        # 将work产出的res,返回给_on_search_fetch_finished函数
        worker.result_signal.connect(lambda res: self._on_search_fetch_finished(res, criteria))
        # [调试] 连接日志信号，子线程 log_cb 打印的内容会通过这里在主线程输出
        worker.log_signal.connect(self._on_worker_log)
        # 任务结束后清理引用
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        # 保存引用防止被垃圾回收
        self.workers.append(worker)
        worker.start()

    def _on_worker_log(self, msg: str):
        """[调试核心] 专门接收子线程发出来的日志数据，在控制台打印方便Debug"""
        # print(f"🧵 [Worker线程]: {msg}")
        pass

    def _apply_local_filter(self, criteria: dict):
        """执行本地过滤"""
        self.model.set_filter(criteria)

    def _on_search_fetch_finished(self, result, criteria):
        """搜索附带的扫描任务完成"""
        self.view.search_btn.setEnabled(True)
        self.view.search_btn.setText("搜索")

        if result is not None:
             # 更新完整文件列表
             self.model.set_file_list(result, notify=False)
             # 看一下这一批数据中都有什么AppID， 更新下拉框中的 AppID 选项
             self._update_view_appids()
             # 紧接着应用一次过滤（让其他条件生效）
             self.model.set_filter(criteria)

        else:
             self.view.show_toast("扫描失败: 无法获取文件列表或目录不存在", 1)


    def on_refresh(self):
        """用户点击刷新按钮，重新加载数据。"""
        # Disable button status
        self.view.refresh_btn.setEnabled(False)
        self.view.refresh_btn.setText("刷新中...")

        # 修改逻辑：刷新时也要带上当前的 Path 和过滤条件
        criteria = self.view.get_filter_criteria()
        path_kw = (criteria.get("path_kw") or "").strip()

        # 传入 path_kw，确保刷新的是当前查看的目录
        worker = Worker(self._do_refresh_task, path_kw)
        # 将 criteria 传给回调，以便刷新后恢复过滤状态
        worker.result_signal.connect(lambda res: self._on_refresh_finished(res, criteria))
        worker.log_signal.connect(self._on_worker_log)
        worker.finished.connect(lambda: self._cleanup_worker(worker))

        self.workers.append(worker)
        worker.start()

    def _do_refresh_task(self, log_cb: Callable[[str], None], custom_path: str = None):
        """刷新任务：在子线程执行"""
        log_cb(f"开始执行刷新任务... 参数 custom_path={custom_path}")

        # 直接检查 Manager 的连接状态（内部会调用 get_client 判断）
        if not self.manager.is_connected():
            log_cb("⚠️ 设备未连接，无法获取文件列表。请先连接设备。")
            return None

        # 2. 调用 Manager 获取业务对象列表
        log_cb("正在调用 Manager fetch_log_list...")
        raw_list = self.manager.fetch_log_list(log_callback=log_cb, custom_path=custom_path)
        log_cb(f"Manager 返回原始数据条数: {len(raw_list) if raw_list else 0}")

        # 3. 在子线程中进行归一化处理，减轻主线程负担防止卡顿
        if raw_list:
            normalized_list = []
            for item in raw_list:
                # 使用 Model 的静态方法进行处理
                normalized_list.append(LogDownloadModel.static_normalize(item))
            log_cb(f"数据归一化完成. 第一条数据示例: {normalized_list[0].get('filename', 'Unknown')}")
            return normalized_list

        return raw_list

    def _on_refresh_finished(self, result, criteria=None):
        """刷新完成：在主线程更新 UI/Model"""
        self.view.refresh_btn.setEnabled(True)
        self.view.refresh_btn.setText("刷新")

        if result is not None:
             # 更新数据，暂不触发更新，等设置完 filter 再触发
             self.model.set_file_list(result, notify=False)
             self._update_view_appids()
             # 重新应用当前的过滤条件
             if criteria:
                 self.model.set_filter(criteria)
             else:
                 self.model.dataChanged.emit()
        else:
             self.view.show_toast("刷新失败: 无法连接设备或获取文件列表", 1)

    def on_download(self, path: str):
        file_info = self.model.get_file_by_path(path)
        if not file_info:
            return
        # 复用统一的下载逻辑，传入单个文件元组
        self._initiate_download([(file_info["path"], file_info["filename"])])

    def on_batch_download(self):
        """批量下载入口（替代原 on_bulk_download）"""
        rows = self.view.get_checked_rows()
        if not rows:
            self.view.show_toast("请先选择要下载的文件", 2)
            return

        file_pairs = []
        # 使用 table_model 获取当前页显示的数据，确保所见即所得
        current_rows = self.table_model.get_rows()
        for r in rows:
            if 0 <= r < len(current_rows):
                fi = current_rows[r]
                file_pairs.append((fi["path"], fi["filename"]))

        self._initiate_download(file_pairs)

    def _initiate_download(self, file_pairs: list):
        if not file_pairs:
            self.view.show_toast("未找到可下载的文件", 1)
            return

        # 统一询问一次保存目录
        local_dir = QtWidgets.QFileDialog.getExistingDirectory(self.view, "选择保存目录")
        if not local_dir:
            return

        # 更新状态并启动 Worker
        for remote_path, _ in file_pairs:
            self.model.update_file_status(remote_path, "下载中", 0)
            if remote_path in self.cancelled_files:
                self.cancelled_files.remove(remote_path)


        worker = Worker(self._do_download_items, file_pairs, local_dir)
        worker.result_signal.connect(lambda res: self._on_download_finished_unified(res))
        worker.log_signal.connect(self._on_worker_log)
        worker.finished.connect(lambda: self._cleanup_worker(worker))

        self.workers.append(worker)
        worker.start()


    @staticmethod
    def _format_speed(speed_bps: float) -> str:
        if speed_bps < 1024:
            return f"{speed_bps:.1f} B/s"
        elif speed_bps < 1024 * 1024:
            return f"{speed_bps/1024:.1f} KB/s"
        else:
            return f"{speed_bps/(1024*1024):.1f} MB/s"

    def _do_download_items(self, log_cb, file_pairs, local_dir):
        """
        在子线程按序列化下载多个文件（含单个文件情况）。
        file_pairs: list of (remote_path, filename)
        """
        log_cb(f"开始批量下载任务, 总数: {len(file_pairs)}")
        results = []
        for index, (remote_path, filename) in enumerate(file_pairs):
            log_cb(f"正在处理第 {index+1}/{len(file_pairs)} 个: {remote_path}")

            # 1. 下载前检查是否取消
            if remote_path in self.cancelled_files:
                self.model.update_file_status(remote_path, "已取消", 0)
                results.append((remote_path, False, "User Cancelled"))
                log_cb(f"文件已取消: {filename}")
                continue

            local_path = os.path.join(local_dir, filename)
            # 处理同名文件逻辑：自动重命名
            local_path = self._get_unique_local_path(local_path)

            # 把状态设为 下载中
            self.model.update_file_status(remote_path, "下载中", 0)

            # 创建 Progress Callback
            progress_cb = self._create_progress_callback(remote_path)

            try:
                success, msg = self.manager.download_file(remote_path, local_path, progress_callback=progress_cb)

                # 如果是 Cancelled 异常导致，这里可能会捕捉到并返回 success=False
                if not success and "Cancelled" in str(msg):
                    self.model.update_file_status(remote_path, "已取消", 0)
                    results.append((remote_path, False, "Cancelled"))
                else:
                    results.append((remote_path, success, msg))
                    # 结束后在 loop 外根据 success 更新为已完成/失败
                    if success:
                        self.model.update_file_status(remote_path, "已下载", 100)
                    else:
                        self.model.update_file_status(remote_path, "下载失败", 0)
            except Exception as e:
                # 若这里捕获到异常（例如 callback 抛出的 RuntimeError）
                if "Cancelled" in str(e):
                    self.model.update_file_status(remote_path, "已取消", 0)
                    results.append((remote_path, False, "Cancelled"))
                else:
                    results.append((remote_path, False, str(e)))
                    self.model.update_file_status(remote_path, "下载失败", 0)

        return results

    def _create_progress_callback(self, remote_path):
        state = {"last_time": time.time(), "last_bytes": 0}
        def _cb(transferred, total):
            # 2. 传输过程中检查是否取消
            if remote_path in self.cancelled_files:
                raise RuntimeError("Cancelled")

            try:
                now = time.time()
                dt = now - state["last_time"]

                # 限制更新频率：每 0.5 秒或完成时更新
                if dt >= 0.5 or (total > 0 and transferred == total):
                    if total and total > 0:
                        pct = int(transferred * 100 / total)

                        diff = transferred - state["last_bytes"]
                        # 避免除以零和负数
                        if dt > 0 and diff >= 0:
                            speed_bps = diff / dt
                            speed_str = self._format_speed(speed_bps)

                            # 打印详细的速率计算参数到控制台
                            print(f"🚀 [Speed Calc] File: {os.path.basename(remote_path)} | "
                                  f"DeltaBytes: {diff} B | DeltaTime: {dt:.4f} s | "
                                  f"Speed: {speed_bps:.2f} B/s ({speed_str})")
                        else:
                            speed_str = ""

                        self.model.update_file_status(remote_path, "下载中", pct, speed_str)

                        state["last_time"] = now
                        state["last_bytes"] = transferred
            except Exception:
                pass
        return _cb

    def _on_download_finished_unified(self, results):
        if not results: return
        # results: list of (remote_path, success(bool), msg)
        success_count = sum(1 for (_, ok, _) in results if ok)
        total = len(results)

        if total == 1:
            _, success, msg = results[0]
            if success:
                self.view.show_toast("文件已下载到本地", 0)
            elif "Cancelled" not in str(msg):
                self.view.show_toast(f"下载失败: {msg}", 1)
        else:
             self.view.show_toast(f"批量下载完成: 已完成 {success_count}/{total} 个文件", 0)


    # 批量取消：只在 UI/Model 层更新为 已取消（真实中断需要底层支持）
    def on_bulk_cancel(self, paths: list):
        if not paths:
            self.view.show_toast("请先选择要取消的文件（可使用 Ctrl 或 Shift 多选）", 2)
            return

        count = 0
        for p in paths:
            # [Modified] 增加逻辑判断：只有“未下载”和“下载中”的才能被取消
            file_info = self.model.get_file_by_path(p)
            if not file_info:
                continue

            # 获取当前状态
            status = file_info.get("status", "未下载")

            # 如果是已下载、下载失败或已取消，则跳过
            if status not in ["未下载", "下载中"]:
                continue

            # 仅把 UI/Model 状态更新为已取消(或取消中)
            self.cancelled_files.add(p)
            self.model.update_file_status(p, "已取消", 0)
            count += 1

        if count > 0:
            self.view.show_toast(f"已标记 {count} 个文件取消下载", 2)
        else:
             self.view.show_toast("所选文件中没有可取消的任务（仅未下载或下载中的文件可取消）", 2)

    def on_cancel(self, path: str):
        # 兼容单行取消：与批量一致，仅修改状态
        self.cancelled_files.add(path)
        self.model.update_file_status(path, "已取消", 0)

    def on_page_changed(self, delta: int):
        """分页切换：delta=-1 表示上一页，+1 表示下一页。"""
        current_page = self.model.page
        target_page = current_page + int(delta or 0)
        if target_page < 1:
            target_page = 1
        self.model.set_page(target_page)

    def on_page_size_changed(self, page_size: int):
        """用户修改每页条数，回到第一页。"""
        self.model.set_page_size(page_size)

    def _cleanup_worker(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)



    def get_view(self):
        return self.view

    def _get_unique_local_path(self, local_path):
        """如果文件已存在，添加 (1), (2), ... 后缀"""
        if not os.path.exists(local_path):
            return local_path

        base, ext = os.path.splitext(local_path)
        counter = 1
        while True:
            new_path = f"{base}({counter}){ext}"
            if not os.path.exists(new_path):
                return new_path
            counter += 1


    def on_sort_changed(self, column: str, order: int):
        # 已废弃：View 不再负责字段映射/顺序推断。
        # 为兼容旧连接保留空实现，但不再使用。
        return

    def on_sort_requested(self, logical_index: int):
        """处理表头点击排序（Controller 负责映射和排序规则）。"""
        logical_index = int(logical_index)

        # 0: Checkbox, 1: 序号, 8: Progress, 9: Status, 10: Action 不参与排序
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

        prev = self._sort_state_by_field.get(field)
        # 规则：首次点击该列 -> 降序；之后每次切换 Asc/Desc
        # Qt.AscendingOrder = 0, Qt.DescendingOrder = 1
        if prev is None:
            next_order = 1 # Descending
        else:
            next_order = 0 if int(prev) == 1 else 1

        self._sort_state_by_field[field] = next_order

        # 更新模型排序
        self.model.set_sort(field, QtCore.Qt.SortOrder(next_order))

        # 更新表头箭头
        try:
            self.view.table.horizontalHeader().setSortIndicator(logical_index, QtCore.Qt.SortOrder(next_order))
        except Exception:
            pass

    # 新增：批量取消入口
    def on_batch_cancel(self):
        rows = self.view.get_checked_rows()
        if not rows:
            self.view.show_toast("请先选择要取消的文件", 2)
            return

        # 使用 table_model 获取当前页显示的数据
        paths = []
        current_rows = self.table_model.get_rows()
        for r in rows:
            if 0 <= r < len(current_rows):
                fi = current_rows[r]
                paths.append(fi["path"])

        # 复用已有的多选取消逻辑
        self.on_bulk_cancel(paths)
