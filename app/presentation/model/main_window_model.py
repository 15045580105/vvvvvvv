from app.core.base_model import BaseModel


class MainModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.registry = {}

    def register(self, key: str, controller):
        self.registry[key] = controller

    def get(self, key: str):
        return self.registry.get(key)

