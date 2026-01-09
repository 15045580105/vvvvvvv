# 控制器类导入（放在基础常量之后，避免循环导入）
from app.modules.demo_page.controller.demo_page_controller import DemoPageController
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
from app.modules.clock_management.controller.clock_management_controller import ClockManagementController
from app.modules.bus_data_management.controller.bus_data_download_controller import BusDataDownloadController
from app.modules.data_format_converter.controller.data_format_converter_controller import DataFormatConverterController
from app.modules.common_config.controller.common_config_controller import CommonConfigController

class PageConfig:
    """页面配置管理类，封装所有页面相关的常量和配置。"""

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
    EMOJI_CLOCK = "⏰"
    # 新增：总线数据下载 emoji
    EMOJI_BUS_DATA_DOWNLOAD = "📡"
    # 新增：数据格式转换 emoji
    EMOJI_DATA_CONVERTER = "🧩"
    # 新增：常用配置 emoji
    EMOJI_COMMON_CONFIG = "🔧"

    # 页面注册名常量
    PAGE_DEVICE = "设备管理"
    PAGE_TOPOLOGY = "拓扑监控"
    PAGE_DTC = "DTC故障诊断"
    PAGE_DID = "DID数据管理"
    PAGE_LOG_DOWNLOAD = "日志文件下载"
    PAGE_BUS_DATA_DOWNLOAD = "总线数据下载"
    PAGE_FILE_TRANSFER = "文件传输中心"
    PAGE_LOG_CONFIG = "日志配置"
    PAGE_COMMON_CONFIG = "常用配置"
    PAGE_UPGRADE = "设备升级"
    PAGE_SCRIPT = "脚本执行"
    PAGE_PERFORMANCE = "性能监控"
    PAGE_UDS = "UDS指令编排"
    PAGE_CLOCK = "时钟管理"
    PAGE_DATA_CONVERTER = "数据格式转换"
    PAGE_DEMO = "示例页面"

    # 导航分组常量（之前缺失，补上）
    NAV_GROUP_DEVICE = "🏎️ 设备管理"
    NAV_GROUP_DIAG = "🛠 诊断功能"
    NAV_GROUP_FILE = "📂 文件管理"
    NAV_GROUP_UPGRADE = "🚀 设备升级"
    NAV_GROUP_CONFIG = "⚙️ 配置中心"
    NAV_GROUP_ADV = "🧬 高级功能"
    NAV_GROUP_DEMO = "🎉 示例"

    # 页面显示名常量（带emoji，用于Tab标签等）
    PAGE_DEVICE_DISPLAY = f"{EMOJI_DEVICE} {PAGE_DEVICE}"
    PAGE_TOPOLOGY_DISPLAY = f"{EMOJI_TOPOLOGY} {PAGE_TOPOLOGY}"
    PAGE_DTC_DISPLAY = f"{EMOJI_DTC} {PAGE_DTC}"
    PAGE_DID_DISPLAY = f"{EMOJI_DID} {PAGE_DID}"
    PAGE_LOG_DOWNLOAD_DISPLAY = f"{EMOJI_LOG_DOWNLOAD} {PAGE_LOG_DOWNLOAD}"
    PAGE_BUS_DATA_DOWNLOAD_DISPLAY = f"{EMOJI_BUS_DATA_DOWNLOAD} {PAGE_BUS_DATA_DOWNLOAD}"
    PAGE_FILE_TRANSFER_DISPLAY = f"{EMOJI_FILE_TRANSFER} {PAGE_FILE_TRANSFER}"
    PAGE_LOG_CONFIG_DISPLAY = f"{EMOJI_LOG_CONFIG} {PAGE_LOG_CONFIG}"
    PAGE_COMMON_CONFIG_DISPLAY = f"{EMOJI_COMMON_CONFIG} {PAGE_COMMON_CONFIG}"
    PAGE_UPGRADE_DISPLAY = f"{EMOJI_UPGRADE} {PAGE_UPGRADE}"
    PAGE_SCRIPT_DISPLAY = f"{EMOJI_SCRIPT} {PAGE_SCRIPT}"
    PAGE_PERFORMANCE_DISPLAY = f"{EMOJI_PERFORMANCE} {PAGE_PERFORMANCE}"
    PAGE_UDS_DISPLAY = f"{EMOJI_UDS} {PAGE_UDS}"
    PAGE_CLOCK_DISPLAY = f"{EMOJI_CLOCK} {PAGE_CLOCK}"
    PAGE_DATA_CONVERTER_DISPLAY = f"{EMOJI_DATA_CONVERTER} {PAGE_DATA_CONVERTER}"
    PAGE_DEMO_DISPLAY = f"🎉 {PAGE_DEMO}"


    # 二级菜单Tab名称常量（用于跳转等调用）
    DEVICE_MANAGEMENT_TAB_NAME = PAGE_DEVICE_DISPLAY
    TOPOLOGY_MONITOR_TAB_NAME = PAGE_TOPOLOGY_DISPLAY
    PERFORMANCE_MONITOR_TAB_NAME = PAGE_PERFORMANCE_DISPLAY
    DTC_DIAGNOSTIC_TAB_NAME = PAGE_DTC_DISPLAY
    DID_MANAGEMENT_TAB_NAME = PAGE_DID_DISPLAY
    UDS_SEQUENCE_TAB_NAME = PAGE_UDS_DISPLAY
    FILE_TRANSFER_TAB_NAME = PAGE_FILE_TRANSFER_DISPLAY
    LOG_DOWNLOAD_TAB_NAME = PAGE_LOG_DOWNLOAD_DISPLAY
    BUS_DATA_DOWNLOAD_TAB_NAME = PAGE_BUS_DATA_DOWNLOAD_DISPLAY
    DEVICE_UPGRADE_TAB_NAME = PAGE_UPGRADE_DISPLAY
    LOG_CONFIG_TAB_NAME = PAGE_LOG_CONFIG_DISPLAY
    COMMON_CONFIG_TAB_NAME = PAGE_COMMON_CONFIG_DISPLAY
    SCRIPT_EXEC_TAB_NAME = PAGE_SCRIPT_DISPLAY
    CLOCK_MANAGEMENT_TAB_NAME = PAGE_CLOCK_DISPLAY
    DATA_CONVERTER_TAB_NAME = PAGE_DATA_CONVERTER_DISPLAY
    DEMO_TAB_NAME = PAGE_DEMO_DISPLAY

    # 统一页面定义：(注册名, 显示名, 控制器类, 是否对话框)
    PAGE_DEFINITIONS = [
        (PAGE_DEVICE, PAGE_DEVICE_DISPLAY, DeviceController, PAGE_TYPE_TAB),
        (PAGE_TOPOLOGY, PAGE_TOPOLOGY_DISPLAY, TopologyController, PAGE_TYPE_TAB),
        (PAGE_DTC, PAGE_DTC_DISPLAY, DTCController, PAGE_TYPE_TAB),
        (PAGE_DID, PAGE_DID_DISPLAY, DIDController, PAGE_TYPE_TAB),
        (PAGE_LOG_DOWNLOAD, PAGE_LOG_DOWNLOAD_DISPLAY, LogDownloadController, PAGE_TYPE_TAB),
        (PAGE_BUS_DATA_DOWNLOAD, PAGE_BUS_DATA_DOWNLOAD_DISPLAY, BusDataDownloadController, PAGE_TYPE_TAB),
        (PAGE_DATA_CONVERTER, PAGE_DATA_CONVERTER_DISPLAY, DataFormatConverterController, PAGE_TYPE_TAB),
        (PAGE_FILE_TRANSFER, PAGE_FILE_TRANSFER_DISPLAY, FileTransferController, PAGE_TYPE_TAB),
        (PAGE_LOG_CONFIG, PAGE_LOG_CONFIG_DISPLAY, LogConfigController, PAGE_TYPE_TAB),
        (PAGE_COMMON_CONFIG, PAGE_COMMON_CONFIG_DISPLAY, CommonConfigController, PAGE_TYPE_TAB),
        (PAGE_UPGRADE, PAGE_UPGRADE_DISPLAY, UpgradeController, PAGE_TYPE_TAB),
        (PAGE_SCRIPT, PAGE_SCRIPT_DISPLAY, ScriptExecController, PAGE_TYPE_TAB),
        (PAGE_PERFORMANCE, PAGE_PERFORMANCE_DISPLAY, PerformanceController, PAGE_TYPE_TAB),
        (PAGE_UDS, PAGE_UDS_DISPLAY, UDSSequenceController, PAGE_TYPE_TAB),
        (PAGE_CLOCK, PAGE_CLOCK_DISPLAY, ClockManagementController, PAGE_TYPE_TAB),
        (PAGE_DEMO, PAGE_DEMO_DISPLAY, DemoPageController, PAGE_TYPE_TAB),
    ]

    # 导航树结构
    NAV_STRUCTURE = {
        NAV_GROUP_DEVICE: {"children": [PAGE_DEVICE_DISPLAY,
                                        PAGE_TOPOLOGY_DISPLAY,
                                        PAGE_PERFORMANCE_DISPLAY,
                                        PAGE_CLOCK_DISPLAY]},
        NAV_GROUP_DIAG: {"children": [PAGE_DTC_DISPLAY,
                                      PAGE_DID_DISPLAY,
                                      PAGE_UDS_DISPLAY]},
        NAV_GROUP_FILE: {"children": [
            PAGE_FILE_TRANSFER_DISPLAY,
            PAGE_LOG_DOWNLOAD_DISPLAY,
            PAGE_BUS_DATA_DOWNLOAD_DISPLAY,
            PAGE_DATA_CONVERTER_DISPLAY,
        ]},
        NAV_GROUP_UPGRADE: {"children": [PAGE_UPGRADE_DISPLAY]},
        NAV_GROUP_CONFIG: {"children": [PAGE_LOG_CONFIG_DISPLAY, PAGE_COMMON_CONFIG_DISPLAY]},
        NAV_GROUP_ADV: {"children": [PAGE_SCRIPT_DISPLAY]},
        NAV_GROUP_DEMO: {"children": [PAGE_DEMO_DISPLAY]},
    }

    @classmethod
    def get_tab_pages(cls):
        """获取Tab页面列表：[(注册名, 显示名, 控制器类)]"""
        return [(k, d, c) for k, d, c, is_dialog in cls.PAGE_DEFINITIONS if not is_dialog]

    @classmethod
    def get_dialog_pages(cls):
        """获取对话框页面列表：[(注册名, 控制器类)]"""
        return [(k, c) for k, d, c, is_dialog in cls.PAGE_DEFINITIONS if is_dialog]

    @classmethod
    def get_page_config(cls):
        """获取页面配置列表：[(注册名, 显示名)]"""
        return [(k, d) for k, d, c, is_dialog in cls.PAGE_DEFINITIONS]

    @classmethod
    def get_page_keys(cls):
        """获取页面注册名列表"""
        return [k for k, _ in cls.get_page_config()]

    @classmethod
    def get_page_display_texts(cls):
        """获取页面显示名列表"""
        return [d for _, d in cls.get_page_config()]

    @classmethod
    def get_page_text_to_key(cls):
        """获取显示名到注册名的映射字典"""
        return dict(cls.get_page_config())


# 自动推导各类页面结构，避免重复（使用类方法）
TAB_PAGES = PageConfig.get_tab_pages()
DIALOG_PAGES = PageConfig.get_dialog_pages()
PAGE_CONFIG = PageConfig.get_page_config()
PAGE_KEYS = PageConfig.get_page_keys()
PAGE_DISPLAY_TEXTS = PageConfig.get_page_display_texts()
PAGE_TEXT_TO_KEY = PageConfig.get_page_text_to_key()

# 导航树结构（直接使用类属性）
NAV_STRUCTURE = PageConfig.NAV_STRUCTURE
