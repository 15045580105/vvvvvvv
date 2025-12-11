from app.core.base_model import BaseModel


class UDSSequenceModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        # nested tree data (no new classes) — each node: {code, name, children}
        self.tree_data = [
            {"code": "10", "name": "DiagnosticSessionControl", "children": [
                {"code": "01", "name": "DefaultSession", "children": []},
                {"code": "02", "name": "ProgrammingSession", "children": []},
                {"code": "03", "name": "ExtendedDiagnosticSession", "children": []},
            ]},
            {"code": "11", "name": "EcuReset", "children": [
                {"code": "01", "name": "HardReset", "children": []},
                {"code": "02", "name": "KeyOffOnReset", "children": []},
                {"code": "03", "name": "SoftReset", "children": []},
            ]},
            {"code": "14", "name": "ClearDiagnosticInformation", "children": []},
            {"code": "19", "name": "ReadDTCInformation", "children": [
                {"code": "01", "name": "ReportNumberOfDTCByStatusMask", "children": []},
                {"code": "02", "name": "ReportDTCByStatusMask", "children": []},
                {"code": "04", "name": "ReportDTCSnapshotRecordByDTCNumber", "children": []},
                {"code": "06", "name": "ReportDTCExtDataRecordByDTCNumber", "children": []},
                {"code": "0A", "name": "ReportSupportedDTC", "children": []},
                {"code": "12", "name": "ReportNumberOfEmissionsRelatedOBDDTCByStatusMask", "children": []},
                {"code": "13", "name": "ReportEmissionsRelatedOBDDTCByStatusMask", "children": []},
            ]},
            {"code": "22", "name": "ReadDataByIdentifier", "children": []},
            {"code": "23", "name": "ReadMemoryByAddress", "children": []},
            {"code": "27", "name": "SecurityAccess", "children": [
                {"code": "01", "name": "RequestSeedLevel1", "children": []},
                {"code": "02", "name": "SendKeyLevel1", "children": []},
                {"code": "03", "name": "RequestSeedLevel2", "children": []},
                {"code": "04", "name": "SendKeyLevel2", "children": []},
                {"code": "21", "name": "RequestReprogrammingSeed", "children": []},
                {"code": "22", "name": "SendReprogrammingKey", "children": []},
            ]},
            {"code": "28", "name": "CommunicationControl", "children": [
                {"code": "00", "name": "EnableRxAndTx", "children": []},
                {"code": "01", "name": "EnableRxAndDisableTx", "children": []},
                {"code": "02", "name": "DisableRxAndEnableTx", "children": []},
                {"code": "03", "name": "DisableRxAndTx", "children": []},
            ]},
            {"code": "2A", "name": "ReadDataByPeriodicIdentifier", "children": []},
            {"code": "2C", "name": "DynamicallyDefineDataIdentifier", "children": [
                {"code": "01", "name": "DefineByIdentifier", "children": []},
                {"code": "03", "name": "ClearDynamicallyDefinedDataIdentifier", "children": []},
            ]},
            {"code": "2E", "name": "WriteDataByIdentifier", "children": []},
            {"code": "2F", "name": "InputOutputControlByIdentifier", "children": []},
            {"code": "31", "name": "RoutineControl", "children": [
                {"code": "01", "name": "StartRoutine", "children": []},
                {"code": "02", "name": "StopRoutine", "children": []},
                {"code": "03", "name": "RequestRoutineResults", "children": []},
            ]},
            {"code": "34", "name": "RequestDownload", "children": []},
            {"code": "35", "name": "RequestUpload", "children": []},
            {"code": "36", "name": "TransferData", "children": []},
            {"code": "37", "name": "RequestTransferExit", "children": []},
            {"code": "38", "name": "RequestFileTransfer", "children": []},
            {"code": "3D", "name": "WriteMemoryByAddress", "children": []},
            {"code": "3E", "name": "TesterPresent", "children": []},
            {"code": "85", "name": "ControlDTCSetting", "children": [
                {"code": "01", "name": "DTCSettingType ON", "children": []},
                {"code": "02", "name": "DTCSettingType OFF", "children": []},
            ]},
        ]

        # flat commands list for compatibility with other code that expects a list
        self.commands = [f"{n['code']} {n['name']}" for n in self.tree_data]
        self.log = ""

    def get_tree_data(self):
        return self.tree_data

    def get_flat_commands(self):
        return self.commands

    def find_node_by_code(self, code: str):
        """Find a node in tree_data by code or compound code (e.g., '10.01').
        Returns a tuple (node_dict, parent_path_codes_list) or (None, None).
        """
        if not code:
            return None, None
        parts = code.split('.')

        def recurse(nodes, parts, path_codes):
            if not parts:
                return None, None
            p = parts[0]
            for n in nodes:
                if n.get('code') == p:
                    if len(parts) == 1:
                        return n, path_codes + [n.get('code')]
                    return recurse(n.get('children', []), parts[1:], path_codes + [n.get('code')])
            return None, None

        return recurse(self.tree_data, parts, [])
