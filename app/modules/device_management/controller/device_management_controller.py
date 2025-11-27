from PyQt5 import QtWidgets
from app.core.base_controller import BaseController
from app.modules.device_management.models.device_model import DeviceModel
from app.modules.device_management.views.device_management_view import DeviceView


class DeviceController(BaseController):
    def __init__(self, parent=None):
        self.model = DeviceModel(parent, seed_initial=True)
        self.view = DeviceView(parent)
        super().__init__(self.model, self.view, parent)
        self._connect_static_signals()
        self._log_initial_devices()

        # 关键：首次主动刷新视图，确保示例数据渲染到表格
        self.on_model_changed()

    def _connect_static_signals(self):
        self.view.add_btn.clicked.connect(self._on_add_clicked)

    def _log_initial_devices(self):
        if not self.model.devices:
            return
        self.view.append_log("初始化设备列表:")
        for i, d in enumerate(self.model.devices, 1):
            self.view.append_log(f"  {i}. {d['name']} {d['ip']}:{d['port']} 状态={d['status']}")

    def _on_add_clicked(self):
        name = self.view.name_input.text().strip()
        ip = self.view.ip_input.text().strip()
        port_text = self.view.port_input.text().strip() or "22"
        user = self.view.user_input.text().strip() or "root"

        if not name or not ip:
            QtWidgets.QMessageBox.warning(self.view, "提示", "设备名与IP不能为空")
            return
        try:
            port = int(port_text)
        except ValueError:
            QtWidgets.QMessageBox.warning(self.view, "提示", "端口必须为数字")
            return

        self.model.add_device(name, ip, port, user)
        self.view.append_log(f"添加设备: {name} ({ip}:{port})")
        self.view.name_input.clear()
        self.view.ip_input.clear()
        self.view.port_input.clear()
        self.view.user_input.clear()

    def on_model_changed(self):
        self.view.populate(self.model.devices)
        self._bind_row_buttons()

    def _bind_row_buttons(self):
        table = self.view.table
        row_count = table.rowCount()
        for row in range(row_count):
            action_widget = table.cellWidget(row, 6)
            if not action_widget:
                continue
            buttons = {}
            for child in action_widget.findChildren(QtWidgets.QAbstractButton):
                buttons[child.text()] = child
            if "连接设备" in buttons:
                buttons["连接设备"].clicked.connect(lambda _, r=row: self._do_connect(r))
            if "断开连接" in buttons:
                buttons["断开连接"].clicked.connect(lambda _, r=row: self._do_disconnect(r))
            if "删除设备" in buttons:
                buttons["删除设备"].clicked.connect(lambda _, r=row: self._do_delete(r))
            if "软件升级" in buttons:
                buttons["软件升级"].clicked.connect(lambda _, r=row: self._do_upgrade(r))
            if "状态查询" in buttons:
                buttons["状态查询"].clicked.connect(lambda _, r=row: self._do_query(r))
            if "远程登录" in buttons:
                buttons["远程登录"].clicked.connect(lambda _, r=row: self._do_remote(r))
            detail_widget = table.cellWidget(row, 5)
            if detail_widget:
                for child in detail_widget.findChildren(QtWidgets.QAbstractButton):
                    child.clicked.connect(lambda _, r=row: self._show_detail(r))

    def _device_repr(self, index):
        d = self.model.devices[index]
        return f"{d.get('name')} {d.get('ip')}:{d.get('port')}"

    def _show_detail(self, index):
        d = self.model.devices[index]
        msg = "\n".join([
            f"设备名: {d.get('name')}",
            f"IP: {d.get('ip')}",
            f"端口: {d.get('port')}",
            f"用户: {d.get('user')}",
            f"状态: {d.get('status')}",
            f"最后刷新: {d.get('last_refresh', '--')}",
        ])
        QtWidgets.QMessageBox.information(self.view, "设备详情", msg)
        self.view.append_log(f"查看详情 -> {self._device_repr(index)}")

    def _do_connect(self, index):
        self.model.connect_device(index)
        self.view.append_log(f"连接设备 -> {self._device_repr(index)}")

    def _do_disconnect(self, index):
        self.model.disconnect_device(index)
        self.view.append_log(f"断开设备 -> {self._device_repr(index)}")

    def _do_delete(self, index):
        name = self._device_repr(index)
        self.model.delete_device(index)
        self.view.append_log(f"删除设备 -> {name}")

    def _do_upgrade(self, index):
        self.model.upgrade_device(index)
        self.view.append_log(f"软件升级触发 -> {self._device_repr(index)}")

    def _do_query(self, index):
        self.model.query_status(index)
        self.view.append_log(f"状态查询 -> {self._device_repr(index)}")

    def _do_remote(self, index):
        self.model.remote_login(index)
        self.view.append_log(f"远程登录 -> {self._device_repr(index)}")

    def get_view(self):
        return self.view
