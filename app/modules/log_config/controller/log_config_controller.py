import logging

from PyQt5 import QtCore, QtWidgets

from app.common.utils.worker import Worker  # 引入 Worker
from app.core.base_controller import BaseController
from app.core.dependency_injection import di_container
from app.modules.log_config.model.log_config_model import LogConfigModel
from app.modules.log_config.view.log_config_view import LogConfigView, LogConfigEditDialog
from app.services.configuration.log_config_service import LogConfigService
from app.services.device_manage.device_service import DeviceService
from app.common.utils.config_center import ConfigCenter  # Add ConfigCenter import
from app.common.ui.modern_widgets import MessageToast

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


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
            device_service.protocol_status_changed_signal.connect(self._on_restore_protocol_status_changed)

        # Load persisted map path
        saved_path = ConfigCenter.get_log_map_path()
        if saved_path:
            self.view.map_path_edit.setText(saved_path)
            self.log_config_service.set_map_file_path(saved_path)
            self.view.append_log(f"已恢复配置文件路径: {saved_path}")
            mapping = self.log_config_service._load_process_log_config_mapping()
            self.view.append_log(f"已恢复的映射文件可用条目数: {len(mapping)}")
            if not mapping:
                self.view.append_log("当前本地映射文件未解析到有效 process_log_configs 条目，请先检查 JSON 文件内容")

        self._workers = []
        self._is_ecu_executing = False
        self._is_restore_executing = False
        self._restore_waiting_reconnect = False
        self._restore_target_ip = None
        self._restore_reconnect_timer = QtCore.QTimer(self.view)
        self._restore_reconnect_timer.setSingleShot(True)
        self._restore_reconnect_timer.timeout.connect(self._on_restore_reconnect_timeout)
        self._bind_signals()

        # # 进入界面后自动触发一次全量刷新，避免下拉框为空
        # QtCore.QTimer.singleShot(100, self._on_app_refresh)

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

        self.log_config_service.log_signal.connect(self.update_log)

    def update_log(self, message):
        self.view.append_log(message)
        logger.info(message)

    def _set_restore_busy(self, busy: bool, progress_text: str = ""):
        self._is_restore_executing = busy
        self.view.restore_btn.setEnabled(not busy)
        self.view.set_restore_progress(busy, progress_text, busy=True)

    def _finish_restore_flow(self, message: str = "", msg_type: str = "info"):
        self._restore_waiting_reconnect = False
        self._restore_target_ip = None
        self._restore_reconnect_timer.stop()
        self._set_restore_busy(False)
        if message:
            self.view.show_message(message, msg_type)

    def _on_restore_protocol_status_changed(self, payload: dict):
        if not self._restore_waiting_reconnect:
            return

        target_ip = self._restore_target_ip
        if target_ip and payload.get("ip") != target_ip:
            return

        doip_status = str(payload.get("doip_connect_status", ""))
        ssh_status = str(payload.get("ssh_connect_status", ""))
        generation = payload.get("_connection_generation", "--")

        doip_ready = "建链成功" in doip_status
        ssh_ready = "建链成功" in ssh_status

        if doip_ready and ssh_ready:
            self.view.append_log(f"CCUA 重连成功: generation={generation} | DoIP={doip_status} | SSH={ssh_status or '--'}")
            self._finish_restore_flow("CCUA 已重启并完成重连", "success")
            return

        if doip_ready and not ssh_ready:
            self.view.set_restore_progress(True, f"DoIP 已恢复，等待 SSH 就绪... (generation={generation}, 当前 SSH: {ssh_status or '--'})", busy=True)

        doip_failed = "连接失败" in doip_status
        ssh_failed = "连接失败" in ssh_status
        still_connecting = ("连接中" in doip_status) or ("连接中" in ssh_status)

        if (doip_failed or ssh_failed) and not still_connecting:
            self.view.append_log(f"CCUA 重连失败: generation={generation} | DoIP={doip_status} | SSH={ssh_status or '--'}")
            self._finish_restore_flow("CCUA 重启后重连失败，请检查设备连接", "error")

    def _on_restore_reconnect_timeout(self):
        if self._restore_waiting_reconnect:
            self.view.append_log("等待 CCUA 重连超时")
            self._finish_restore_flow("CCUA 重启后等待重连超时，请手动检查设备状态", "warning")

    def _format_ecu_execute_result_text(self, result):
        def fmt_byte(value):
            return "--" if value is None else f"{int(value):02X}"

        requested_level = result.get("requested_level", "")
        requested_level_value = result.get("requested_level_value")
        success_count = result.get("success_count", 0)
        total_count = result.get("total_count", 0)
        lines = [
            f"设置目标日志等级: {requested_level} ({requested_level_value if requested_level_value is not None else '--'})",
            f"执行结果成功率: {success_count}/{total_count}",
            "",
        ]

        for item in result.get("results", []):
            ecu = item.get("ecu", "未知ECU")
            did = item.get("did", "----")
            read_value = item.get("read_value")
            write_value = item.get("write_value")
            verify_value = item.get("verify_value")
            warning = item.get("warning") or ""
            error = item.get("error") or ""

            if item.get("success"):
                line = (
                    f"✓ {ecu} (DID {did}) | 读: {fmt_byte(read_value)} | "
                    f"写: {fmt_byte(write_value)} | 回读: {fmt_byte(verify_value)}"
                )
                if warning:
                    line += f"\n  提示: {warning}"
            # else:
            #     line = f"✗ {ecu} (DID {did}) | {error or '执行失败'}"
            lines.append(line)

        return "\n".join(lines)

    def _on_import_map(self):
        from PyQt5 import QtWidgets
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.view, "选择日志配置文件", "", "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.view.append_log(f"开始导入日志配置映射文件: {file_path}")
            self.view.map_path_edit.setText(file_path)
            self.log_config_service.set_map_file_path(file_path)
            # Save path to config center
            ConfigCenter.set_log_map_path(file_path)
            mapping = self.log_config_service._load_process_log_config_mapping()
            mapping_count = len(mapping)
            self.view.append_log(f"导入完成：process_log_configs 共 {mapping_count} 个条目")
            if mapping_count > 0:
                self.view.show_message(f"已加载配置文件: {file_path}", "success")
            else:
                self.view.show_message("配置文件已加载，但 process_log_configs 为 0，请先检查本地 JSON 内容", "warning")
            # 如果 APP tab 需要依赖此文件刷新，可以在这里调用刷新
            # self._on_app_refresh()

    def _on_ecu_execute(self):
        if self._is_ecu_executing:
            self.view.show_message("ECU 日志等级配置执行中，请稍候...", "info")
            return

        selected_ecus = list(self.view.ecu_select_combo.currentSelection())
        log_level = self.view.ecu_log_level_combo.currentText().strip().upper()
        if not selected_ecus:
            self.view.show_message("请选择至少一个 ECU", "warning")
            return

        # 检查设备是否连接
        device_service = self.log_config_service._device_service
        doip_client = device_service.get_doip_client() if device_service else None
        is_connected = False
        if doip_client:
            is_connected = doip_client.is_connected() if hasattr(doip_client, "is_connected") else bool(getattr(doip_client, "connected", False))
        if not is_connected:
            self.view.show_message("设备未连接 (DoIP)，无法执行配置", "error")
            return

        self._is_ecu_executing = True
        self.view.ecu_execute_btn.setEnabled(False)
        self.view.show_message(f"开始执行 {len(selected_ecus)} 个 ECU 的日志等级配置", "info")
        self.view.append_log(
            f"目标日志等级={log_level} | 目标ECU={'、'.join(selected_ecus)}"
        )

        def task():
            return self.log_config_service.set_ecu_log_level(selected_ecus, log_level)

        worker = Worker(task)
        # 连接日志信号到 View 的 append_log
        worker.log_signal.connect(self.view.append_log)

        def on_finished(result):
            self._is_ecu_executing = False
            self.view.ecu_execute_btn.setEnabled(True)

            if not isinstance(result, dict):
                self.view.append_log("ECU 日志等级配置执行失败：返回结果为空或格式异常")
                self.view.show_message("执行失败，请检查操作日志", "error")
                return

            summary = self._format_ecu_execute_result_text(result)
            for line in summary.splitlines():
                if line.strip():
                    self.view.append_log(line)

            if result.get("success"):
                self.view.show_message(
                    f"已完成 {result.get('success_count', 0)}/{result.get('total_count', 0)} 个 ECU 的日志等级配置",
                    "info"
                )
            elif result.get("success_count", 0) > 0:
                self.view.show_message(
                    f"部分 ECU 配置成功：{result.get('success_count', 0)}/{result.get('total_count', 0)}",
                    "warning"
                )
            else:
                self.view.show_message("所有 ECU 日志等级配置均失败，请检查日志", "error")

        worker.result_signal.connect(on_finished)
        worker.start()
        # Keep reference to avoid GC
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

    def _on_app_search(self):
        # 0. 检查是否已导入配置文件
        if not self.log_config_service._map_file_path:
             MessageToast(self.view).show_toast("请先导入 process_log_config_map.json 配置文件", 1) # 1=warning/error style
             return

        # 1. 获取 UI 参数（必须在主线程完成）
        ecu_id = self.view.app_filter_ecu_combo.currentText()
        app_id = self.view.app_filter_appid_combo.currentText()
        log_level = self.view.app_filter_loglevel_combo.currentText()

        # 将 "全部" 转换为空字符串，以便 Service 层识别为不筛选
        if ecu_id == "全部": ecu_id = ""
        if app_id == "全部": app_id = ""
        if log_level == "全部": log_level = ""

        # 在 Controller 里增加一个标志位，防止重复点击，而不是禁用按钮
        if getattr(self, '_is_searching', False):
             self.view.show_message("正在执行搜索中，请稍候...", "info")
             return
        self._is_searching = True

        self.view.append_log(
            f"正在获取配置... 筛选条件: ECU={ecu_id or '全部'} | APPID={app_id or '全部'} | LOGLevel={log_level or '全部'}"
        )

        # 2. 定义后台任务
        def search_task():
            return self.log_config_service.get_apps(ecu_id, app_id, log_level)

        # 3. 定义完成回调
        def on_search_finished(result):
            # 任务结束，释放标志位
            self._is_searching = False
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
            if all_apps:
                self.view.show_message(f"加载完成，共 {len(all_apps)} 个应用", "info")
            else:
                self.view.show_message("加载完成，共 0 个应用；请查看操作日志中的具体原因", "warning")

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
        """批量修改日志配置 (Batch)"""
        # 1. 弹出编辑框获取目标配置
        info_mock = ["已选应用", "CCUA", "", ""] # Mock info just to reuse dialog layout

        dialog = LogConfigEditDialog(self.view, info_mock)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return

        new_level = dialog.get_new_level()
        new_mode = dialog.get_new_mode()

        if not new_level.strip():
            return

        target_apps = [item[0] for item in self.model.apps if item[1] == "CCUA"]

        if not target_apps:
            self.view.show_message("当前列表无 CCUA 应用可修改", "warning")
            return

        msg = f"即将批量修改 {len(target_apps)} 个 CCUA 应用的日志配置：\n\n等级 -> {new_level}"
        if new_mode:
            msg += f"\n模式 -> {new_mode}"
        msg += "\n\n修改将在后台通过 SSH 执行，完成后需重启 CCU 生效。\n是否继续？"

        if not self.view.show_confirm(msg):
            return

        # 3. Worker 执行
        def task():
            return self.log_config_service.batch_update_ccua_apps(target_apps, new_level, new_mode)

        worker = Worker(task)
        worker.log_signal.connect(self.view.append_log)

        def on_complete(success):
            if success:
                # Refresh UI
                if self.log_config_service.restart_ccu("CCUA"):
                     self.view.show_message("批量修改完成，CCU正在重启...", "success")
                else:
                     self.view.show_message("批量修改完成，但重启命令发送异常，请手动重启", "warning")
                # Reload (Wait a bit?) -> Actually reboot disconnects.
            else:
                self.view.show_message("批量修改部分失败，请检查日志", "error")

        worker.result_signal.connect(on_complete)
        worker.start()
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

    def _do_restart_ccu(self):
        """执行 CCU 重启"""
        self.view.append_log("正在请求重启 CCU...")

        def restart_task():
            return self.log_config_service.restart_ccu(ecu="CCUA")

        def on_restart_finished(success):
            if success:
                self.view.show_message("重启指令已发送", "success")
            else:
                self.view.show_message("重启失败", "error")

        worker = Worker(restart_task)
        worker.result_signal.connect(on_restart_finished)
        worker.start()
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)


    def _on_restore_config(self):
        if self._is_restore_executing:
            self.view.show_message("恢复操作执行中，请稍候...", "info")
            return

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
            MessageToast(self.view).show_toast("请选择至少一项恢复操作", 1)
            return

        device_service = self.log_config_service._device_service
        requires_doip = restore_ccua or restore_ccu0 or restore_ccu1
        doip_client = device_service.get_doip_client() if (device_service and requires_doip) else None
        doip_connected = False
        if doip_client:
            doip_connected = doip_client.is_connected() if hasattr(doip_client, "is_connected") else bool(getattr(doip_client, "connected", False))

        if requires_doip and not doip_connected:
            self.view.show_message("设备未连接 (DoIP)，无法执行恢复操作", "error")
            return

        summary_lines = []
        if restore_ccua:
            summary_lines.append("- 恢复 CCUA 默认配置")
        if restore_ccu0:
            summary_lines.append("- 恢复 CCU0 默认配置")
        if restore_ccu1:
            summary_lines.append("- 恢复 CCU1 默认配置")
        if delete_logs:
            summary_lines.append("- 删除 /log 下所有 DLT 日志文件")

        if not self.view.show_confirm("确定执行以下操作吗？\n\n" + "\n".join(summary_lines)):
            return

        if delete_logs:
            if not self.view.show_confirm("确定要删除 /log 下所有 DLT 日志文件吗？\n\n该操作不可恢复。"):
                return

            ssh_client = device_service.get_ssh_client() if device_service else None
            if not ssh_client or not ssh_client.is_connected():
                self.view.show_message("设备未连接 (SSH)，无法执行删除日志操作", "error")
                return

        self._set_restore_busy(True, "正在执行恢复操作，请稍候...")
        self.view.append_log("[恢复默认配置] 开始执行")
        for line in summary_lines:
            self.view.append_log(line)

        def task():
            return self.log_config_service.restore_config(options)

        worker = Worker(task)
        worker.log_signal.connect(self.view.append_log)

        def on_finished(result):
            if not isinstance(result, dict):
                self._finish_restore_flow("恢复操作执行失败，请检查日志", "error")
                return

            for line in result.get("summary_lines", []):
                self.view.append_log(line)

            if not result.get("success", False):
                self._finish_restore_flow("部分恢复操作失败，请检查日志", "error")
                return

            if options.get("restore_ccua") and result.get("restart_required", False):
                confirm_restart = self.view.show_confirm(
                    "CCUA 默认配置恢复完成。\n\n需要重启 CCU 才能生效，是否立即重启？"
                )
                if not confirm_restart:
                    self._finish_restore_flow("恢复完成，请稍后手动重启 CCUA 使配置生效", "warning")
                    return

                self.view.append_log("用户确认立即重启 CCUA")
                self.view.set_restore_progress(True, "CCUA 正在重启，正在重连设备...", busy=True)

                def restart_task():
                    return self.log_config_service.restart_ccu("CCUA")

                restart_worker = Worker(restart_task)
                restart_worker.log_signal.connect(self.view.append_log)

                def on_restart_finished(ok):
                    if not ok:
                        self._finish_restore_flow("CCUA 重启指令发送失败", "error")
                        return

                    self._restore_waiting_reconnect = True
                    self._restore_target_ip = device_service.get_current_device_ip() if device_service else None
                    self._restore_reconnect_timer.start(120000)
                    # self.view.append_log("CCUA 重启指令已发送，进入最长 120s 的自动重连等待窗口...")

                restart_worker.result_signal.connect(on_restart_finished)
                restart_worker.start()
                self._workers.append(restart_worker)
                restart_worker.finished.connect(
                    lambda: self._workers.remove(restart_worker) if restart_worker in self._workers else None
                )
                return

            self._finish_restore_flow("恢复操作执行完成", "info")

        worker.result_signal.connect(on_finished)
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
        # 2. 定义后台任务
        def task():
            return self.log_config_service.update_ccua_app_config(app_id, new_level)

        worker = Worker(task)
        # 将进度日志输出到界面
        worker.log_signal.connect(self.view.append_log)

        # 3. 定义完成回调
        def on_finished(success):
            if success:
                # 更新 Model 显示
                self.model.update_app_level(app_id, "CCUA", new_level)
                self.on_model_changed()

                # 刷新 UI，确保用户先看到表格变化
                QtWidgets.QApplication.processEvents()

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
        start_index = (self.model.current_page - 1) * self.model.page_size + 1
        self.view.populate(self.model.apps, start_index=start_index)

        # 2. 更新分页 UI 状态
        current = self.model.current_page
        total = self.model.total_pages

        self.view.prev_page_btn.setEnabled(current > 1)
        self.view.next_page_btn.setEnabled(current < total)

        if hasattr(self.view, 'page_info_label'):
             self.view.page_info_label.setText(f"第 {current} / {total} 页")

    def get_view(self):
        return self.view
