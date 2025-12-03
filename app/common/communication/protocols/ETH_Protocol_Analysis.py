import struct
from typing import Dict, Any, Optional, List
import socket
from enum import IntEnum


class EtherType(IntEnum):
    """常见的以太网类型值"""
    IPV4 = 0x0800
    ARP = 0x0806
    IPV6 = 0x86DD
    VLAN = 0x8100
    DOT1Q = 0x8100
    IPX = 0x8137
    SNMP = 0x814C
    PPPoE_DISCOVERY = 0x8863
    PPPoE_SESSION = 0x8864
    MPLS_UNICAST = 0x8847
    MPLS_MULTICAST = 0x8848


class IPProtocol(IntEnum):
    """IP协议号"""
    ICMP = 1
    TCP = 6
    UDP = 17
    GRE = 47
    ESP = 50
    AH = 51
    ICMPv6 = 58


class SOMEIPMessageType(IntEnum):
    """SOME/IP 消息类型"""
    REQUEST = 0x00
    REQUEST_NO_RETURN = 0x01
    NOTIFICATION = 0x02
    RESPONSE = 0x80
    ERROR = 0x81
    TP_REQUEST = 0x20
    TP_REQUEST_NO_RETURN = 0x21
    TP_NOTIFICATION = 0x22
    TP_RESPONSE = 0xA0
    TP_ERROR = 0xA1


class SOMEIPReturnCode(IntEnum):
    """SOME/IP 返回码"""
    E_OK = 0x00
    E_NOT_OK = 0x01
    E_UNKNOWN_SERVICE = 0x02
    E_UNKNOWN_METHOD = 0x03
    E_NOT_READY = 0x04
    E_NOT_REACHABLE = 0x05
    E_TIMEOUT = 0x06
    E_WRONG_PROTOCOL_VERSION = 0x07
    E_WRONG_INTERFACE_VERSION = 0x08
    E_MALFORMED_MESSAGE = 0x09
    E_WRONG_MESSAGE_TYPE = 0x0A


class DoIPPayloadType(IntEnum):
    """DoIP 载荷类型"""
    GENERIC_ACK = 0x0000
    VEHICLE_IDENTIFICATION_REQUEST = 0x0001
    VEHICLE_IDENTIFICATION_REQUEST_EID = 0x0002
    VEHICLE_IDENTIFICATION_REQUEST_VIN = 0x0003
    VEHICLE_ANNOUNCEMENT = 0x0004
    ROUTING_ACTIVATION_REQUEST = 0x0005
    ROUTING_ACTIVATION_RESPONSE = 0x0006
    ALIVE_CHECK_REQUEST = 0x0007
    ALIVE_CHECK_RESPONSE = 0x0008
    DOIP_ENTITY_STATUS_REQUEST = 0x4001
    DOIP_ENTITY_STATUS_RESPONSE = 0x4002
    DIAGNOSTIC_POWER_MODE_REQUEST = 0x4003
    DIAGNOSTIC_POWER_MODE_RESPONSE = 0x4004
    DIAGNOSTIC_MESSAGE = 0x8001
    DIAGNOSTIC_MESSAGE_ACK = 0x8002
    DIAGNOSTIC_MESSAGE_NACK = 0x8003


class EthernetFrame:
    def __init__(self, raw_data: bytes):
        self.raw_data = raw_data
        self.dest_mac = None
        self.src_mac = None
        self.ether_type = None
        self.payload = None
        self.vlan_tags = []  # 支持多层VLAN
        self.length = len(raw_data)

    def parse(self) -> bool:
        """解析以太网帧，支持多层VLAN标签"""
        if len(self.raw_data) < 14:
            return False

        data = self.raw_data
        offset = 0

        # 解析目的MAC和源MAC
        try:
            self.dest_mac = self._bytes_to_mac(data[offset:offset + 6])
            self.src_mac = self._bytes_to_mac(data[offset + 6:offset + 12])
            offset += 12

            # 解析类型/长度字段
            ether_type = struct.unpack('!H', data[offset:offset + 2])[0]
            offset += 2

            # 处理VLAN标签（802.1Q）
            while ether_type in [EtherType.DOT1Q, 0x9100, 0x9200, 0x9300]:  # 支持多种VLAN标签
                if len(data) < offset + 4:
                    return False

                vlan_header = struct.unpack('!H', data[offset:offset + 2])[0]
                vlan_tag = {
                    'tpid': hex(ether_type),
                    'pcp': (vlan_header >> 13) & 0x07,
                    'dei': (vlan_header >> 12) & 0x01,
                    'vid': vlan_header & 0x0FFF
                }
                self.vlan_tags.append(vlan_tag)

                offset += 2
                ether_type = struct.unpack('!H', data[offset:offset + 2])[0]
                offset += 2

            self.ether_type = ether_type
            self.payload = data[offset:]

            return True

        except Exception as e:
            print(f"Ethernet parsing error: {e}")
            return False

    def _bytes_to_mac(self, mac_bytes: bytes) -> str:
        """将字节转换为MAC地址字符串"""
        return ':'.join(f'{b:02x}' for b in mac_bytes).upper()


class ProtocolParser:
    def __init__(self):
        self.parsed_layers = []

    def parse_ethernet_frame(self, raw_bytes: bytes) -> Dict[str, Any]:
        """
        解析以太网帧的主方法，自动解析到不可解析为止

        Args:
            raw_bytes: 以太网帧的原始字节

        Returns:
            包含所有解析层信息的字典
        """
        result = {
            'layers': [],
            'remaining_data': len(raw_bytes),
            'error': None
        }

        try:
            data = raw_bytes
            layer_num = 0

            # 解析以太网层
            eth_frame = EthernetFrame(data)
            if eth_frame.parse():
                eth_layer = {
                    'layer': 'ethernet',
                    'destination_mac': eth_frame.dest_mac,
                    'source_mac': eth_frame.src_mac,
                    'ether_type': hex(eth_frame.ether_type),
                    'ether_type_name': self._get_ethertype_name(eth_frame.ether_type),
                    'vlan_tags': eth_frame.vlan_tags,
                    'payload_length': len(eth_frame.payload),
                    'header_length': len(data) - len(eth_frame.payload)
                }
                result['layers'].append(eth_layer)
                data = eth_frame.payload
                layer_num += 1

                # 根据以太网类型继续解析
                if eth_frame.ether_type == EtherType.IPV4:
                    data = self._parse_ipv4(data, result, layer_num)
                elif eth_frame.ether_type == EtherType.IPV6:
                    data = self._parse_ipv6(data, result, layer_num)
                elif eth_frame.ether_type == EtherType.ARP:
                    data = self._parse_arp(data, result, layer_num)
                elif eth_frame.ether_type == EtherType.PPPoE_SESSION:
                    data = self._parse_pppoe(data, result, layer_num)
                # 可以继续添加其他以太网类型解析

            result['remaining_data'] = len(data)
            if data and len(data) > 0:
                result['layers'].append({
                    'layer': 'unknown',
                    'data_length': len(data),
                    'data_preview': data[:32].hex()  # 预览前32字节
                })

        except Exception as e:
            result['error'] = f'Parsing error: {str(e)}'

        return result

    def _parse_ipv4(self, data: bytes, result: Dict, layer_num: int) -> bytes:
        """解析IPv4数据包"""
        if len(data) < 20:
            return data

        try:
            ip_header = data[:20]
            iph = struct.unpack('!BBHHHBBH4s4s', ip_header)

            version_ihl = iph[0]
            version = version_ihl >> 4
            ihl = (version_ihl & 0xF) * 4
            protocol = iph[6]
            total_length = iph[2]
            src_ip = socket.inet_ntoa(iph[8])
            dest_ip = socket.inet_ntoa(iph[9])

            # 检查IP头部长度是否有效
            if ihl < 20 or ihl > 60:  # IP头部最小20字节，最大60字节
                raise ValueError(f"Invalid IP header length: {ihl}")

            ip_layer = {
                'layer': 'network',
                'protocol': 'IPv4',
                'version': version,
                'header_length': ihl,
                'total_length': total_length,
                'protocol_number': protocol,
                'protocol_name': self._get_ip_protocol_name(protocol),
                'source_ip': src_ip,
                'destination_ip': dest_ip,
                'ttl': iph[5],
                'identification': iph[3],
                'flags': (iph[4] >> 13) & 0x07,
                'fragment_offset': iph[4] & 0x1FFF
            }

            # 处理IP选项（如果有）
            if ihl > 20:
                options_length = ihl - 20
                if len(data) >= ihl:
                    ip_layer['options'] = data[20:ihl].hex()
                else:
                    raise ValueError("IP header length exceeds available data")

            result['layers'].append(ip_layer)

            # 解析传输层
            if len(data) >= ihl:
                transport_data = data[ihl:total_length] if total_length <= len(data) else data[ihl:]
                return self._parse_transport(protocol, transport_data, result, layer_num + 1)
            else:
                return data[ihl:]

        except Exception as e:
            print(f"IPv4 parsing error: {e}")
            return data[20:] if len(data) > 20 else b''

    def _parse_ipv6(self, data: bytes, result: Dict, layer_num: int) -> bytes:
        """解析IPv6数据包"""
        if len(data) < 40:
            return data

        try:
            ipv6_header = data[:40]

            version_traffic_flow = struct.unpack('!I', ipv6_header[0:4])[0]
            version = version_traffic_flow >> 28
            traffic_class = (version_traffic_flow >> 20) & 0xFF
            flow_label = version_traffic_flow & 0xFFFFF

            payload_length = struct.unpack('!H', ipv6_header[4:6])[0]
            next_header = ipv6_header[6]
            hop_limit = ipv6_header[7]

            src_ip = socket.inet_ntop(socket.AF_INET6, ipv6_header[8:24])
            dest_ip = socket.inet_ntop(socket.AF_INET6, ipv6_header[24:40])

            ipv6_layer = {
                'layer': 'network',
                'protocol': 'IPv6',
                'version': version,
                'traffic_class': traffic_class,
                'flow_label': flow_label,
                'payload_length': payload_length,
                'next_header': next_header,
                'next_header_name': self._get_ip_protocol_name(next_header),
                'hop_limit': hop_limit,
                'source_ip': src_ip,
                'destination_ip': dest_ip
            }
            result['layers'].append(ipv6_layer)

            # 解析扩展头部或传输层
            if len(data) >= 40 + payload_length:
                next_data = data[40:40 + payload_length]
            else:
                next_data = data[40:]

            return self._parse_ipv6_extension_or_transport(next_header, next_data, result, layer_num + 1)

        except Exception as e:
            print(f"IPv6 parsing error: {e}")
            return data[40:] if len(data) > 40 else b''

    def _parse_ipv6_extension_or_transport(self, next_header: int, data: bytes, result: Dict, layer_num: int) -> bytes:
        """解析IPv6扩展头部或传输层"""
        # 常见的扩展头部类型
        extension_headers = {
            0: 'Hop-by-Hop',
            43: 'Routing',
            44: 'Fragment',
            50: 'ESP',
            51: 'AH',
            60: 'Destination'
        }

        while next_header in extension_headers and len(data) >= 8:
            try:
                header_type = extension_headers.get(next_header, f'Unknown_{next_header}')
                next_header = data[0]  # 下一个头部类型
                hdr_ext_len = data[1]  # 扩展头部长度（8字节为单位）
                header_length = (hdr_ext_len + 1) * 8

                if len(data) < header_length:
                    break

                ext_layer = {
                    'layer': 'ipv6_extension',
                    'protocol': header_type,
                    'header_type': next_header,
                    'header_length': header_length
                }
                result['layers'].append(ext_layer)

                data = data[header_length:]

            except Exception:
                break

        # 解析传输层
        return self._parse_transport(next_header, data, result, layer_num)

    def _parse_arp(self, data: bytes, result: Dict, layer_num: int) -> bytes:
        """解析ARP数据包"""
        if len(data) < 28:
            return data

        try:
            arp_fields = struct.unpack('!HHBBH6s4s6s4s', data[:28])

            arp_layer = {
                'layer': 'network',
                'protocol': 'ARP',
                'hardware_type': arp_fields[0],
                'protocol_type': hex(arp_fields[1]),
                'hardware_size': arp_fields[2],
                'protocol_size': arp_fields[3],
                'operation': 'request' if arp_fields[4] == 1 else 'reply',
                'sender_mac': self._bytes_to_mac(arp_fields[5]),
                'sender_ip': socket.inet_ntoa(arp_fields[6]),
                'target_mac': self._bytes_to_mac(arp_fields[7]),
                'target_ip': socket.inet_ntoa(arp_fields[8])
            }
            result['layers'].append(arp_layer)

            return data[28:]

        except Exception as e:
            print(f"ARP parsing error: {e}")
            return data[28:] if len(data) > 28 else b''

    def _parse_pppoe(self, data: bytes, result: Dict, layer_num: int) -> bytes:
        """解析PPPoE会话"""
        if len(data) < 6:
            return data

        try:
            ver_type = data[0]
            code = data[1]
            session_id = struct.unpack('!H', data[2:4])[0]
            length = struct.unpack('!H', data[4:6])[0]

            pppoe_layer = {
                'layer': 'pppoe',
                'protocol': 'PPPoE',
                'version': (ver_type >> 4) & 0x0F,
                'type': ver_type & 0x0F,
                'code': code,
                'session_id': session_id,
                'length': length
            }
            result['layers'].append(pppoe_layer)

            # PPPoE载荷通常是PPP协议
            ppp_data = data[6:6 + length] if len(data) >= 6 + length else data[6:]
            return self._parse_ppp(ppp_data, result, layer_num + 1)

        except Exception as e:
            print(f"PPPoE parsing error: {e}")
            return data[6:] if len(data) > 6 else b''

    def _parse_ppp(self, data: bytes, result: Dict, layer_num: int) -> bytes:
        """解析PPP协议"""
        if len(data) < 2:
            return data

        try:
            protocol = struct.unpack('!H', data[:2])[0]

            ppp_layer = {
                'layer': 'ppp',
                'protocol': 'PPP',
                'protocol_field': hex(protocol),
                'protocol_name': self._get_ppp_protocol_name(protocol)
            }
            result['layers'].append(ppp_layer)

            # 继续解析PPP载荷
            return data[2:]

        except Exception as e:
            print(f"PPP parsing error: {e}")
            return data[2:] if len(data) > 2 else b''

    def _parse_transport(self, protocol: int, data: bytes, result: Dict, layer_num: int) -> bytes:
        """解析传输层协议"""
        try:
            if protocol == IPProtocol.TCP:
                return self._parse_tcp(data, result, layer_num)
            elif protocol == IPProtocol.UDP:
                return self._parse_udp(data, result, layer_num)
            elif protocol == IPProtocol.ICMP:
                return self._parse_icmp(data, result, layer_num)
            elif protocol == IPProtocol.ICMPv6:
                return self._parse_icmpv6(data, result, layer_num)
            else:
                # 未知传输层协议，返回剩余数据
                return data
        except Exception as e:
            print(f"Transport layer parsing error: {e}")
            return data

    def _parse_tcp(self, data: bytes, result: Dict, layer_num: int) -> bytes:
        """解析TCP段"""
        if len(data) < 20:
            return data

        try:
            tcp_header = data[:20]
            tcph = struct.unpack('!HHLLBBHHH', tcp_header)

            data_offset = (tcph[4] >> 4) * 4
            if data_offset < 20:  # TCP头部最小20字节
                data_offset = 20

            flags = tcph[4] & 0x3F

            tcp_layer = {
                'layer': 'transport',
                'protocol': 'TCP',
                'source_port': tcph[0],
                'destination_port': tcph[1],
                'sequence_number': tcph[2],
                'acknowledgment_number': tcph[3],
                'data_offset': data_offset,
                'flags': {
                    'urg': (flags >> 5) & 1,
                    'ack': (flags >> 4) & 1,
                    'psh': (flags >> 3) & 1,
                    'rst': (flags >> 2) & 1,
                    'syn': (flags >> 1) & 1,
                    'fin': flags & 1
                },
                'window_size': tcph[5],
                'checksum': tcph[6],
                'urgent_pointer': tcph[7]
            }

            # 处理TCP选项（如果有）
            if data_offset > 20:
                options_length = data_offset - 20
                if len(data) >= data_offset:
                    tcp_layer['options'] = data[20:data_offset].hex()
                else:
                    raise ValueError("TCP header length exceeds available data")

            result['layers'].append(tcp_layer)

            # 获取IP层的总长度
            ip_total_length = 0
            for layer in reversed(result['layers']):
                if layer.get('protocol') == 'IPv4':
                    ip_total_length = layer.get('total_length', 0)
                    break

            # 计算TCP载荷长度
            if ip_total_length > 0:
                ip_header_length = next((layer.get('header_length', 20) for layer in result['layers']
                                         if layer.get('protocol') == 'IPv4'), 20)
                tcp_payload_length = ip_total_length - ip_header_length - data_offset
                app_data = data[data_offset:data_offset + tcp_payload_length]
            else:
                app_data = data[data_offset:]

            # 解析应用层
            return self._parse_application(tcph[0], tcph[1], app_data, result, layer_num + 1)

        except Exception as e:
            print(f"TCP parsing error: {e}")
            return data[20:] if len(data) > 20 else b''

    def _parse_udp(self, data: bytes, result: Dict, layer_num: int) -> bytes:
        """解析UDP数据报"""
        if len(data) < 8:
            return data

        try:
            udp_header = data[:8]
            udph = struct.unpack('!HHHH', udp_header)

            udp_layer = {
                'layer': 'transport',
                'protocol': 'UDP',
                'source_port': udph[0],
                'destination_port': udph[1],
                'length': udph[2],
                'checksum': udph[3]
            }
            result['layers'].append(udp_layer)

            # 解析应用层
            app_data = data[8:8 + udph[2] - 8] if len(data) >= udph[2] else data[8:]
            return self._parse_application(udph[0], udph[1], app_data, result, layer_num + 1)

        except Exception as e:
            print(f"UDP parsing error: {e}")
            return data[8:] if len(data) > 8 else b''

    def _parse_icmp(self, data: bytes, result: Dict, layer_num: int) -> bytes:
        """解析ICMP报文"""
        if len(data) < 4:
            return data

        try:
            icmp_header = data[:4]
            icmph = struct.unpack('!BBH', icmp_header)

            icmp_layer = {
                'layer': 'transport',
                'protocol': 'ICMP',
                'type': icmph[0],
                'code': icmph[1],
                'checksum': icmph[2]
            }
            result['layers'].append(icmp_layer)

            return data[4:]

        except Exception as e:
            print(f"ICMP parsing error: {e}")
            return data[4:] if len(data) > 4 else b''

    def _parse_icmpv6(self, data: bytes, result: Dict, layer_num: int) -> bytes:
        """解析ICMPv6报文"""
        if len(data) < 4:
            return data

        try:
            icmp_header = data[:4]
            icmph = struct.unpack('!BBH', icmp_header)

            icmp_layer = {
                'layer': 'transport',
                'protocol': 'ICMPv6',
                'type': icmph[0],
                'code': icmph[1],
                'checksum': icmph[2]
            }
            result['layers'].append(icmp_layer)

            return data[4:]

        except Exception as e:
            print(f"ICMPv6 parsing error: {e}")
            return data[4:] if len(data) > 4 else b''

    def _parse_application(self, src_port: int, dst_port: int, data: bytes, result: Dict, layer_num: int) -> bytes:
        """根据端口号识别应用层协议"""
        # SOME/IP和SOMEIP-SD通常使用相同的端口(13400)
        if dst_port == 13400 or src_port == 13400:
            if len(data) >= 16:  # 检查是否有足够的数据解析头部
                # 检查是否是SOMEIP-SD(服务ID=0xFFFF, 方法ID=0x8100)
                service_id = struct.unpack('!H', data[0:2])[0]
                method_id = struct.unpack('!H', data[2:4])[0]

                if service_id == 0xFFFF and method_id == 0x8100:
                    return self._parse_someip_sd(data, result, layer_num)
                else:
                    return self._parse_someip(data, result, layer_num)
            else:
                return self._parse_someip(data, result, layer_num)
        elif dst_port == 13401 or src_port == 13401:  # DoIP
            return self._parse_doip(data, result, layer_num)
        else:
            # 其他常见协议
            common_ports = {
                80: 'HTTP', 443: 'HTTPS', 53: 'DNS', 25: 'SMTP',
                110: 'POP3', 143: 'IMAP', 22: 'SSH', 23: 'TELNET',
                21: 'FTP', 67: 'DHCP Server', 68: 'DHCP Client',
                69: 'TFTP', 123: 'NTP', 161: 'SNMP', 162: 'SNMP Trap',
                389: 'LDAP', 636: 'LDAPS', 993: 'IMAPS', 995: 'POP3S'
            }

            port = dst_port if dst_port in common_ports else src_port
            protocol_name = common_ports.get(port, f'Port_{port}')

            app_layer = {
                'layer': 'application',
                'protocol': protocol_name,
                'source_port': src_port,
                'destination_port': dst_port,
                'data_length': len(data)
            }
            result['layers'].append(app_layer)
            return b''

    def _parse_someip(self, data: bytes, result: Dict, layer_num: int) -> bytes:
        """解析SOME/IP协议"""
        if len(data) < 16:  # SOME/IP头部最小16字节
            someip_layer = {
                'layer': 'application',
                'protocol': 'SOME/IP',
                'error': 'Incomplete SOME/IP header (less than 16 bytes)',
                'data_length': len(data),
                'data_preview': data.hex() if len(data) > 0 else ''
            }
            result['layers'].append(someip_layer)
            return b''

        try:
            # 解析SOME/IP头部 (16字节)
            service_id = struct.unpack('!H', data[0:2])[0]
            method_id = struct.unpack('!H', data[2:4])[0]
            length = struct.unpack('!I', data[4:8])[0]
            client_id = struct.unpack('!H', data[8:10])[0]
            session_id = struct.unpack('!H', data[10:12])[0]
            protocol_ver = data[12]
            interface_ver = data[13]
            message_type = data[14]
            return_code = data[15]

            someip_layer = {
                'layer': 'application',
                'protocol': 'SOME/IP',
                'service_id': hex(service_id),
                'method_id': hex(method_id),
                'length': length,
                'client_id': client_id,
                'session_id': session_id,
                'protocol_version': protocol_ver,
                'interface_version': interface_ver,
                'message_type': message_type,
                'message_type_name': self._get_someip_message_type_name(message_type),
                'return_code': return_code,
                'return_code_name': self._get_someip_return_code_name(return_code)
            }

            # 计算载荷长度 (length字段包含8字节的额外长度)
            payload_length = length - 8
            total_length = 16 + payload_length

            if len(data) >= total_length:
                someip_layer['payload_length'] = payload_length
                if payload_length > 0:
                    someip_layer['payload_preview'] = data[16:16 + min(32, payload_length)].hex()
                    someip_layer['payload'] = data[16:total_length].hex()
            else:
                someip_layer[
                    'error'] = f'Incomplete payload: expected {payload_length} bytes, got {len(data) - 16} bytes'
                someip_layer['payload_preview'] = data[16:].hex()

            result['layers'].append(someip_layer)

            # 返回剩余数据
            return data[total_length:] if len(data) > total_length else b''

        except Exception as e:
            print(f"SOME/IP parsing error: {e}")
            someip_layer = {
                'layer': 'application',
                'protocol': 'SOME/IP',
                'error': f'Parsing error: {str(e)}',
                'data_length': len(data),
                'data_preview': data[:32].hex() if len(data) > 0 else ''
            }
            result['layers'].append(someip_layer)
            return b''

    def _parse_someip_sd(self, data: bytes, result: Dict, layer_num: int) -> bytes:
        """解析SOMEIP-SD协议"""
        if len(data) < 16:
            someip_sd_layer = {
                'layer': 'application',
                'protocol': 'SOMEIP-SD',
                'error': 'Incomplete SOMEIP-SD header (less than 16 bytes)',
                'data_length': len(data)
            }
            result['layers'].append(someip_sd_layer)
            return b''

        try:
            # 解析SOME/IP头部 (16字节)
            service_id = struct.unpack('!H', data[0:2])[0]
            method_id = struct.unpack('!H', data[2:4])[0]
            length = struct.unpack('!I', data[4:8])[0]
            client_id = struct.unpack('!H', data[8:10])[0]
            session_id = struct.unpack('!H', data[10:12])[0]
            protocol_ver = data[12]
            interface_ver = data[13]
            message_type = data[14]
            return_code = data[15]

            someip_sd_layer = {
                'layer': 'application',
                'protocol': 'SOMEIP-SD',
                'service_id': hex(service_id),
                'method_id': hex(method_id),
                'length': length,
                'client_id': client_id,
                'session_id': session_id,
                'protocol_version': protocol_ver,
                'interface_version': interface_ver,
                'message_type': message_type,
                'message_type_name': self._get_someip_message_type_name(message_type),
                'return_code': return_code,
                'return_code_name': self._get_someip_return_code_name(return_code),
                'is_sd': True
            }

            # 解析SOMEIP-SD特定字段
            if len(data) >= 28:  # 基本SD头部(16) + Flags(4) + EntriesArrayLength(4) + OptionsArrayLength(4)
                flags = struct.unpack('!I', data[16:20])[0]
                entries_length = struct.unpack('!I', data[20:24])[0]
                options_length = struct.unpack('!I', data[24:28])[0]

                someip_sd_layer.update({
                    'flags': hex(flags),
                    'reboot_flag': (flags >> 31) & 1,
                    'unicast_flag': (flags >> 30) & 1,
                    'entries_length': entries_length,
                    'options_length': options_length
                })

                # 解析Entries数组
                entries_start = 28
                entries_end = entries_start + entries_length
                if len(data) >= entries_end:
                    someip_sd_layer['entries'] = self._parse_sd_entries(data[entries_start:entries_end])

                # 解析Options数组
                options_start = entries_end
                options_end = options_start + options_length
                if len(data) >= options_end:
                    someip_sd_layer['options'] = self._parse_sd_options(data[options_start:options_end])

            # 计算总长度 (length字段包含8字节的额外长度)
            payload_length = length - 8
            total_length = 16 + payload_length if payload_length > 0 else 16

            result['layers'].append(someip_sd_layer)

            # 返回剩余数据
            return data[total_length:] if len(data) > total_length else b''

        except Exception as e:
            print(f"SOMEIP-SD parsing error: {e}")
            someip_sd_layer = {
                'layer': 'application',
                'protocol': 'SOMEIP-SD',
                'error': f'Parsing error: {str(e)}',
                'data_length': len(data)
            }
            result['layers'].append(someip_sd_layer)
            return b''

    def _parse_sd_entries(self, data: bytes) -> List[Dict]:
        """解析SOMEIP-SD Entries数组"""
        entries = []
        offset = 0
        data_length = len(data)

        while offset + 16 <= data_length:  # 每个Entry至少16字节
            entry_type = data[offset]
            index1 = data[offset + 1]
            index2 = data[offset + 2]
            num_opt1 = data[offset + 3] & 0x0F
            num_opt2 = (data[offset + 3] >> 4) & 0x0F
            service_id = struct.unpack('!H', data[offset + 4:offset + 6])[0]
            instance_id = struct.unpack('!H', data[offset + 6:offset + 8])[0]
            major_ver = data[offset + 8]
            ttl = struct.unpack('!I', data[offset + 12:offset + 16])[0]

            entry = {
                'type': entry_type,
                'type_name': self._get_sd_entry_type_name(entry_type),
                'index1': index1,
                'index2': index2,
                'num_opt1': num_opt1,
                'num_opt2': num_opt2,
                'service_id': hex(service_id),
                'instance_id': instance_id,
                'major_version': major_ver,
                'ttl': ttl
            }

            # 解析IPv4/6端点信息
            if entry_type in [0x00, 0x01, 0x06, 0x07]:  # 包含端点的Entry类型
                if offset + 24 > data_length:
                    entry['error'] = 'Incomplete entry data'
                    entries.append(entry)
                    break

                ip_addr = data[offset + 16:offset + 20]
                port = struct.unpack('!H', data[offset + 20:offset + 22])[0]
                reserved = struct.unpack('!H', data[offset + 22:offset + 24])[0]

                entry.update({
                    'ip_address': socket.inet_ntoa(ip_addr),
                    'port': port,
                    'reserved': reserved
                })
                offset += 24
            else:
                offset += 16

            entries.append(entry)

        return entries

    def _parse_sd_options(self, data: bytes) -> List[Dict]:
        """解析SOMEIP-SD Options数组"""
        options = []
        offset = 0

        while offset + 4 <= len(data):  # 每个Option至少4字节
            length = struct.unpack('!H', data[offset:offset + 2])[0]
            option_type = data[offset + 2]
            option_data = data[offset + 4:offset + length] if offset + length <= len(data) else b''

            option = {
                'length': length,
                'type': option_type,
                'type_name': self._get_sd_option_type_name(option_type),
                'data': option_data.hex()
            }

            # 解析特定Option类型
            if option_type == 0x01:  # 配置选项
                if len(option_data) >= 4:
                    option['configuration'] = {
                        'ip_address': socket.inet_ntoa(option_data[:4]),
                        'reserved': option_data[4:].hex()
                    }

            options.append(option)
            offset += length

        return options

    def _get_sd_entry_type_name(self, entry_type: int) -> str:
        """获取SD Entry类型名称"""
        entry_types = {
            0x00: 'FindService',
            0x01: 'OfferService',
            0x02: 'StopOffer',
            0x03: 'SubscribeEventgroup',
            0x04: 'StopSubscribeEventgroup',
            0x05: 'SubscribeEventgroupAck',
            0x06: 'SubscribeEventgroupNack',
            0x07: 'SubscribeEventgroupNack'
        }
        return entry_types.get(entry_type, f'Unknown_{hex(entry_type)}')

    def _get_sd_option_type_name(self, option_type: int) -> str:
        """获取SD Option类型名称"""
        option_types = {
            0x01: 'Configuration',
            0x02: 'LoadBalancing',
            0x03: 'IPv4Endpoint',
            0x04: 'IPv6Endpoint',
            0x05: 'IPv4Multicast',
            0x06: 'IPv6Multicast',
            0x07: 'IPv4SdEndpoint',
            0x08: 'IPv6SdEndpoint'
        }
        return option_types.get(option_type, f'Unknown_{hex(option_type)}')

    def _parse_doip(self, data: bytes, result: Dict, layer_num: int) -> bytes:
        """解析DoIP协议"""
        if len(data) < 8:
            doip_layer = {
                'layer': 'application',
                'protocol': 'DoIP',
                'error': 'Incomplete DoIP header (less than 8 bytes)',
                'data_length': len(data)
            }
            result['layers'].append(doip_layer)
            return b''

        try:
            # 解析DoIP头部 (8字节)
            protocol_version = data[0]
            inverse_version = data[1]
            payload_type = struct.unpack('!H', data[2:4])[0]
            payload_length = struct.unpack('!I', data[4:8])[0]

            doip_layer = {
                'layer': 'application',
                'protocol': 'DoIP',
                'protocol_version': protocol_version,
                'inverse_version': inverse_version,
                'payload_type': payload_type,
                'payload_type_name': self._get_doip_payload_type_name(payload_type),
                'payload_length': payload_length
            }

            # 解析特定类型的DoIP载荷
            if len(data) >= 8 + payload_length:
                payload_data = data[8:8 + payload_length]

                # 根据payload_type解析不同消息
                if payload_type == 0x0008:  # Alive Check Response
                    if len(payload_data) >= 2:
                        doip_layer['alive_check'] = {
                            'source_address': struct.unpack('!H', payload_data[:2])[0]
                        }

                elif payload_type == 0x0005:  # Routing Activation Request
                    if len(payload_data) >= 11:
                        doip_layer['routing_activation'] = {
                            'source_address': struct.unpack('!H', payload_data[:2])[0],
                            'activation_type': payload_data[2],
                            'reserved': payload_data[3:11].hex()
                        }

                elif payload_type == 0x0006:  # Routing Activation Response
                    if len(payload_data) >= 9:
                        doip_layer['routing_activation_response'] = {
                            'client_address': struct.unpack('!H', payload_data[:2])[0],
                            'logical_address': struct.unpack('!H', payload_data[2:4])[0],
                            'response_code': payload_data[4],
                            'reserved': payload_data[5:9].hex()
                        }

                elif payload_type == 0x8001:  # Diagnostic Message
                    if len(payload_data) >= 4:
                        doip_layer['diagnostic_message'] = {
                            'source_address': struct.unpack('!H', payload_data[:2])[0],
                            'target_address': struct.unpack('!H', payload_data[2:4])[0],
                            'user_data': payload_data[4:].hex()
                        }

                elif payload_type == 0x8002:  # Diagnostic Message ACK
                    if len(payload_data) >= 4:
                        doip_layer['diagnostic_ack'] = {
                            'source_address': struct.unpack('!H', payload_data[:2])[0],
                            'target_address': struct.unpack('!H', payload_data[2:4])[0],
                            'ack_code': payload_data[4] if len(payload_data) > 4 else None
                        }

                elif payload_type == 0x0001:  # Vehicle Identification Request
                    if len(payload_data) >= 1:
                        doip_layer['vehicle_identification'] = {
                            'request_type': payload_data[0]
                        }

                elif payload_type == 0x0004:  # Vehicle Announcement
                    if len(payload_data) >= 32:
                        vin = payload_data[:17].decode('ascii', errors='replace').rstrip('\x00')
                        doip_layer['vehicle_announcement'] = {
                            'vin': vin,
                            'logical_address': struct.unpack('!H', payload_data[17:19])[0],
                            'eid': payload_data[19:25].hex(),
                            'gid': payload_data[25:31].hex(),
                            'action_type': payload_data[31]
                        }

            result['layers'].append(doip_layer)

            # 返回剩余数据
            total_length = 8 + payload_length
            return data[total_length:] if len(data) > total_length else b''

        except Exception as e:
            print(f"DoIP parsing error: {e}")
            doip_layer = {
                'layer': 'application',
                'protocol': 'DoIP',
                'error': f'Parsing error: {str(e)}',
                'data_length': len(data)
            }
            result['layers'].append(doip_layer)
            return b''

    def _get_someip_message_type_name(self, message_type: int) -> str:
        """获取SOME/IP消息类型名称"""
        try:
            return SOMEIPMessageType(message_type).name
        except ValueError:
            return f'Unknown_{message_type}'

    def _get_someip_return_code_name(self, return_code: int) -> str:
        """获取SOME/IP返回码名称"""
        try:
            return SOMEIPReturnCode(return_code).name
        except ValueError:
            return f'Unknown_{return_code}'

    def _get_doip_payload_type_name(self, payload_type: int) -> str:
        """获取DoIP载荷类型名称"""
        try:
            return DoIPPayloadType(payload_type).name
        except ValueError:
            return f'Unknown_{payload_type}'

    def _get_ethertype_name(self, ethertype: int) -> str:
        """获取以太网类型名称"""
        ethertype_map = {
            0x0800: 'IPv4',
            0x0806: 'ARP',
            0x8035: 'RARP',
            0x809B: 'AppleTalk',
            0x80F3: 'AppleTalk ARP',
            0x8100: 'VLAN',
            0x8137: 'IPX',
            0x814C: 'SNMP',
            0x86DD: 'IPv6',
            0x8808: 'Ethernet Flow Control',
            0x880B: 'PPP',
            0x8847: 'MPLS Unicast',
            0x8848: 'MPLS Multicast',
            0x8863: 'PPPoE Discovery',
            0x8864: 'PPPoE Session',
            0x8870: 'Jumbo Frames',
            0x888E: 'EAP over LAN',
            0x88A2: 'ATA over Ethernet',
            0x88A4: 'EtherCAT',
            0x88A8: 'Provider Bridging',
            0x88CC: 'LLDP',
            0x88E5: 'MAC Security',
            0x8906: 'FCoE'
        }
        return ethertype_map.get(ethertype, f'Unknown_{hex(ethertype)}')

    def _get_ip_protocol_name(self, protocol: int) -> str:
        """获取IP协议名称"""
        protocol_map = {
            0: 'HOPOPT', 1: 'ICMP', 2: 'IGMP', 6: 'TCP', 17: 'UDP',
            41: 'IPv6', 47: 'GRE', 50: 'ESP', 51: 'AH', 58: 'ICMPv6',
            88: 'EIGRP', 89: 'OSPF', 115: 'L2TP'
        }
        return protocol_map.get(protocol, f'Unknown_{protocol}')

    def _get_ppp_protocol_name(self, protocol: int) -> str:
        """获取PPP协议名称"""
        ppp_map = {
            0x0021: 'IPv4',
            0x0057: 'IPv6',
            0xC021: 'LCP',
            0xC023: 'PAP',
            0xC223: 'CHAP'
        }
        return ppp_map.get(protocol, f'Unknown_{hex(protocol)}')

    def _bytes_to_mac(self, mac_bytes: bytes) -> str:
        """将字节转换为MAC地址字符串"""
        return ':'.join(f'{b:02x}' for b in mac_bytes).upper()


def parse_ethernet_packet(raw_bytes: bytes) -> Dict[str, Any]:
    """
    解析以太网帧的主函数

    Args:
        raw_bytes: 以太网帧的原始字节数据

    Returns:
        包含所有解析层信息的字典
    """
    parser = ProtocolParser()
    return parser.parse_ethernet_frame(raw_bytes)


# 示例用法
# 示例用法
# 示例用法
if __name__ == "__main__":
    # 创建更完整的DoIP数据包示例
    def create_sample_doip_packet():
        """创建示例DoIP数据包（路由激活响应）"""
        # 以太网头部 (14字节)
        eth_header = (
                bytes.fromhex('ffffffffffff') +  # 目标MAC
                bytes.fromhex('000000000000') +  # 源MAC
                bytes.fromhex('0800')  # 以太网类型(IPv4)
        )

        # IP头部 (20字节)
        ip_header = bytes.fromhex(
            '45'  # 版本和头部长度
            '00'  # 服务类型
            '003C'  # 总长度(60字节)
            '0000'  # 标识
            '4000'  # 标志和片偏移
            '40'  # TTL
            '06'  # 协议(TCP)
            '8d8b'  # 校验和
            'c0a80001'  # 源IP(192.168.0.1)
            'c0a80002'  # 目标IP(192.168.0.2)
        )

        # TCP头部 (20字节)
        tcp_header = bytes.fromhex(
            'd431'  # 源端口(54321)
            '3459'  # 目标端口(13401 - DoIP标准端口)
            '00000000'  # 序列号
            '00000000'  # 确认号
            '50'  # 数据偏移(20字节)
            '02'  # 标志(SYN)
            '2000'  # 窗口大小
            'a8a1'  # 校验和
            '0000'  # 紧急指针
        )

        # DoIP头部 + 路由激活响应载荷
        doip_data = bytes.fromhex(
            '02FD'  # 协议版本和反向版本
            '0006'  # 载荷类型(路由激活响应)
            '00000009'  # 载荷长度(9字节)
            # 路由激活响应载荷
            'E080'  # 客户端地址
            '0ABC'  # 逻辑地址
            '00'  # 响应码(0x00表示成功)
            '00000000'  # 保留字段
        )

        return eth_header + ip_header + tcp_header + doip_data


    # 创建并解析数据包
    sample_data = create_sample_doip_packet()
    print(f"Generated packet length: {len(sample_data)} bytes")  # 应该输出62

    # 解析数据包
    result = parse_ethernet_packet(sample_data)

    # 打印解析结果
    import json

    print(json.dumps(result, indent=2, default=str))


