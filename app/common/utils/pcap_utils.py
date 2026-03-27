import socket
import os
from scapy.utils import RawPcapReader
from typing import List, Dict, Callable, Optional


class PcapUtils:
    ENTRY_TYPE_NAMES = {
        0x00: 'FindService',
        0x01: 'OfferService',
        0x02: 'StopOfferService',
        0x03: 'SubscribeEventgroup',
        0x04: 'StopSubscribeEventgroup',
        0x05: 'SubscribeEventgroupAck',
        0x06: 'SubscribeEventgroupNack',
        0x07: 'SubscribeEventgroupAck',
    }
    ENDPOINT_OPTION_TYPES = {
        0x03: 'IPv4-Endpoint',
        0x04: 'IPv4-Endpoint',
        0x05: 'IPv4-Multicast',
        0x06: 'IPv6-Endpoint',
        0x07: 'IPv4-SD-Endpoint',
        0x14: 'IPv4-Multicast',
        0x16: 'IPv6-Multicast',
        0x24: 'IPv4-SD-Endpoint',
        0x26: 'IPv6-SD-Endpoint',
    }

    @staticmethod
    def parse_someip_sd_pcap(file_path: str, progress_callback: Optional[Callable[[int], None]] = None) -> List[Dict]:
        findings = []
        try:
            file_size = max(os.path.getsize(file_path), 1)
            is_pcapng = file_path.lower().endswith('.pcapng')
            if is_pcapng:
                from scapy.utils import RawPcapNgReader
                reader_cls = RawPcapNgReader
            else:
                reader_cls = RawPcapReader

            with reader_cls(file_path) as packets:
                for i, pkt_tuple in enumerate(packets):
                    if i % 1000 == 0 and progress_callback:
                        try:
                            if hasattr(packets, 'f'):
                                progress_callback(min(100, int((packets.f.tell() / file_size) * 100)))
                            elif hasattr(packets, 'wrapped') and hasattr(packets.wrapped, 'f'):
                                progress_callback(min(100, int((packets.wrapped.f.tell() / file_size) * 100)))
                        except Exception:
                            pass

                    pkt_data = pkt_tuple[0]
                    metadata = pkt_tuple[1]
                    parsed = PcapUtils._parse_packet(pkt_data, metadata, is_pcapng)
                    if parsed:
                        findings.extend(parsed)

            if progress_callback:
                progress_callback(100)
        except Exception as e:
            print(f"Error parsing PCAP: {e}")
        return findings

    @staticmethod
    def _parse_packet(pkt_data: bytes, metadata, is_pcapng: bool) -> List[Dict]:
        if len(pkt_data) < 34:
            return []

        eth_len = 14
        if pkt_data[12:14] == b'\x81\x00':
            eth_len = 18
        ether_type = int.from_bytes(pkt_data[eth_len - 2:eth_len], 'big')
        if ether_type != 0x0800:
            return []

        if len(pkt_data) < eth_len + 20:
            return []
        ver_ihl = pkt_data[eth_len]
        ihl = (ver_ihl & 0x0F) * 4
        if ihl < 20 or len(pkt_data) < eth_len + ihl + 8:
            return []
        if pkt_data[eth_len + 9] != 17:
            return []

        src_ip = socket.inet_ntoa(pkt_data[eth_len + 12:eth_len + 16])
        dst_ip = socket.inet_ntoa(pkt_data[eth_len + 16:eth_len + 20])
        udp_start = eth_len + ihl
        src_port = int.from_bytes(pkt_data[udp_start:udp_start + 2], 'big')
        dst_port = int.from_bytes(pkt_data[udp_start + 2:udp_start + 4], 'big')
        payload = pkt_data[udp_start + 8:]
        if len(payload) < 16:
            return []
        if payload[0:2] != b'\xFF\xFF' or payload[2:4] != b'\x81\x00':
            return []

        timestamp = 0.0
        try:
            if is_pcapng and hasattr(metadata, 'tshigh'):
                timestamp = (float(metadata.tshigh) * 2 ** 32 + float(metadata.tslow)) / float(metadata.resol)
            elif not is_pcapng:
                timestamp = float(metadata[0]) + float(metadata[1]) / 1_000_000.0
        except Exception:
            pass

        sd_offset = 16
        if len(payload) < sd_offset + 8:
            return []
        sd_offset += 4  # flags+reserved
        entries_len = int.from_bytes(payload[sd_offset:sd_offset + 4], 'big')
        sd_offset += 4
        entries_start = sd_offset
        entries_end = entries_start + entries_len
        if len(payload) < entries_start:
            return []
        entries_data = payload[entries_start:min(entries_end, len(payload))]

        options_dict = {}
        if len(payload) >= entries_end + 4:
            options_len = int.from_bytes(payload[entries_end:entries_end + 4], 'big')
            options_start = entries_end + 4
            options_end = options_start + options_len
            options_data = payload[options_start:min(options_end, len(payload))]
            options_dict = PcapUtils._parse_sd_options(options_data)

        entries = PcapUtils._parse_sd_entries(entries_data, options_dict)
        packet_src = f"{src_ip}:{src_port}"
        packet_dst = f"{dst_ip}:{dst_port}"
        for entry in entries:
            entry['timestamp'] = timestamp
            entry['packet_src_ip'] = src_ip
            entry['packet_src_endpoint'] = packet_src
            entry['packet_dst_ip'] = dst_ip
            entry['packet_dst_endpoint'] = packet_dst
        return entries

    @staticmethod
    def _parse_sd_entries(data: bytes, options_map: Dict[int, Dict]) -> List[Dict]:
        entries = []
        offset = 0
        while offset + 16 <= len(data):
            entry_type = data[offset]
            index1 = data[offset + 1]
            index2 = data[offset + 2]
            opt_counts = data[offset + 3]
            num_opt1 = (opt_counts >> 4) & 0x0F
            num_opt2 = opt_counts & 0x0F
            service_id = int.from_bytes(data[offset + 4:offset + 6], 'big')
            instance_id = int.from_bytes(data[offset + 6:offset + 8], 'big')
            major_version = data[offset + 8]
            ttl = int.from_bytes(b'\x00' + data[offset + 9:offset + 12], 'big')
            minor_or_counter = int.from_bytes(data[offset + 12:offset + 16], 'big')

            referenced_options = []
            for i in range(num_opt1):
                if index1 + i in options_map:
                    referenced_options.append(options_map[index1 + i])
            for i in range(num_opt2):
                if index2 + i in options_map:
                    referenced_options.append(options_map[index2 + i])

            endpoint = ''
            endpoint_ip = ''
            endpoint_port = ''
            l4_proto = ''
            config_texts = []
            for opt in referenced_options:
                if opt.get('type') in ('IPv4-Endpoint', 'IPv6-Endpoint', 'IPv4-Multicast', 'IPv6-Multicast', 'IPv4-SD-Endpoint', 'IPv6-SD-Endpoint'):
                    endpoint_ip = opt.get('ip', '')
                    endpoint_port = opt.get('port', '')
                    l4_proto = opt.get('l4_proto', '')
                    endpoint = f"{endpoint_ip}:{endpoint_port}" if endpoint_ip and endpoint_port != '' else endpoint_ip
                elif opt.get('type') == 'Configuration' and opt.get('text'):
                    config_texts.extend(opt.get('text', []))

            eventgroup_id = ''
            counter = ''
            minor_version = None
            if entry_type in (0x00, 0x01, 0x02):
                minor_version = minor_or_counter
            elif entry_type in (0x03, 0x04, 0x05, 0x06, 0x07):
                counter = (minor_or_counter >> 16) & 0x0F
                eventgroup_id = f"0x{(minor_or_counter & 0xFFFF):04X}"

            entries.append({
                'entry_type': entry_type,
                'entry_type_name': PcapUtils.ENTRY_TYPE_NAMES.get(entry_type, f'Unknown_{entry_type:#x}'),
                'service_id': f"0x{service_id:04X}",
                'instance_id': f"0x{instance_id:04X}",
                'major_version': major_version,
                'minor_version': minor_version,
                'version': f"{major_version}.{minor_version}" if minor_version is not None else f"{major_version}.x",
                'ttl': ttl,
                'endpoint': endpoint,
                'endpoint_ip': endpoint_ip,
                'endpoint_port': endpoint_port,
                'l4_proto': l4_proto,
                'eventgroup_id': eventgroup_id,
                'counter': counter,
                'config_texts': config_texts,
            })
            offset += 16
        return entries

    @staticmethod
    def _parse_sd_options(data: bytes) -> Dict[int, Dict]:
        options = {}
        offset = 0
        idx = 0
        while offset + 3 < len(data):
            length = int.from_bytes(data[offset:offset + 2], 'big')
            option_total = 2 + length
            if length <= 0 or offset + option_total > len(data):
                break
            option_type = data[offset + 2]
            option_payload = data[offset + 4:offset + option_total]
            opt = {'type': 'Unknown', 'raw_type': option_type}

            endpoint_type = PcapUtils.ENDPOINT_OPTION_TYPES.get(option_type)
            if endpoint_type in ('IPv4-Endpoint', 'IPv4-Multicast', 'IPv4-SD-Endpoint'):
                if len(option_payload) >= 8:
                    opt.update({
                        'type': endpoint_type,
                        'ip': socket.inet_ntoa(option_payload[0:4]),
                        'l4_proto': 'UDP' if option_payload[5] == 0x11 else ('TCP' if option_payload[5] == 0x06 else str(option_payload[5])),
                        'port': int.from_bytes(option_payload[6:8], 'big')
                    })
            elif endpoint_type in ('IPv6-Endpoint', 'IPv6-Multicast', 'IPv6-SD-Endpoint'):
                if len(option_payload) >= 20:
                    opt.update({
                        'type': endpoint_type,
                        'ip': socket.inet_ntop(socket.AF_INET6, option_payload[0:16]),
                        'l4_proto': 'UDP' if option_payload[17] == 0x11 else ('TCP' if option_payload[17] == 0x06 else str(option_payload[17])),
                        'port': int.from_bytes(option_payload[18:20], 'big')
                    })
            elif option_type == 0x01:
                text_items = []
                cursor = 0
                while cursor < len(option_payload):
                    item_len = option_payload[cursor]
                    cursor += 1
                    if item_len == 0 or cursor + item_len > len(option_payload):
                        break
                    item = option_payload[cursor:cursor + item_len].decode('utf-8', errors='ignore').strip('\x00')
                    if item:
                        text_items.append(item)
                    cursor += item_len
                if not text_items and option_payload:
                    fallback = option_payload.decode('utf-8', errors='ignore').strip('\x00')
                    if fallback:
                        text_items.append(fallback)
                opt.update({'type': 'Configuration', 'text': text_items})

            options[idx] = opt
            idx += 1
            offset += option_total
        return options
