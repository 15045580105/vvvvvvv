from app.core.base_model import BaseModel

class CommonConfigModel(BaseModel):
    def __init__(self):
        super().__init__()
        self._data = {}

