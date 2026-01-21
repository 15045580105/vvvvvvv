import json
import os
from app.core.base_model import BaseModel
from app.common.utils.path_utils import get_app_data_path

_uds_dir = os.path.join(get_app_data_path(), "UDS_SEQUENCE")
if not os.path.exists(_uds_dir):
    try:
        os.makedirs(_uds_dir, exist_ok=True)
    except OSError:
        pass
UDS_SEQ_FILE = os.path.join(_uds_dir, "uds_sequences.json")


class UDSSequenceModel(BaseModel):
    CONFIG_FILE = UDS_SEQ_FILE

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
        self.configs = self._load_configs_from_file()

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

    def _load_configs_from_file(self):
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_config(self, config_name: str, data: list):
        """
        Save the given configuration data to a file.
        Args:
            config_name: The name of the configuration.
            data: The configuration data to save (list of commands).
        """
        try:
            with open(self.CONFIG_FILE, 'r', encoding='utf-8') as file:
                configs = json.load(file)
        except FileNotFoundError:
            configs = {}

        configs[config_name] = data

        with open(self.CONFIG_FILE, 'w', encoding='utf-8') as file:
            json.dump(configs, file, indent=4, ensure_ascii=False)

        # Update in-memory configs
        self.configs = configs

    def delete_config(self, config_name: str):
        """Delete a configuration."""
        try:
            with open(self.CONFIG_FILE, 'r', encoding='utf-8') as file:
                configs = json.load(file)
        except FileNotFoundError:
            return

        if config_name in configs:
            del configs[config_name]
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as file:
                json.dump(configs, file, indent=4, ensure_ascii=False)
            self.configs = configs

    def get_config_names(self):
        """Return a list of configuration names."""
        return list(self.configs.keys())

    def load_config(self, config_name: str) -> list:
        """
        Load the configuration data for the given name.
        Args:
            config_name: The name of the configuration to load.
        Returns:
            The configuration data (list of commands).
        """
        try:
            with open(self.CONFIG_FILE, 'r', encoding='utf-8') as file:
                configs = json.load(file)
            data = configs.get(config_name, [])
            if isinstance(data, list):
                return data
            return []
        except (FileNotFoundError, json.JSONDecodeError, Exception):
            return []

    def get_config_data(self) -> dict:
        """
        Retrieve all configuration data.
        Returns:
            A dictionary of all configurations.
        """
        try:
            with open(self.CONFIG_FILE, 'r', encoding='utf-8') as file:
                return json.load(file)
        except FileNotFoundError:
            return {}

