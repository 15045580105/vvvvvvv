from app.core.base_model import BaseModel


class LogConfigModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ecu_levels = {"CCUA":"INFO","CCU0":"WARN","CCU1":"ERROR"}
        self.apps = [("ACSG","CCUA","INFO"),("ADAP","CCUA","DEBUG"),("TSYN","CCU0","WARN"),("SOAM","CCU1","ERROR")]

