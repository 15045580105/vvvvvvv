from app.core.base_model import BaseModel
from app.services.device_manage.topology_service import TopologyService, TopologySnapshot


class TopologyModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.networks = []
        self.nodes = []
        self.vehicle_info = {}
        self.service_status = {}
        self.security_info = {}
        self.network_mgmt = {}
        self.storage_info = {}
        self._service = TopologyService()
        self._snapshot: TopologySnapshot | None = None
        # self.refresh()

    def refresh(self):
        snapshot: TopologySnapshot = self._service.fetch_snapshot()
        self._snapshot = snapshot
        self.nodes = snapshot.nodes
        self.networks = snapshot.networks
        self.vehicle_info = snapshot.vehicle_info
        self.service_status = snapshot.service_status
        self.security_info = snapshot.security_info
        self.network_mgmt = snapshot.network_management
        self.storage_info = snapshot.storage_info
        self.dataChanged.emit()

    def info_blocks_payload(self) -> dict:
        return {
            "vehicle_info": self.vehicle_info,
            "service_status": self.service_status,
            "security_info": self.security_info,
            "network_mgmt": self.network_mgmt,
            "storage_info": self.storage_info,
        }
