from typing import List, Dict, Any, Optional
from app.core.base_service import BaseService
from app.services.device_manage.device_service import DeviceService
from app.services.device_manage.topology_service import TopologyService
from app.core.dependency_injection import di_container


class LoggingService(BaseService):
    def __init__(self):
        super().__init__()
        self._device_service: Optional[DeviceService] = None
        self._topology_service: Optional[TopologyService] = None

    def inject_device_service(self, device_service: DeviceService):
        self._device_service = device_service
        # 注入 TopologyService，如果未注入则尝试从 DI 容器获取或创建
        self._topology_service = di_container.resolve(TopologyService)
        if not self._topology_service:
            self._topology_service = TopologyService(device_service)
            di_container.register_singleton(TopologyService, self._topology_service)
