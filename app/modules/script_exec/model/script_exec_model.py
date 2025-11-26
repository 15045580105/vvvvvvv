from app.core.base_model import BaseModel


class ScriptExecModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scripts = ["check_voltage.py","dump_dtc.sh","performance_test.py","backup_config.sh"]
        self.output = ""

