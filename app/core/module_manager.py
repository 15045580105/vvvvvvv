# app/core/module_manager.py
import importlib
import inspect
from typing import Dict, List, Type, Optional
from PyQt5.QtCore import QObject, pyqtSignal

from .base_module import BaseModule
from .base_controller import BaseController
from .dependency_injection import DIContainer


class ModuleManager(QObject):
    """
    模块管理器 - 负责动态加载和管理所有功能模块
    """

    # 信号定义
    module_loaded = pyqtSignal(str, BaseModule)  # 模块名称, 模块实例
    module_unloaded = pyqtSignal(str)  # 模块名称
    all_modules_loaded = pyqtSignal()  # 所有模块加载完成

    def __init__(self, di_container: DIContainer):
        super().__init__()
        self.di_container = di_container
        self._modules: Dict[str, BaseModule] = {}
        self._module_configs = self._load_module_configs()

    def _load_module_configs(self) -> Dict:
        """加载模块配置"""
        # 这里可以从配置文件或数据库中加载模块配置
        # 简化实现：返回硬编码的配置
        return {
            'device_management': {
                'enabled': True,
                'display_name': '设备状态管理',
                'description': '设备连接、状态监控和拓扑管理'
            },
            'dtc_diagnostic': {
                'enabled': True,
                'display_name': 'DTC故障诊断',
                'description': '故障码读取、清除和分析'
            },
            'did_management': {
                'enabled': True,
                'display_name': 'DID数据管理',
                'description': '数据标识符读取和写入'
            },
            'file_transfer': {
                'enabled': True,
                'display_name': '文件传输管理',
                'description': '文件上传、下载和管理'
            },
            'device_upgrade': {
                'enabled': True,
                'display_name': '设备升级管理',
                'description': '软件和固件升级'
            },
            'configuration': {
                'enabled': True,
                'display_name': '配置管理中心',
                'description': '系统配置和用户管理'
            }
        }

    def load_all_modules(self) -> Dict[str, BaseModule]:
        """加载所有启用的模块"""
        loaded_modules = {}

        for module_name, config in self._module_configs.items():
            if config.get('enabled', False):
                module = self.load_module(module_name)
                if module:
                    loaded_modules[module_name] = module
                    self.module_loaded.emit(module_name, module)

        self.all_modules_loaded.emit()
        return loaded_modules

    def load_module(self, module_name: str) -> Optional[BaseModule]:
        """动态加载单个模块"""
        try:
            # 动态导入模块
            module_path = f"app.modules.{module_name}.{module_name}_module"
            module_lib = importlib.import_module(module_path)

            # 查找模块类（约定：模块类名为{ModuleName}Module）
            module_class_name = f"{module_name.title().replace('_', '')}Module"
            module_class = None

            for name, obj in inspect.getmembers(module_lib):
                if (inspect.isclass(obj) and
                        issubclass(obj, BaseModule) and
                        name == module_class_name):
                    module_class = obj
                    break

            if not module_class:
                raise ValueError(f"在模块 {module_name} 中未找到 {module_class_name} 类")

            # 创建模块实例
            module_instance = module_class(module_name, self.di_container)

            # 初始化模块
            if module_instance.initialize():
                self._modules[module_name] = module_instance
                return module_instance
            else:
                raise ValueError(f"模块 {module_name} 初始化失败")

        except Exception as e:
            print(f"加载模块 {module_name} 失败: {str(e)}")
            return None

    def get_module(self, module_name: str) -> Optional[BaseModule]:
        """获取已加载的模块"""
        return self._modules.get(module_name)

    def get_all_modules(self) -> Dict[str, BaseModule]:
        """获取所有已加载的模块"""
        return self._modules.copy()

    def get_module_controller(self, module_name: str):
        """获取模块的控制器"""
        module = self.get_module(module_name)
        if module:
            return module.get_controller()
        return None

    def get_module_view(self, module_name: str) -> Optional[QWidget]:
        """获取模块的视图"""
        module = self.get_module(module_name)
        if module:
            return module.get_view()
        return None

    def unload_module(self, module_name: str) -> bool:
        """卸载模块"""
        module = self._modules.get(module_name)
        if module:
            module.cleanup()
            del self._modules[module_name]
            self.module_unloaded.emit(module_name)
            return True
        return False

    def cleanup_all(self):
        """清理所有模块"""
        for module_name in list(self._modules.keys()):
            self.unload_module(module_name)