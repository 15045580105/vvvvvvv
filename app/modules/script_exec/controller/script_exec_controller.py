from app.core.base_controller import BaseController
from app.modules.script_exec.model.script_exec_model import ScriptExecModel
from app.modules.script_exec.view.script_exec_view import ScriptExecView


class ScriptExecController(BaseController):
    def __init__(self, parent=None):
        self.model = ScriptExecModel(parent)
        self.view = ScriptExecView(parent)
        super().__init__(self.model, self.view, parent)
        self.on_model_changed()

    def on_model_changed(self):
        self.view.populate(self.model.scripts)

    def get_view(self):
        return self.view

