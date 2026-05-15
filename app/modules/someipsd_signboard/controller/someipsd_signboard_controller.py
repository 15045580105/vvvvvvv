import datetime
from decimal import Decimal, ROUND_HALF_UP

from PyQt5.QtWidgets import QProgressDialog
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from app.core.base_controller import BaseController
from app.modules.someipsd_signboard.view.someipsd_signboard_view import SomeIpSignboardView
from app.modules.someipsd_signboard.model.someipsd_signboard_model import SomeIpSignboardModel
from app.common.utils.pcap_utils import PcapUtils
from app.common.utils.someip_utils import get_service_info


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
        self.current_findings = []
        self.baseline_datetime = self._parse_baseline_time(self.view.get_baseline_time_text())

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
        self.view.baseline_time_changed.connect(self.on_baseline_time_changed)

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
        matrix_info = get_service_info(service_id, instance_id)
        matrix_matched = bool(matrix_info)
        service_name = (
            (matrix_info or {}).get("service_interface_name")
            or self.known_service_names.get(service_id, "Unknown Service")
        )
        return {
            "uid": f"{service_id}_{instance_id}",
            "service_id": service_id,
            "service_name": service_name,
            "instance_id": instance_id,
            "matrix_matched": matrix_matched,
            "in_matrix": matrix_matched,
            "version": "-",
            "major_version": "-",
            "minor_version": "-",
            "server_endpoint": "-",
            "last_time": "-",
            "last_time_source": "-",
            "status": "active" if matrix_matched else "inactive",
            "status_reason": "矩阵中存在该服务实例" if matrix_matched else "矩阵中未找到该服务实例",
            "subscribe_info": [],
            "find_info": [],
            "show_details": False,
            "_subscribe_map": {},
            "_find_map": {},
            "_cached_endpoint": "-",
            "_last_timestamp_value": None,
        }

    @staticmethod
    def _parse_baseline_time(value):
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                return datetime.datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    def _format_display_time(self, timestamp, zero_timestamp=None):
        if timestamp in (None, ""):
            return "-"

        try:
            ts = float(timestamp)
        except (TypeError, ValueError):
            return "-"

        if self.baseline_datetime is not None and zero_timestamp is not None:
            try:
                zero_decimal = Decimal(str(zero_timestamp))
                ts_decimal = Decimal(str(timestamp))
                offset_decimal = max(Decimal('0'), ts_decimal - zero_decimal)
                total_nanos = int((offset_decimal * Decimal('1000000000')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                seconds_part, fraction_part = divmod(total_nanos, 1_000_000_000)
                display_dt = self.baseline_datetime + datetime.timedelta(seconds=int(seconds_part))
                return self._format_datetime_with_fraction(display_dt, fraction_part, 1_000_000_000)
            except (TypeError, ValueError, OverflowError):
                pass

        try:
            ts_decimal = Decimal(str(timestamp))
            seconds_part = int(ts_decimal // Decimal('1'))
            fraction_part = int(((ts_decimal - Decimal(seconds_part)) * Decimal('1000000000')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            if fraction_part >= 1_000_000_000:
                seconds_part += 1
                fraction_part -= 1_000_000_000
            return self._format_datetime_with_fraction(datetime.datetime.fromtimestamp(seconds_part), fraction_part, 1_000_000_000)
        except (OverflowError, OSError, ValueError):
            return "-"

    @staticmethod
    def _format_datetime_with_fraction(value, raw_fraction, resolution):
        if resolution in (None, 0):
            resolution = 1_000_000_000

        try:
            resolution_value = int(resolution)
            fraction_value = int(raw_fraction)
        except (TypeError, ValueError):
            resolution_value = 1_000_000_000
            fraction_value = 0

        fraction_decimal = (Decimal(fraction_value) / Decimal(resolution_value)).quantize(
            Decimal('0.000001'),
            rounding=ROUND_HALF_UP,
        )
        if fraction_decimal >= Decimal('1.000000'):
            value = value + datetime.timedelta(seconds=1)
            fraction_decimal -= Decimal('1.000000')
        fraction_text = f"{int((fraction_decimal * Decimal('1000000')).to_integral_value(rounding=ROUND_HALF_UP)):06d}"

        return f"{value.strftime('%Y/%m/%d %H:%M:%S')}.{fraction_text}"

    def _format_display_time_precise(self, timestamp, zero_timestamp=None, timestamp_raw=None, zero_timestamp_raw=None, timestamp_resolution=None, zero_timestamp_resolution=None):
        if timestamp in (None, ""):
            return "-"

        if self.baseline_datetime is not None and timestamp_raw not in (None, "") and zero_timestamp_raw not in (None, ""):
            try:
                current_raw = int(timestamp_raw)
                base_raw = int(zero_timestamp_raw)
                resolution = int(timestamp_resolution or zero_timestamp_resolution or 1_000_000_000)
                offset_raw = max(0, current_raw - base_raw)
                seconds_part, fraction_part = divmod(offset_raw, resolution)
                display_dt = self.baseline_datetime + datetime.timedelta(seconds=int(seconds_part))
                return self._format_datetime_with_fraction(display_dt, fraction_part, resolution)
            except (TypeError, ValueError, OverflowError):
                pass

        return self._format_display_time(timestamp, zero_timestamp)

    @staticmethod
    def _resolve_capture_start_timestamp(findings):
        for key in ('capture_start_timestamp', 'file_start_timestamp'):
            values = []
            for entry in findings or []:
                ts = entry.get(key)
                if ts in (None, ''):
                    continue
                try:
                    values.append(float(ts))
                except (TypeError, ValueError):
                    continue
            if values:
                return min(values)

        timestamps = []
        for entry in findings or []:
            ts = entry.get('timestamp')
            if ts in (None, ''):
                continue
            try:
                timestamps.append(float(ts))
            except (TypeError, ValueError):
                continue
        if timestamps:
            return min(timestamps)
        return None

    @staticmethod
    def _resolve_capture_start_reference(findings):
        raw_candidates = []
        for entry in findings or []:
            raw_value = entry.get('capture_start_timestamp_raw')
            resolution = entry.get('capture_start_timestamp_resolution')
            if raw_value in (None, ''):
                raw_value = entry.get('timestamp_raw')
                resolution = entry.get('timestamp_resolution')
            if raw_value in (None, ''):
                continue
            try:
                raw_candidates.append((int(raw_value), int(resolution or 1_000_000_000)))
            except (TypeError, ValueError):
                continue
        if raw_candidates:
            return min(raw_candidates, key=lambda x: x[0])
        return None, None

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
    def _set_latest_time(item, time_str, source='-', timestamp=None):
        if not time_str or time_str == '-':
            return

        # last_time 是服务卡片聚合后的“最新活动时间”，不是逐报文逐条展示。
        # 因此多个报文/多个 SD entry 在同一微秒内时，界面上可能出现相同显示值。

        ts_value = None
        if timestamp not in (None, ''):
            try:
                ts_value = float(timestamp)
            except (TypeError, ValueError):
                ts_value = None

        current_ts_value = item.get('_last_timestamp_value')
        should_update = current_ts_value is None
        if not should_update and ts_value is not None:
            should_update = ts_value >= current_ts_value
        elif not should_update:
            current = item.get('last_time', '-')
            should_update = current in ('', '-', None) or time_str >= current

        if should_update:
            item['last_time'] = time_str
            item['last_time_source'] = source or '-'
            item['_last_timestamp_value'] = ts_value

    @staticmethod
    def _derive_service_status(item):
        matrix_flag = item.get('matrix_matched')
        if isinstance(matrix_flag, str):
            matrix_flag = matrix_flag.strip().lower() in ('1', 'true', 'yes', 'y', 'active')
        else:
            matrix_flag = bool(matrix_flag)

        if matrix_flag:
            return 'active', '矩阵中存在该服务实例'
        return 'inactive', '矩阵中未找到该服务实例'

    def on_pcap_parsed(self, findings):
        # Parse PCAP
        try:
            self.current_findings = list(findings or [])
            zero_timestamp = self._resolve_capture_start_timestamp(self.current_findings)
            zero_timestamp_raw, zero_timestamp_resolution = self._resolve_capture_start_reference(self.current_findings)

            services_map = {}

            def get_service_item(service_id, instance_id):
                key = (service_id, instance_id)
                if key not in services_map:
                    services_map[key] = self._create_service_item(service_id, instance_id)
                return services_map[key]

            for entry in self.current_findings:
                service_id = entry['service_id']
                instance_id = entry['instance_id']
                entry_type = entry['entry_type']
                eventgroup_id = entry.get('eventgroup_id') or '-'
                packet_src_ip = entry.get('packet_src_ip', '')
                packet_src_endpoint = entry.get('packet_src_endpoint', '')
                time_str = self._format_display_time_precise(
                    entry.get('timestamp'),
                    zero_timestamp,
                    entry.get('timestamp_raw'),
                    zero_timestamp_raw,
                    entry.get('timestamp_resolution'),
                    zero_timestamp_resolution,
                )
                version_str = entry.get('version', '-')

                if entry_type in (0x01, 0x02):
                    item = get_service_item(service_id, instance_id)
                    source = 'OfferService' if entry_type == 0x01 else 'StopOfferService'
                    self._set_latest_time(item, time_str, source, entry.get('timestamp'))
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
                        self._set_latest_time(item, time_str, 'FindService', entry.get('timestamp'))
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
                    self._set_latest_time(item, time_str, time_source, entry.get('timestamp'))
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
                item['status'], item['status_reason'] = self._derive_service_status(item)
                del item['_subscribe_map']
                del item['_find_map']
                del item['_cached_endpoint']
                del item['_last_timestamp_value']
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
        self.search_query = text.strip()
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

    def on_baseline_time_changed(self, text):
        self.baseline_datetime = self._parse_baseline_time(text)
        if self.current_findings:
            self.on_pcap_parsed(self.current_findings)
        else:
            self._update_view()

    def _load_dummy_data(self):
        self.all_data = []
        self._update_view()

    def _update_view(self):
        # Filter
        filtered = []
        
        # Prepare search evaluator
        from app.common.utils.search_utils import SearchQueryEvaluator
        search_evaluator = SearchQueryEvaluator(self.search_query) if self.search_query else None

        for item in self.all_data:
            uid = item['uid']

            # Hide logic
            if uid in self.hidden_ids and not self.show_hidden:
                continue

            # Search logic
            if search_evaluator:
                parts = [
                    str(item.get('index', '')),
                    str(item.get('service_name', '')),
                    str(item.get('service_id', '')),
                    str(item.get('instance_id', '')),
                    str(item.get('version', '')),
                    str(item.get('major_version', '')),
                    str(item.get('minor_version', '')),
                    str(item.get('server_endpoint', '')),
                ]
                for sub in item.get('subscribe_info', []):
                    parts.append(str(sub.get('subscriber_ip_port', '')))
                for f_info in item.get('find_info', []):
                    parts.append(str(f_info.get('finder_ip', '')))
                    parts.append(str(f_info.get('find_version', '')))

                item_text = " ".join(parts).lower()
                if not search_evaluator.evaluate(item_text):
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
