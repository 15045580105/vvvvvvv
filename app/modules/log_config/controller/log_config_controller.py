from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import QInputDialog

from app.common.utils.worker import Worker  # 引入 Worker
from app.core.base_controller import BaseController
from app.core.dependency_injection import di_container
from app.modules.log_config.model.log_config_model import LogConfigModel
from app.modules.log_config.view.log_config_view import LogConfigView, LogConfigEditDialog
from app.services.configuration.log_config_service import LogConfigService
from app.services.device_manage.device_service import DeviceService


class LogConfigController(BaseController):
    def __init__(self, parent=None):
        self.model = LogConfigModel(parent)
        self.view = LogConfigView(parent)
        super().__init__(self.model, self.view, parent)

        self.log_config_service = di_container.resolve(LogConfigService)
        if not self.log_config_service:
            self.log_config_service = LogConfigService()
            di_container.register_singleton(LogConfigService, self.log_config_service)

        # 尝试注入 DeviceService
        device_service = di_container.resolve(DeviceService)
        if device_service:
            self.log_config_service.inject_device_service(device_service)

        self._workers = []

        self._bind_signals()

        # 进入界面后自动触发一次全量刷新，避免下拉框为空
        QtCore.QTimer.singleShot(100, self._on_app_refresh)

    def _bind_signals(self):
        # ECU Config
        self.view.ecu_execute_btn.clicked.connect(self._on_ecu_execute)

        # App Config - Filter
        self.view.app_search_btn.clicked.connect(self._on_app_search)
        self.view.app_refresh_btn.clicked.connect(self._on_app_refresh)

        # App Config - Pagination
        self.view.prev_page_btn.clicked.connect(self._on_prev_page)
        self.view.next_page_btn.clicked.connect(self._on_next_page)
        self.view.page_size_combo.currentTextChanged.connect(self._on_page_size_changed)

        # App Config - Log Operations
        self.view.batch_modify_btn.clicked.connect(self._on_batch_modify_clicked)

        # Restore Config
        self.view.restore_btn.clicked.connect(self._on_restore_config)

        # Modify App Config
        self.view.modify_requested.connect(self._on_modify_requested)

        # Import Map File
        self.view.import_map_btn.clicked.connect(self._on_import_map)

    def _on_import_map(self):
        from PyQt5 import QtWidgets
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.view, "选择日志配置文件", "", "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.view.map_path_edit.setText(file_path)
            self.log_config_service.set_map_file_path(file_path)
            self.view.show_message(f"已加载配置文件: {file_path}", "success")
            # 如果 APP tab 需要依赖此文件刷新，可以在这里调用刷新
            # self._on_app_refresh()

    def _on_ecu_execute(self):
        selected_ecus = self.view.ecu_select_combo.currentSelection()
        log_level = self.view.ecu_log_level_combo.currentText()
        if not selected_ecus:
            # 使用 Toast 提示而不是弹窗
            from app.common.ui.modern_widgets import MessageToast
            MessageToast(self.view).show_toast("请选择至少一个ECU", 1)
            return

        # 检查设备是否连接
        if not self.log_config_service._device_service or not self.log_config_service._device_service.get_doip_client():
             # 尝试恢复 Toast 提示
             from app.common.ui.modern_widgets import MessageToast
             MessageToast(self.view).show_toast("设备未连接 (DoIP)，无法执行配置", 2)
             # self.view.show_message("设备未连接 (DoIP)，无法执行配置", "error")
             return

        # 使用 Worker 在后台线程执行，避免阻塞 UI
        # from app.common.utils.worker import Worker # 已移至顶部导入
        def task(log_callback):
            return self.log_config_service.set_ecu_log_level(selected_ecus, log_level, log_callback)

        worker = Worker(task)
        # 连接日志信号到 View 的 append_log
        worker.log_signal.connect(self.view.append_log)

        def on_finished(success):
            if success:
                self.view.show_message(f"已设置 {selected_ecus} 日志等级为 {log_level}", "success")
            else:
                self.view.show_message("设置失败，请检查日志", "error")

        worker.result_signal.connect(on_finished)
        worker.start()
        # Keep reference to avoid GC
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

    def _on_app_search(self):
        # 1. 获取 UI 参数（必须在主线程完成）
        ecu_id = self.view.app_filter_ecu_combo.currentText()
        app_id = self.view.app_filter_appid_combo.currentText()
        log_level = self.view.app_filter_loglevel_combo.currentText()

        # 将 "全部" 转换为空字符串，以便 Service 层识别为不筛选
        if ecu_id == "全部": ecu_id = ""
        if app_id == "全部": app_id = ""
        if log_level == "全部": log_level = ""

        # 禁用按钮防止重复点击
        self.view.app_search_btn.setEnabled(False)
        self.view.app_refresh_btn.setEnabled(False)
        self.view.show_message("正在获取配置...", "info")

        # 2. 定义后台任务
        def search_task(log_callback):
            # log_callback 可以用来向界面打印进度日志
            return self.log_config_service.get_apps(ecu_id, app_id, log_level)

        # 3. 定义完成回调
        def on_search_finished(result):
            # 恢复按钮
            self.view.app_search_btn.setEnabled(True)
            self.view.app_refresh_btn.setEnabled(True)

            if result is None:
                self.view.show_message("获取配置失败，请检查连接", "error")
                return

            all_apps = result
            # 将数据交给 Model 处理
            self.model.set_data(all_apps)

            # 如果是全量搜索（或者下拉框为空），则更新筛选项
            is_full_search = (not ecu_id and not app_id and not log_level)
            combo_is_empty = (self.view.app_filter_ecu_combo.count() <= 1)

            if (is_full_search or combo_is_empty):
                # 无论是否有数据，都尝试更新下拉框（如果没有数据则清空）
                self._update_filter_options(all_apps)

            # 刷新 UI 状态
            self.on_model_changed()
            self.view.show_message(f"加载完成，共 {len(all_apps)} 个应用", "info")

        # 4. 启动 Worker
        worker = Worker(search_task)
        worker.result_signal.connect(on_search_finished)
        worker.start()

        # 保持引用以防止 GC (垃圾回收)
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

    def _update_filter_options(self, apps):
        """根据当前应用列表更新筛选下拉框的选项"""
        # 提取并去重
        ecu_ids = sorted(list(set(app["ecu_id"] for app in apps if app.get("ecu_id"))))
        app_ids = sorted(list(set(app["app_id"] for app in apps if app.get("app_id"))))

        # 更新 View
        self.view.update_filter_combos(ecu_ids, app_ids)

    def _on_app_refresh(self):
        # 刷新时清空筛选条件，进行全量查询
        self.view.app_filter_ecu_combo.setCurrentIndex(0)
        self.view.app_filter_appid_combo.setCurrentIndex(0)
        self.view.app_filter_loglevel_combo.setCurrentIndex(0)
        self._on_app_search()

    def _on_prev_page(self):
        if self.model.prev_page():
            self.on_model_changed()

    def _on_next_page(self):
        if self.model.next_page():
            self.on_model_changed()

    def _on_page_size_changed(self, text):
        try:
            import re
            match = re.search(r'\d+', text)
            size = int(match.group()) if match else 10
            self.model.set_page_size(size)
            self.on_model_changed()
        except:
             pass


    def _on_batch_modify_clicked(self):
        """批量修改选中的 CCUA APP"""
        # 1. 获取选中项
        selected_apps = self.view.get_selected_apps()
        if not selected_apps:
            self.view.show_message("请至少选择一个APP", "warning")
            return

        # 2. 校验 (仅允许 CCUA)
        ccua_apps_ids = []
        for app in selected_apps:
            if app['ecu_id'] != 'CCUA':
                self.view.show_message("当前选区包含非CCUA的应用。请取消勾选它们后再试。", "warning")
                return
            ccua_apps_ids.append(app['app_id'])

        # 3. 询问目标日志等级
        # 弹窗询问
        levels = ["OFF", "FATAL", "ERROR", "WARN", "INFO", "DEBUG", "VERBOSE"]
        target_level, ok = QInputDialog.getItem(self.view, "批量修改配置",
                                                f"即将修改 {len(ccua_apps_ids)} 个应用的日志等级\n请选择目标等级:",
                                                levels, 4, False) # Default to INFO index 4
        if not ok:
            return

        # 4. 执行 Worker: Batch Update
        self.view.show_message(f"开始批量修改，目标等级: {target_level}...", "info")
        self.view.append_log(f"用户发起批量修改: {ccua_apps_ids} -> {target_level}")

        def update_task(log_callback):
            return self.log_config_service.batch_update_ccua_apps(ccua_apps_ids, target_level, log_callback)

        def on_update_finished(success):
            if success:
                self.view.show_message("批量配置修改完成！", "success")

                # 5. 询问重启 - 修改为使用 self.view.show_confirm 统一风格
                msg = "配置已更新并落盘。是否立即重启 CCU 以使配置生效？"
                if self.view.show_confirm(msg):
                   self._do_restart_ccu()
                else:
                    self.view.append_log("用户选择暂不重启。")
            else:
                self.view.show_message("批量修改过程中出现错误，请检查日志", "error")

        worker = Worker(update_task)
        worker.log_signal.connect(self.view.append_log)
        worker.result_signal.connect(on_update_finished)
        worker.start()
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

    def _do_restart_ccu(self):
        """执行 CCU 重启"""
        self.view.append_log("正在请求重启 CCU...")

        def restart_task(log_callback):
            return self.log_config_service.restart_ccu(ecu="CCUA") # 显式指定 CCUA

        def on_restart_finished(success):
            if success:
                self.view.show_message("重启指令已发送", "success")
            else:
                self.view.show_message("重启失败", "error")

        worker = Worker(restart_task)
        # restart_ccu 内部用 print，这里可能需要 service 改成支持 log_callback，或者这里不需要 worker log_signal
        # Service 代码现在 print，尚未全改成 log callback，不过 worker 会捕获 stdout 吗？
        # Worker 实现通常不捕获 stdout。
        # Service 里的 restart_ccu目前只是 print。
        # 我们稍微修改一下 Service 的 restart_ccu 以支持 log_callback 吧？不改也没事，反正 UI 会提示。
        worker.result_signal.connect(on_restart_finished)
        worker.start()
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)


    def _on_restore_config(self):
        restore_ccua = self.view.restore_ccua.isChecked()
        restore_ccu0 = self.view.restore_ccu0.isChecked()
        restore_ccu1 = self.view.restore_ccu1.isChecked()
        delete_logs = self.view.delete_logs.isChecked()

        options = {
            "restore_ccua": restore_ccua,
            "restore_ccu0": restore_ccu0,
            "restore_ccu1": restore_ccu1,
            "delete_logs": delete_logs
        }

        if not any(options.values()):
             # 使用 Toast 提示
             from app.common.ui.modern_widgets import MessageToast
             MessageToast(self.view).show_toast("请选择至少一项恢复操作", 1) # 1 for Info/Warning like usage here, or 2 for Warning
             return

        # 检查设备连接 (DoIP 检查)
        if not self.log_config_service._device_service or not self.log_config_service._device_service.get_doip_client():
             self.view.show_message("设备未连接 (DoIP)，无法执行操作", "error")
             return
        msg = ""

        if delete_logs:
            # 优先提示删除日志的不可逆性
            msg = "确定要删除所有 DLT 日志文件吗？\n若删除文件将无法恢复。"

            others = []
            if restore_ccua: others.append("恢复 CCUA 默认配置")
            if restore_ccu0: others.append("恢复 CCU0 默认配置")
            if restore_ccu1: others.append("恢复 CCU1 默认配置")

            if others:
                msg += "\n\n同时执行以下操作:\n" + "\n".join([f"- {o}" for o in others])

        elif restore_ccua:
            msg = "恢复 CCUA 默认配置和修改process_log_configs？"

            others = []
            if restore_ccu0: others.append("恢复 CCU0 默认配置")
            if restore_ccu1: others.append("恢复 CCU1 默认配置")

            if others:
                msg += "\n\n其他操作:\n" + "\n".join([f"- {o}" for o in others])

        else:
            msg = "确定要执行以下操作吗？\n"
            if restore_ccu0: msg += "- 恢复 CCU0 默认配置\n"
            if restore_ccu1: msg += "- 恢复 CCU1 默认配置\n"

        if self.view.show_confirm(msg):
             from app.common.utils.worker import Worker
             # 删除日志需要 SSH
             if delete_logs:
                 ssh_client = self.log_config_service._device_service.get_ssh_client()
                 if not ssh_client or not ssh_client.is_connected():
                     self.view.show_message("设备未连接 (SSH)，无法执行删除日志操作", "error")
                     return
             # 定义任务函数
             def task(log_callback):
                 return self.log_config_service.restore_config(options, log_callback)

             worker = Worker(task)
             worker.log_signal.connect(self.view.append_log)

             def on_finished(result):
                 if hasattr(result, "get") and result.get("success", False): # Use safe access if result could be None or bool
                     if result.get("restart_required", False):
                         if self.view.show_confirm("CCUA 默认配置恢复完成，需要重启 CCU 才能生效。\n是否立即重启 CCU？"):
                             # 启动新的 worker 执行重启
                             self._perform_ccu_reset()

                     self.view.show_message("操作执行完成", "success")
                 elif isinstance(result, bool) and result:
                      self.view.show_message("操作执行完成", "success")
                 else:
                     self.view.show_message("部分操作执行失败，请查看日志", "error")

             worker.result_signal.connect(on_finished)
             worker.start()

             self._workers.append(worker)
             worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

    def _perform_ccu_reset(self):
        from app.common.utils.worker import Worker
        def reset_task(log_callback):
            return self.log_config_service.reset_ccu(log_callback)

        worker = Worker(reset_task)
        worker.log_signal.connect(self.view.append_log)
        worker.start()
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

    def _on_modify_requested(self, row_index):
        if row_index < 0 or row_index >= len(self.model.apps):
            return

        app_info = self.model.apps[row_index]
        ecu_id = app_info[1]

        # 限制：仅支持修改 CCUA 的应用日志等级
        if ecu_id != "CCUA":
            # 使用 Toast 而不是弹窗，体验更好
            from app.common.ui.modern_widgets import MessageToast
            MessageToast(self.view).show_toast("目前只支持修改 CCUA 的应用日志等级", 1)
            # self.view.show_message("目前只支持修改 CCUA 的应用日志等级", "warning")
            return

        # 使用自定义的 LogConfigEditDialog 替代简单的 QInputDialog
        dialog = LogConfigEditDialog(self.view, app_info)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            new_level = dialog.get_new_level()
            app_id = app_info[0] # Re-extract just in case
            if new_level and new_level != app_info[2]: # Only update if changed
                self._handle_ccua_modification(app_id, new_level)
            else:
                self.view.append_log(f"{app_id}日志等级未变更")

    def _handle_ccua_modification(self, app_id, new_level):
        """处理 CCUA 专用的修改流程：Worker异步写入 -> 重启确认"""
        # 1. 提示并锁定 UI
        self.view.show_message("正在写入配置并同步文件，请稍候...", "info")

        # 2. 定义后台任务
        def task(log_callback):
            return self.log_config_service.update_ccua_app_config(app_id, new_level, log_callback)

        worker = Worker(task)
        # 将进度日志输出到界面
        worker.log_signal.connect(self.view.append_log)

        # 3. 定义完成回调
        def on_finished(success):
            if success:
                # 更新 Model 显示
                self.model.update_app_level(app_id, "CCUA", new_level)
                self.on_model_changed()

                # 弹出重启询问
                msg = f"应用 {app_id} 的日志等级已修改为 {new_level}。\n\n注意：该修改需要重启 CCU 才能生效。\n是否立即重启 CCU？"
                if self.view.show_confirm(msg):
                    # 执行重启
                    self.view.show_message("正在重启 CCUA，请稍候...", "warning")
                    self.log_config_service.restart_ccu("CCUA")
                else:
                    self.view.show_message("配置已保存，请择机重启设备以生效", "success")
            else:
                self.view.show_message("修改配置失败，请查看操作日志", "error")

        worker.result_signal.connect(on_finished)
        worker.start()

        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

    def on_model_changed(self):
        # 1. 更新表格内容
        self.view.populate(self.model.apps)

        # 2. 更新分页 UI 状态
        current = self.model.current_page
        total = self.model.total_pages

        self.view.prev_page_btn.setEnabled(current > 1)
        self.view.next_page_btn.setEnabled(current < total)

        if hasattr(self.view, 'page_info_label'):
             self.view.page_info_label.setText(f"第 {current} / {total} 页")

    def get_view(self):
        return self.view
