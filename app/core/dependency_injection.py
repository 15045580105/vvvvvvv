# 依赖注入容器
# app/core/dependency_injection.py
from typing import Dict, Type, Any, Callable, Optional


class DIContainer:
    """依赖注入容器"""

    def __init__(self):
        self._singletons: Dict[Type, Any] = {}
        self._factories: Dict[Type, Callable] = {}
        self._instances: Dict[Type, Any] = {}

    def register_singleton(self, interface: Type, implementation: Any):
        """注册单例"""
        self._singletons[interface] = implementation

    def register_factory(self, interface: Type, factory: Callable):
        """注册工厂"""
        self._factories[interface] = factory

    def resolve(self, interface: Type) -> Optional[Any]:
        """解析依赖"""
        # 检查单例缓存
        if interface in self._instances:
            return self._instances[interface]

        # 检查单例注册
        if interface in self._singletons:
            impl = self._singletons[interface]
            if callable(impl):
                instance = impl()
            else:
                instance = impl
            self._instances[interface] = instance
            return instance

        # 检查工厂注册
        if interface in self._factories:
            factory = self._factories[interface]
            instance = factory()
            self._instances[interface] = instance
            return instance

        return None


# 全局依赖注入容器
di_container = DIContainer()


def configure_dependencies():
    """配置应用程序依赖"""
    # 注册模块管理器
    di_container.register_singleton(ModuleManager, lambda: ModuleManager(di_container))

    # 注册服务（示例）