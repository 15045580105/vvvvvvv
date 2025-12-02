# 控制器类导入
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

# 页面类型常量
PAGE_TYPE_TAB = False
PAGE_TYPE_DIALOG = True

# 页面emoji常量
EMOJI_DEVICE = "📁"
EMOJI_TOPOLOGY = "📊"
EMOJI_DTC = "⚠️"
EMOJI_DID = "🔍"
EMOJI_LOG_DOWNLOAD = "📥"
EMOJI_FILE_TRANSFER = "🔄"
EMOJI_LOG_CONFIG = "📝"
EMOJI_UPGRADE = "🚗"
EMOJI_SCRIPT = "🧭"
EMOJI_PERFORMANCE = "⚙️"
EMOJI_UDS = "🧪"

# 页面注册名常量
PAGE_DEVICE = "设备管理"
PAGE_TOPOLOGY = "拓扑监控"
PAGE_DTC = "DTC故障诊断"
PAGE_DID = "DID数据管理"
PAGE_LOG_DOWNLOAD = "日志下载"
PAGE_FILE_TRANSFER = "文件传输中心"
PAGE_LOG_CONFIG = "日志配置"
PAGE_UPGRADE = "设备升级"
PAGE_SCRIPT = "脚本执行"
PAGE_PERFORMANCE = "性能监控"
PAGE_UDS = "UDS指令编排"


# 导航分组常量
NAV_GROUP_DEVICE = "🏎️ 设备管理"
NAV_GROUP_DIAG = "🛠 诊断功能"
NAV_GROUP_FILE = "📂 文件管理"
NAV_GROUP_UPGRADE = "🚀 设备升级"
NAV_GROUP_CONFIG = "⚙️ 配置中心"
NAV_GROUP_ADV = "🧬 高级功能"

# 统一页面定义：(注册名, 显示名, 控制器类, 是否对话框)
PAGE_DEFINITIONS = [
    (PAGE_DEVICE, f"{EMOJI_DEVICE} {PAGE_DEVICE}", DeviceController, PAGE_TYPE_TAB),
    (PAGE_TOPOLOGY, f"{EMOJI_TOPOLOGY} {PAGE_TOPOLOGY}", TopologyController, PAGE_TYPE_TAB),
    (PAGE_DTC, f"{EMOJI_DTC} {PAGE_DTC}", DTCController, PAGE_TYPE_TAB),
    (PAGE_DID, f"{EMOJI_DID} {PAGE_DID}", DIDController, PAGE_TYPE_TAB),
    (PAGE_LOG_DOWNLOAD, f"{EMOJI_LOG_DOWNLOAD} {PAGE_LOG_DOWNLOAD}", LogDownloadController, PAGE_TYPE_TAB),
    (PAGE_FILE_TRANSFER, f"{EMOJI_FILE_TRANSFER} {PAGE_FILE_TRANSFER}", FileTransferController, PAGE_TYPE_TAB),
    (PAGE_LOG_CONFIG, f"{EMOJI_LOG_CONFIG} {PAGE_LOG_CONFIG}", LogConfigController, PAGE_TYPE_TAB),
    (PAGE_UPGRADE, f"{EMOJI_UPGRADE} {PAGE_UPGRADE}", UpgradeController, PAGE_TYPE_TAB),
    (PAGE_SCRIPT, f"{EMOJI_SCRIPT} {PAGE_SCRIPT}", ScriptExecController, PAGE_TYPE_TAB),
    (PAGE_PERFORMANCE, f"{EMOJI_PERFORMANCE} {PAGE_PERFORMANCE}", PerformanceController, PAGE_TYPE_DIALOG),
    (PAGE_UDS, f"{EMOJI_UDS} {PAGE_UDS}", UDSSequenceController, PAGE_TYPE_DIALOG),
]

# 自动推导各类页面结构，避免重复
TAB_PAGES = [(k, d, c) for k, d, c, is_dialog in PAGE_DEFINITIONS if not is_dialog]
DIALOG_PAGES = [(k, c) for k, d, c, is_dialog in PAGE_DEFINITIONS if is_dialog]
PAGE_CONFIG = [(k, d) for k, d, c, is_dialog in PAGE_DEFINITIONS]
PAGE_KEYS = [k for k, _ in PAGE_CONFIG]
PAGE_DISPLAY_TEXTS = [d for _, d in PAGE_CONFIG]
PAGE_TEXT_TO_KEY = dict(PAGE_CONFIG)



# 导航树结构
NAV_STRUCTURE = {
    NAV_GROUP_DEVICE: {"children": [f"{EMOJI_DEVICE} {PAGE_DEVICE}",
                                    f"{EMOJI_TOPOLOGY} {PAGE_TOPOLOGY}",
                                    f"{EMOJI_PERFORMANCE} {PAGE_PERFORMANCE}"]},
    NAV_GROUP_DIAG: {"children": [f"{EMOJI_DTC} {PAGE_DTC}",
                                  f"{EMOJI_DID} {PAGE_DID}",
                                  f"{EMOJI_UDS} {PAGE_UDS}"]},
    NAV_GROUP_FILE: {"children": [f"{EMOJI_FILE_TRANSFER} {PAGE_FILE_TRANSFER}",
                                  f"{EMOJI_LOG_DOWNLOAD} {PAGE_LOG_DOWNLOAD}"]},
    NAV_GROUP_UPGRADE: {"children": [f"{EMOJI_UPGRADE} {PAGE_UPGRADE}"]},
    NAV_GROUP_CONFIG: {"children": [f"{EMOJI_LOG_CONFIG} {PAGE_LOG_CONFIG}"]},
    NAV_GROUP_ADV: {"children": [f"{EMOJI_SCRIPT} {PAGE_SCRIPT}"]},
}
