import datetime

from PyQt5.QtWidgets import QProgressDialog
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from app.core.base_controller import BaseController
from app.modules.someip_signboard.view.someip_signboard_view import SomeIpSignboardView
from app.modules.someip_signboard.model.someip_signboard_model import SomeIpSignboardModel
from app.common.utils.pcap_utils import PcapUtils
from app.common.utils.someip_utils import get_service_interface_name


class PcapWorker(QThread):
    progress_signal = pyqtSignal(int)
    result_signal = pyqtSignal(list)

    def __init__(self, path):
        super().__init__()
        self.path = path

    def run(self):
        try:
            findings = PcapUtils.parse_someip_sd_pcap(self.path, self.progress_signal.emit)
            self.result_signal.emit(findings)
        except Exception as e:
            print(f"Worker Error: {e}")
            self.result_signal.emit([])


class SomeIpSignboardController(BaseController):
    def __init__(self, parent=None):
        self.model = SomeIpSignboardModel()
        self.view = SomeIpSignboardView()
        super().__init__(self.model, self.view, parent)

        # State
        self.all_data = []
        self.pinned_ids = set()
        self.hidden_ids = set()

        self.current_page = 1
        self.page_size = 12
        self.search_query = ""
        self.show_hidden = False

        # Connect View Signals
        self.view.pcap_selected.connect(self.on_pcap_selected)
        self.view.refresh_requested.connect(self.on_refresh)
        self.view.search_changed.connect(self.on_search_changed)
        self.view.show_hidden_toggled.connect(self.on_show_hidden_toggled)
        self.view.card_action_triggered.connect(self.on_card_action)
        self.view.page_changed.connect(self.on_page_changed)
        self.view.page_size_calculated.connect(self.on_page_size_calculated)

        # Service Name Map
        self.known_service_names = {
            "0x10FA": "AP_ServiceManagementInterface",
            "0x106E": "VersionInformation",
            "0x10C7": "PS_OTAModeStatus",
            "0x1055": "VehicleStateService",
            "0xFF47": "UnknownService_AB",
            "0x2001": "AudioController",
            "0x2002": "DisplayManager",
            "0x3005": "NavigationData",
            "0x4010": "ClimateControl",
            "0x5001": "BatteryStatus",
        }

        # Initial Load
        # self._load_dummy_data()
        self._update_view()

    def on_pcap_selected(self, path):
        if not path:
            return

        # Setup Progress Dialog
        self.progress_dlg = QProgressDialog("正在解析 PCAP 文件...", "取消", 0, 100, self.view)
        self.progress_dlg.setWindowModality(Qt.WindowModal)
        self.progress_dlg.setMinimumDuration(0) # Show immediately
        self.progress_dlg.setValue(0)

        # Use Custom Worker to parse PCAP in background
        self.worker = PcapWorker(path)

        # Connect signals
        self.worker.progress_signal.connect(self.progress_dlg.setValue)
        self.worker.result_signal.connect(self.on_pcap_parsed)
        self.worker.finished.connect(self.progress_dlg.close)

        # Handle Cancel
        self.progress_dlg.canceled.connect(self.worker.terminate)

        self.worker.start()

    def _create_service_item(self, service_id, instance_id):
        service_name = get_service_interface_name(
            service_id,
            instance_id,
            default=self.known_service_names.get(service_id, "Unknown Service")
        )
        return {
            "uid": f"{service_id}_{instance_id}",
            "service_id": service_id,
            "service_name": service_name,
            "instance_id": instance_id,
            "version": "-",
            "major_version": "-",
            "minor_version": "-",
            "server_endpoint": "-",
            "last_time": "-",
            "last_time_source": "-",
            "subscribe_info": [],
            "find_info": [],
            "show_details": False,
            "_subscribe_map": {},
            "_find_map": {},
            "_cached_endpoint": "-",
        }

    @staticmethod
    def _fmt_time(timestamp):
        if not timestamp:
            return "-"
        return datetime.datetime.fromtimestamp(timestamp).strftime("%Y/%m/%d %H:%M:%S")

    @staticmethod
    def _clean_endpoint(entry, fallback_endpoint=''):
        endpoint = entry.get('endpoint') or ''
        if endpoint:
            proto = entry.get('l4_proto') or ''
            return f"{endpoint} ({proto})" if proto else endpoint
        return fallback_endpoint or '-'

    @staticmethod
    def _infer_service_endpoint(entry):
        endpoint = entry.get('endpoint') or ''
        proto = entry.get('l4_proto') or ''
        if endpoint:
            return f"{endpoint} ({proto})" if proto else endpoint

        packet_dst = entry.get('packet_dst_endpoint') or ''
        packet_src = entry.get('packet_src_endpoint') or ''
        packet_dst_ip = entry.get('packet_dst_ip') or ''
        packet_src_ip = entry.get('packet_src_ip') or ''

        if packet_dst and packet_dst_ip and not packet_dst.startswith('239.'):
            return packet_dst
        if packet_src and packet_src_ip and not packet_src.startswith('239.'):
            return packet_src
        return '-'

    @staticmethod
    def _set_latest_time(item, time_str, source='-'):
        if not time_str or time_str == '-':
            return
        current = item.get('last_time', '-')
        if current in ('', '-', None) or time_str > current:
            item['last_time'] = time_str
            item['last_time_source'] = source or '-'

    def on_pcap_parsed(self, findings):
        # Parse PCAP
        try:
            services_map = {}

            def get_service_item(service_id, instance_id):
                key = (service_id, instance_id)
                if key not in services_map:
                    services_map[key] = self._create_service_item(service_id, instance_id)
                return services_map[key]

            for entry in findings:
                service_id = entry['service_id']
                instance_id = entry['instance_id']
                entry_type = entry['entry_type']
                eventgroup_id = entry.get('eventgroup_id') or '-'
                packet_src_ip = entry.get('packet_src_ip', '')
                packet_src_endpoint = entry.get('packet_src_endpoint', '')
                time_str = self._fmt_time(entry.get('timestamp'))
                version_str = entry.get('version', '-')

                if entry_type in (0x01, 0x02):
                    item = get_service_item(service_id, instance_id)
                    source = 'OfferService' if entry_type == 0x01 else 'StopOfferService'
                    self._set_latest_time(item, time_str, source)
                    endpoint = self._infer_service_endpoint(entry)
                    if endpoint != '-':
                        item['server_endpoint'] = endpoint
                        item['_cached_endpoint'] = endpoint
                    elif item['_cached_endpoint'] != '-':
                        item['server_endpoint'] = item['_cached_endpoint']

                    if entry_type == 0x01:
                        item['major_version'] = str(entry.get('major_version', '-'))
                        item['minor_version'] = str(entry.get('minor_version', '-'))
                        item['version'] = version_str
                elif entry_type == 0x00:
                    target_items = []
                    if instance_id == '0xFFFF':
                        same_service_items = [v for (sid, _), v in services_map.items() if sid == service_id]
                        target_items = same_service_items or [get_service_item(service_id, '0xFFFF')]
                    else:
                        target_items = [get_service_item(service_id, instance_id)]

                    finder_ip = packet_src_ip or (entry.get('endpoint_ip') or '-')
                    for item in target_items:
                        self._set_latest_time(item, time_str, 'FindService')
                        find_key = (
                            finder_ip,
                            version_str,
                            instance_id,
                            time_str,
                        )
                        item['_find_map'][find_key] = {
                            'finder_ip': finder_ip or '-',
                            'find_version': f"[{instance_id}, {version_str}]",
                            'last_find_time': time_str,
                        }

                elif entry_type in (0x03, 0x04, 0x05, 0x06, 0x07):
                    item = get_service_item(service_id, instance_id)
                    time_source = {
                        0x03: 'SubscribeEventgroup',
                        0x04: 'StopSubscribeEventgroup',
                        0x05: 'SubscribeEventgroupAck',
                        0x06: 'SubscribeEventgroupNack',
                        0x07: 'SubscribeEventgroupAck/Nack',
                    }.get(entry_type, 'SubscribeEventgroup')
                    self._set_latest_time(item, time_str, time_source)
                    subscriber_ip_port = self._clean_endpoint(entry, packet_src_endpoint or packet_src_ip or '-')
                    sub_key = (
                        subscriber_ip_port,
                        eventgroup_id,
                    )
                    sub_entry = item['_subscribe_map'].get(sub_key, {
                        'subscriber_ip_port': subscriber_ip_port,
                        'event_group_id': eventgroup_id,
                        'last_subscribe_time': '-',
                        'last_suback_time': '-',
                        'last_nack_time': '-',
                    })
                    if entry_type == 0x03:
                        sub_entry['last_subscribe_time'] = time_str
                    elif entry_type == 0x05:
                        sub_entry['last_suback_time'] = time_str
                    elif entry_type == 0x06:
                        sub_entry['last_nack_time'] = time_str
                    elif entry_type == 0x07:
                        if entry.get('ttl', 0) and int(entry.get('ttl', 0)) > 0:
                            sub_entry['last_suback_time'] = time_str
                        else:
                            sub_entry['last_nack_time'] = time_str
                    item['_subscribe_map'][sub_key] = sub_entry

            final_items = []
            for item in services_map.values():
                item['subscribe_info'] = list(item['_subscribe_map'].values())
                item['find_info'] = list(item['_find_map'].values())
                del item['_subscribe_map']
                del item['_find_map']
                del item['_cached_endpoint']
                final_items.append(item)

            final_items.sort(key=lambda x: (x['service_id'], x['instance_id']))
            for idx, item in enumerate(final_items, start=1):
                item['index'] = idx

            self.all_data = final_items
            self.current_page = 1
            self._update_view()

        except Exception as e:
            print(f"Error processing PCAP data in Controller: {e}")

    def on_refresh(self):
        # self._load_dummy_data()
        self._update_view()

    def on_search_changed(self, text):
        self.search_query = text.lower().strip()
        self.current_page = 1  # Reset to page 1
        self._update_view()

    def on_show_hidden_toggled(self, checked):
        self.show_hidden = checked
        self.current_page = 1
        self._update_view()

    def on_card_action(self, action, data):
        uid = data.get('uid')
        if not uid: return

        if action == 'pin':
            if uid in self.pinned_ids:
                self.pinned_ids.remove(uid)
            else:
                self.pinned_ids.add(uid)
        elif action == 'hide':
            self.hidden_ids.add(uid)
        elif action == 'restore':
            if uid in self.hidden_ids:
                self.hidden_ids.remove(uid)
        elif action == 'details':
            for item in self.all_data:
                if item.get('uid') == uid:
                    item['show_details'] = not item.get('show_details', False)
                    break

        self._update_view()

    def on_page_changed(self, new_page):
        # View requests a page change, we just confirm via update
        self.current_page = new_page
        self._update_view()

    def on_page_size_calculated(self, new_size):
        self.page_size = new_size
        self._update_view()

    def _load_dummy_data(self):
        self.all_data = []
        self._update_view()

    def _update_view(self):
        # Filter
        filtered = []
        for item in self.all_data:
            uid = item['uid']

            # Hide logic
            if uid in self.hidden_ids and not self.show_hidden:
                continue

            # Search logic
            if self.search_query:
                # Naive search check
                found = False
                if self.search_query in item['service_name'].lower(): found = True
                if self.search_query in item['service_id'].lower(): found = True
                if self.search_query == str(item['index']): found = True

                if not found:
                    continue

            filtered.append(item)

        # Sort (Pinned first)
        filtered.sort(key=lambda x: 0 if x['uid'] in self.pinned_ids else 1)

        # Paginate
        total_items = len(filtered)
        if self.page_size < 1: self.page_size = 1
        total_pages = max(1, (total_items + self.page_size - 1) // self.page_size)

        self.current_page = max(1, min(self.current_page, total_pages))

        start_idx = (self.current_page - 1) * self.page_size
        end_idx = start_idx + self.page_size
        page_items = filtered[start_idx:end_idx]

        # Push to View
        self.view.update_view_data(page_items, total_pages, self.current_page, self.pinned_ids, self.hidden_ids)
