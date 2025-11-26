from PyQt5 import QtCore, QtWidgets

from app.common.ui.style import APP_STYLE
from app.core.base_controller import BaseController
from app.modules.device_management.controller.device_management_controller import DeviceController
from app.modules.device_topology.controller.device_topology_controller import TopologyController
from app.modules.device_upgrade.controller.device_upgrade_controller import UpgradeController
from app.modules.did_management.controller.did_management_controller import DIDController
from app.modules.dtc_management.controller.dtc_management_controller import DTCController
from app.modules.file_transfer.controller.file_transfer_controller import FileTransferController
from app.modules.log_config.controller.log_config_controller import LogConfigController
from app.modules.log_management.controller.log_management_controller import LogDownloadController
from app.modules.performance_management.controller.performance_management_controller import PerformanceController
from app.modules.script_exec.controller.script_exec_controller import ScriptExecController
from app.modules.uds_sequence.controller.uds_sequence_controller import UDSSequenceController
from app.presentation.model.main_window_model import MainModel
from app.presentation.views.main_window_view import MainView


class MainController(BaseController):
    def __init__(self):
        self.model = MainModel()
        self.view = MainView()
        super().__init__(self.model, self.view)
        self.view.setStyleSheet(APP_STYLE)
        self.view.workspace.tabCloseRequested.connect(self.close_tab)
        self.build_pages()
        self.build_navigation()
        self.view.nav_tree.itemClicked.connect(self.on_nav_item_clicked)

    def build_pages(self):
        # Instantiate controllers
        device = DeviceController(self.view)
        topology = TopologyController(self.view)
        dtc = DTCController(self.view)
        did = DIDController(self.view)
        log_download = LogDownloadController(self.view)
        file_transfer = FileTransferController(self.view)
        log_config = LogConfigController(self.view)
        upgrade = UpgradeController(self.view)
        script_exec = ScriptExecController(self.view)
        perf = PerformanceController(self.view)  # dialog
        uds = UDSSequenceController(self.view)   # dialog
        # Register (tab controllers)
        self.model.register("设备管理", device)
        self.model.register("拓扑监控", topology)
        self.model.register("DTC故障诊断", dtc)
        self.model.register("DID数据管理", did)
        self.model.register("日志下载", log_download)
        self.model.register("文件传输中心", file_transfer)
        self.model.register("日志配置", log_config)
        self.model.register("设备升级", upgrade)
        self.model.register("脚本执行", script_exec)
        # Register dialogs separately
        self.model.register("性能监控", perf)
        self.model.register("UDS指令编排", uds)
        # Add tabs (order similar to original)
        self.view.workspace.addTab(device.get_view(), "📁 设备管理")
        self.view.workspace.addTab(topology.get_view(), "📊 拓扑监控")
        self.view.workspace.addTab(dtc.get_view(), "⚠️ DTC故障诊断")
        self.view.workspace.addTab(did.get_view(), "🔍 DID数据管理")
        self.view.workspace.addTab(file_transfer.get_view(), "🔄 文件传输中心")
        self.view.workspace.addTab(log_config.get_view(), "📝 日志配置")
        self.view.workspace.addTab(upgrade.get_view(), "🚀 设备升级")
        self.view.workspace.addTab(script_exec.get_view(), "📝 脚本执行")
        self.view.workspace.addTab(log_download.get_view(), "📥 日志下载")

    def build_navigation(self):
        structure = {
            "🏎️ 设备管理": {"children": ["📁 设备管理", "📊 拓扑监控", "⚙️ 性能监控"]},
            "🛠 诊断功能": {"children": ["⚠️ DTC故障诊断", "🔍 DID数据管理", "🧪 UDS指令编排"]},
            "📂 文件管理": {"children": ["🔄 文件传输中心", "📥 日志下载"]},
            "⚙️ 配置中心": {"children": ["📝 日志配置", "🚀 设备升级"]},
            "🧬 高级功能": {"children": ["📝 脚本执行"]},
        }
        self.view.build_navigation(structure)

    def on_nav_item_clicked(self, item, column):
        if item.data(0, QtCore.Qt.UserRole) != "function":
            return
        text = item.text(0)
        # Map display text to registry keys
        mapping = {
            "📁 设备管理": "设备管理",
            "📊 拓扑监控": "拓扑监控",
            "⚠️ DTC故障诊断": "DTC故障诊断",
            "🔍 DID数据管理": "DID数据管理",
            "📥 日志下载": "日志下载",
            "🔄 文件传输中心": "文件传输中心",
            "📝 日志配置": "日志配置",
            "🚀 设备升级": "设备升级",
            "📝 脚本执行": "脚本执行",
            "⚙️ 性能监控": "性能监控",
            "🧪 UDS指令编排": "UDS指令编排",
        }
        key = mapping.get(text)
        controller = self.model.get(key) if key else None
        # Dialogs: show directly
        if key in ["性能监控", "UDS指令编排"] and controller:
            controller.show_dialog()
            return
        # Tabs: select if exists, otherwise recreate and open
        # 1) try to select existing tab
        for i in range(self.view.workspace.count()):
            if self.view.workspace.tabText(i) == text:
                self.view.workspace.setCurrentIndex(i)
                return
        # 2) recreate closed tab
        if controller and hasattr(controller, "get_view"):
            view_widget = controller.get_view()
            self.view.workspace.addTab(view_widget, text)
            self.view.workspace.setCurrentIndex(self.view.workspace.count() - 1)

    def close_tab(self, index):
        if self.view.workspace.count() > 1:
            self.view.workspace.removeTab(index)

    def get_view(self):
        return self.view

