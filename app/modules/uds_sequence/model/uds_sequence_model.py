from app.core.base_model import BaseModel


class UDSSequenceModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.commands = [
            "10 DiagnosticSessionControl",
            "11 EcuReset",
            "14 ClearDiagnosticInformation",
            "19 ReadDTCInformation",
            "22 ReadDataByIdentifier",
            "23 ReadMemoryByAddress",
            "27 SecurityAccess",
            "28 CommunicationControl",
            "2A ReadDataByPeriodicIdentifier",
            "2C DynamicallyDefineDataIdentifier",
            "2E WriteDataByIdentifier",
            "2F InputOutputControlByIdentifier",
            "31 RoutineControl",
            "34 RequestDownload",
            "35 RequestUpload",
            "36 TransferData",
            "37 RequestTransferExit",
            "38 RequestFileTransfer",
            "3D WriteMemoryByAddress",
            "3E TesterPresent",
            "85 ControlDTCSetting"
        ]
        self.log = ""

