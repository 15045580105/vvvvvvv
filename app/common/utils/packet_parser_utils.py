from __future__ import annotations

import re
import struct
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, cast

from app.common.utils.pcap_utils import PcapUtils
from app.common.utils.someip_utils import get_payload_rules, get_service_info, import_someip_matrix


class PacketParserUtils:
    """通用报文解析工具，提供文件导入、列表摘要和结构树构建能力。"""

    DEFAULT_BATCH_SIZE = 200
    DEFAULT_INITIAL_BATCH_SIZE = 20
    DEFAULT_FLUSH_INTERVAL_MS = 150

    SUPPORTED_FILE_FILTER = (
        "Packet Files (*.pcap *.pcapng *.txt *.log *.hex *.bin *.dat);;"
        "PCAP Files (*.pcap *.pcapng);;"
        "Text Files (*.txt *.log *.hex);;"
        "Binary Files (*.bin *.dat);;"
        "All Files (*.*)"
    )
    _matrix_service_index: Optional[Dict[str, Dict[str, Any]]] = None
    _matrix_fingerprint: Optional[Tuple[Any, Any]] = None

    @classmethod
    def load_packets(
        cls,
        file_path: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> List[Dict[str, Any]]:
        path = Path(file_path)
        suffix = path.suffix.lower()

        cls._report_progress(progress_callback, 0, "准备导入文件...")

        if suffix in {".pcap", ".pcapng"}:
            return cls._load_capture_packets(path, progress_callback=progress_callback)

        if suffix in {".txt", ".log", ".hex"}:
            packets = cls._load_text_packets(path, progress_callback=progress_callback)
            if packets:
                cls._report_progress(progress_callback, 100, "文本报文导入完成")
                return packets

        cls._report_progress(progress_callback, 20, "正在读取二进制文件...")
        raw_bytes = path.read_bytes()
        if not raw_bytes:
            cls._report_progress(progress_callback, 100, "文件为空")
            return []
        cls._report_progress(progress_callback, 70, "正在导入二进制报文...")
        packets = [cls._build_packet_record(1, raw_bytes, "-", source_hint="binary")]
        cls._report_progress(progress_callback, 100, "二进制报文导入完成")
        return packets

    @classmethod
    def stream_packet_batches(
        cls,
        file_path: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        initial_batch_size: Optional[int] = None,
        flush_interval_ms: int = DEFAULT_FLUSH_INTERVAL_MS,
    ) -> Iterator[List[Dict[str, Any]]]:
        path = Path(file_path)
        suffix = path.suffix.lower()

        cls._report_progress(progress_callback, 0, "准备导入文件...")

        if suffix in {".pcap", ".pcapng"}:
            yield from cls._stream_capture_packet_batches(
                path,
                progress_callback=progress_callback,
                batch_size=batch_size,
                initial_batch_size=initial_batch_size,
                flush_interval_ms=flush_interval_ms,
            )
            return

        if suffix in {".txt", ".log", ".hex"}:
            yielded = False
            for batch in cls._stream_text_packet_batches(
                path,
                progress_callback=progress_callback,
                batch_size=batch_size,
                initial_batch_size=initial_batch_size,
                flush_interval_ms=flush_interval_ms,
            ):
                yielded = True
                yield batch
            if yielded:
                cls._report_progress(progress_callback, 100, "文本报文导入完成")
                return

        cls._report_progress(progress_callback, 20, "正在读取二进制文件...")
        raw_bytes = path.read_bytes()
        if not raw_bytes:
            cls._report_progress(progress_callback, 100, "文件为空")
            return
        cls._report_progress(progress_callback, 70, "正在导入二进制报文...")
        packets = [cls._build_packet_record(1, raw_bytes, "-", source_hint="binary")]
        cls._report_progress(progress_callback, 100, "二进制报文导入完成")
        yield packets

    @classmethod
    def _load_capture_packets(
        cls,
        path: Path,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> List[Dict[str, Any]]:
        packets: List[Dict[str, Any]] = []
        is_pcapng = path.suffix.lower() == ".pcapng"
        file_size = max(path.stat().st_size, 1)

        if is_pcapng:
            from scapy.utils import RawPcapNgReader

            reader_cls = RawPcapNgReader
        else:
            from scapy.utils import RawPcapReader

            reader_cls = RawPcapReader

        cls._report_progress(progress_callback, 5, "正在读取抓包文件...")
        with reader_cls(str(path)) as reader:
            for index, (packet_bytes, metadata) in enumerate(reader, start=1):
                ts_info = PcapUtils._extract_packet_timestamp_info(metadata, is_pcapng) or {}
                timestamp_text = cls._format_timestamp(ts_info.get("timestamp"))
                packets.append(cls._build_packet_record(index=index, raw_bytes=packet_bytes, timestamp_text=timestamp_text, source_hint="pcap"))

                if index == 1 or index % 100 == 0:
                    position = cls._reader_position(reader)
                    if position is not None:
                        progress = min(99, max(5, int((position / file_size) * 100)))
                        cls._report_progress(progress_callback, progress, f"正在导入抓包报文... 已读取 {index} 条")

        cls._report_progress(progress_callback, 100, f"抓包文件导入完成，共加载 {len(packets)} 条报文")
        return packets

    @classmethod
    def _stream_capture_packet_batches(
        cls,
        path: Path,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        initial_batch_size: Optional[int] = None,
        flush_interval_ms: int = DEFAULT_FLUSH_INTERVAL_MS,
    ):
        packets: List[Dict[str, Any]] = []
        total_loaded = 0
        is_pcapng = path.suffix.lower() == ".pcapng"
        file_size = max(path.stat().st_size, 1)
        current_batch_size, steady_batch_size, flush_interval_seconds = cls._resolve_batch_settings(
            batch_size,
            initial_batch_size,
            flush_interval_ms,
        )
        last_flush_time = time.perf_counter()

        if is_pcapng:
            from scapy.utils import RawPcapNgReader

            reader_cls = RawPcapNgReader
        else:
            from scapy.utils import RawPcapReader

            reader_cls = RawPcapReader

        cls._report_progress(progress_callback, 5, "正在读取抓包文件...")
        with reader_cls(str(path)) as reader:
            for index, (packet_bytes, metadata) in enumerate(reader, start=1):
                ts_info = PcapUtils._extract_packet_timestamp_info(metadata, is_pcapng) or {}
                timestamp_text = cls._format_timestamp(ts_info.get("timestamp"))
                packets.append(cls._build_packet_record(
                    index=index,
                    raw_bytes=packet_bytes,
                    timestamp_text=timestamp_text,
                    source_hint="pcap",
                ))
                total_loaded += 1
                if index == 1 or index % 100 == 0:
                    position = cls._reader_position(reader)
                    if position is not None:
                        progress = min(99, max(5, int((position / file_size) * 100)))
                        cls._report_progress(progress_callback, progress, f"正在导入抓包报文... 已读取 {index} 条")
                if cls._should_flush_batch(packets, current_batch_size, last_flush_time, flush_interval_seconds):
                    yield packets
                    packets = []
                    current_batch_size = steady_batch_size
                    last_flush_time = time.perf_counter()
        if packets:
            yield packets
        cls._report_progress(progress_callback, 100, f"抓包文件导入完成，共加载 {total_loaded} 条报文")

    @classmethod
    def _load_text_packets(
        cls,
        path: Path,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> List[Dict[str, Any]]:
        cls._report_progress(progress_callback, 5, "正在读取文本报文...")
        packets: List[Dict[str, Any]] = []
        file_size = max(path.stat().st_size, 1)
        encoding = cls._detect_text_encoding(path)

        with path.open("rb") as handle:
            for index, raw_line in enumerate(iter(handle.readline, b""), start=1):
                line = raw_line.decode(encoding, errors="ignore")
                raw_bytes = cls.extract_hex_bytes(line)
                if raw_bytes:
                    packets.append(cls._build_packet_record(len(packets) + 1, raw_bytes, "-", source_hint="text"))

                if index == 1 or index % 50 == 0:
                    progress = min(95, max(5, int((handle.tell() / file_size) * 100)))
                    cls._report_progress(progress_callback, progress, f"正在导入文本报文... 已扫描 {index} 行，加载 {len(packets)} 条")

        if packets:
            return packets

        cls._report_progress(progress_callback, 70, "正在尝试按整体十六进制块导入...")
        content = cls._read_text(path)
        raw_bytes = cls.extract_hex_bytes(content)
        if raw_bytes:
            return [cls._build_packet_record(1, raw_bytes, "-", source_hint="text")]

        cls._report_progress(progress_callback, 100, "未识别到可导入的文本报文")
        return []

    @classmethod
    def _stream_text_packet_batches(
        cls,
        path: Path,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        initial_batch_size: Optional[int] = None,
        flush_interval_ms: int = DEFAULT_FLUSH_INTERVAL_MS,
    ):
        cls._report_progress(progress_callback, 5, "正在读取文本报文...")
        packets: List[Dict[str, Any]] = []
        total_kept = 0
        file_size = max(path.stat().st_size, 1)
        encoding = cls._detect_text_encoding(path)
        current_batch_size, steady_batch_size, flush_interval_seconds = cls._resolve_batch_settings(
            batch_size,
            initial_batch_size,
            flush_interval_ms,
        )
        last_flush_time = time.perf_counter()

        with path.open("rb") as handle:
            for index, raw_line in enumerate(iter(handle.readline, b""), start=1):
                line = raw_line.decode(encoding, errors="ignore")
                raw_bytes = cls.extract_hex_bytes(line)
                if raw_bytes:
                    packets.append(cls._build_packet_record(total_kept + 1, raw_bytes, "-", source_hint="text"))
                    total_kept += 1

                if index == 1 or index % 50 == 0:
                    progress = min(95, max(5, int((handle.tell() / file_size) * 100)))
                    cls._report_progress(progress_callback, progress, f"正在解析文本报文... 已扫描 {index} 行，命中 {total_kept} 条")
                if cls._should_flush_batch(packets, current_batch_size, last_flush_time, flush_interval_seconds):
                    yield packets
                    packets = []
                    current_batch_size = steady_batch_size
                    last_flush_time = time.perf_counter()

        if total_kept:
            if packets:
                yield packets
            return

        cls._report_progress(progress_callback, 70, "正在尝试按整体十六进制块解析...")
        content = cls._read_text(path)
        raw_bytes = cls.extract_hex_bytes(content)
        if raw_bytes:
            yield [cls._build_packet_record(1, raw_bytes, "-", source_hint="text")]
            return
        cls._report_progress(progress_callback, 100, "未识别到可解析的文本报文")

    @staticmethod
    def _read_text(path: Path) -> str:
        for encoding in ("utf-8", "gbk", "latin-1"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        return path.read_text(encoding="utf-8", errors="ignore")

    @staticmethod
    def _detect_text_encoding(path: Path) -> str:
        sample = b""
        try:
            with path.open("rb") as handle:
                sample = handle.read(4096)
        except OSError:
            return "utf-8"

        for encoding in ("utf-8", "gbk", "latin-1"):
            try:
                sample.decode(encoding)
                return encoding
            except UnicodeDecodeError:
                continue
        return "utf-8"

    @staticmethod
    def extract_hex_bytes(content: str) -> bytes:
        if not content:
            return b""

        no_prefix = re.sub(r"0x", "", content, flags=re.IGNORECASE)
        byte_tokens = re.findall(r"\b[0-9A-Fa-f]{2}\b", no_prefix)
        if len(byte_tokens) >= 4:
            try:
                return bytes.fromhex("".join(byte_tokens))
            except ValueError:
                pass

        compact = re.sub(r"[^0-9A-Fa-f]", "", no_prefix)
        if len(compact) >= 8 and len(compact) % 2 == 0:
            try:
                return bytes.fromhex(compact)
            except ValueError:
                return b""
        return b""

    @classmethod
    def _build_packet_record(
        cls,
        index: int,
        raw_bytes: bytes,
        timestamp_text: str,
        source_hint: str = "raw",
    ) -> Dict[str, Any]:
        summary_info = cls.summarize_packet(raw_bytes, source_hint=source_hint)
        return {
            "no": index,
            "timestamp": timestamp_text or "-",
            "source": summary_info.get("source", "-"),
            "destination": summary_info.get("destination", "-"),
            "protocol": summary_info.get("protocol", "RAW"),
            "length": len(raw_bytes),
            "summary": summary_info.get("summary", f"Raw Payload ({len(raw_bytes)} bytes)"),
            "raw_bytes": raw_bytes,
            "analysis": None,
            "_analysis_ready": False,
        }

    @classmethod
    def summarize_packet(cls, raw_bytes: bytes, source_hint: str = "raw") -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "source": "-",
            "destination": "-",
            "protocol": "RAW",
            "summary": f"Raw Payload ({len(raw_bytes)} bytes)",
        }

        context = cls._extract_packet_context(raw_bytes)
        summary["source"] = context["source"]
        summary["destination"] = context["destination"]
        payload = context["payload"]
        transport_protocol = context["transport_protocol"]

        if len(payload) >= 16 and payload[:4] == b"\xFF\xFF\x81\x00":
            summary["protocol"] = "SOME/IP-SD"
            summary["summary"] = cls._summarize_someip_sd(payload)
            return summary

        if len(payload) >= 16:
            service_id = f"0x{int.from_bytes(payload[0:2], 'big'):04X}"
            method_id = f"0x{int.from_bytes(payload[2:4], 'big'):04X}"
            length = int.from_bytes(payload[4:8], "big")
            payload_length = max(0, min(len(payload) - 16, length - 8))
            summary["protocol"] = "SOME/IP"
            summary["summary"] = f"SOME/IP {service_id}/{method_id}, Length: {payload_length}"
            return summary

        if transport_protocol != "RAW":
            summary["protocol"] = transport_protocol
            summary["summary"] = f"{transport_protocol} Payload ({len(payload)} bytes)"
        return summary

    @classmethod
    def ensure_packet_analysis(cls, packet: Dict[str, Any]) -> Dict[str, Any]:
        if packet.get("_analysis_ready") and isinstance(packet.get("analysis"), dict):
            return cast(Dict[str, Any], packet["analysis"])

        analysis = cls.analyze_packet(packet.get("raw_bytes", b""))
        packet["analysis"] = analysis
        packet["_analysis_ready"] = True
        packet["source"] = analysis.get("source", packet.get("source", "-"))
        packet["destination"] = analysis.get("destination", packet.get("destination", "-"))
        packet["protocol"] = analysis.get("protocol", packet.get("protocol", "RAW"))
        return analysis

    @classmethod
    def analyze_packet(cls, raw_bytes: bytes, source_hint: str = "raw") -> Dict[str, Any]:
        analysis: Dict[str, Any] = {
            "source": "-",
            "destination": "-",
            "protocol": "RAW",
            "matrix_hit": False,
            "matrix_label": "-",
            "summary": f"Raw Payload ({len(raw_bytes)} bytes)",
            "nodes": [],
            "data_text": cls.format_hex_dump(raw_bytes),
        }

        if not raw_bytes:
            analysis["nodes"] = [
                cls._node("Frame", "0 bytes", 0, 0, "空报文")
            ]
            return analysis

        nodes: List[Dict[str, Any]] = []
        context = cls._extract_packet_context(raw_bytes)
        payload_offset = context["payload_offset"]
        payload_bytes = context["payload"]
        src_endpoint = context["source"]
        dst_endpoint = context["destination"]
        transport_protocol = context["transport_protocol"]
        analysis["source"] = src_endpoint
        analysis["destination"] = dst_endpoint

        app_result = cls._parse_application_payload(payload_bytes, payload_offset, src_endpoint, dst_endpoint, transport_protocol)
        if app_result["nodes"]:
            nodes.extend(app_result["nodes"])
            analysis["protocol"] = app_result["protocol"]
            analysis["summary"] = app_result["summary"]
            analysis["matrix_hit"] = bool(app_result.get("matrix_hit", False))
            analysis["matrix_label"] = app_result.get("matrix_label", analysis["matrix_label"])
            analysis["data_text"] = app_result.get("data_text", analysis["data_text"])
        else:
            nodes.append(cls._node("原始数据", cls._format_preview(payload_bytes), payload_offset, len(payload_bytes), "未识别到矩阵结构"))
            if transport_protocol != "RAW":
                analysis["protocol"] = transport_protocol
                analysis["summary"] = f"{transport_protocol} Payload ({len(payload_bytes)} bytes)"

        analysis["nodes"] = nodes
        if analysis["source"] == "-":
            analysis["source"] = src_endpoint
        if analysis["destination"] == "-":
            analysis["destination"] = dst_endpoint
        return analysis

    @staticmethod
    def _looks_like_ethernet_frame(raw_bytes: bytes) -> bool:
        if len(raw_bytes) < 14:
            return False
        ether_type = int.from_bytes(raw_bytes[12:14], "big")
        return ether_type in {0x0800, 0x86DD, 0x8100, 0x88A8}

    @classmethod
    def _parse_ethernet(cls, raw_bytes: bytes) -> Dict[str, Any]:
        eth_len = 14
        ether_type = int.from_bytes(raw_bytes[12:14], "big")
        children = [
            cls._node("Destination MAC", cls._format_mac(raw_bytes[0:6]), 0, 6, "目的 MAC 地址"),
            cls._node("Source MAC", cls._format_mac(raw_bytes[6:12]), 6, 6, "源 MAC 地址"),
        ]

        if ether_type == 0x8100 and len(raw_bytes) >= 18:
            vlan_tci = int.from_bytes(raw_bytes[14:16], "big")
            ether_type = int.from_bytes(raw_bytes[16:18], "big")
            eth_len = 18
            children.append(cls._node("VLAN TCI", f"0x{vlan_tci:04X}", 14, 2, "VLAN 标签控制信息"))
            children.append(cls._node("Inner EtherType", f"0x{ether_type:04X}", 16, 2, "内层 EtherType"))
        else:
            children.append(cls._node("EtherType", f"0x{ether_type:04X}", 12, 2, "链路层协议类型"))

        return {
            "node": cls._node("Ethernet II", "", 0, eth_len, "以太网头", children),
            "ether_type": ether_type,
            "src_mac": cls._format_mac(raw_bytes[6:12]),
            "dst_mac": cls._format_mac(raw_bytes[0:6]),
            "next_offset": eth_len,
        }

    @classmethod
    def _parse_ipv4(cls, raw_bytes: bytes, offset: int) -> Optional[Dict[str, Any]]:
        if len(raw_bytes) < offset + 20:
            return None
        version_ihl = raw_bytes[offset]
        ihl = (version_ihl & 0x0F) * 4
        if ihl < 20 or len(raw_bytes) < offset + ihl:
            return None

        src_ip = ".".join(str(part) for part in raw_bytes[offset + 12:offset + 16])
        dst_ip = ".".join(str(part) for part in raw_bytes[offset + 16:offset + 20])
        protocol_number = raw_bytes[offset + 9]
        total_length = int.from_bytes(raw_bytes[offset + 2:offset + 4], "big")
        ttl = raw_bytes[offset + 8]

        node = cls._node(
            "IPv4",
            "",
            offset,
            ihl,
            "IPv4 头部",
            [
                cls._node("Header Length", f"{ihl} bytes", offset, 1, "IPv4 头长度"),
                cls._node("Total Length", str(total_length), offset + 2, 2, "IP 总长度"),
                cls._node("TTL", str(ttl), offset + 8, 1, "生存时间"),
                cls._node("Protocol", cls._ip_protocol_name(protocol_number), offset + 9, 1, "上层协议号"),
                cls._node("Source", src_ip, offset + 12, 4, "源 IP 地址"),
                cls._node("Destination", dst_ip, offset + 16, 4, "目的 IP 地址"),
            ],
        )
        return {
            "node": node,
            "source": src_ip,
            "destination": dst_ip,
            "protocol_number": protocol_number,
            "next_offset": offset + ihl,
        }

    @classmethod
    def _parse_ipv6(cls, raw_bytes: bytes, offset: int) -> Optional[Dict[str, Any]]:
        if len(raw_bytes) < offset + 40:
            return None

        next_header = raw_bytes[offset + 6]
        payload_length = int.from_bytes(raw_bytes[offset + 4:offset + 6], "big")
        src = raw_bytes[offset + 8:offset + 24]
        dst = raw_bytes[offset + 24:offset + 40]
        src_ip = cls._format_ipv6(src)
        dst_ip = cls._format_ipv6(dst)
        node = cls._node(
            "IPv6",
            "",
            offset,
            40,
            "IPv6 头部",
            [
                cls._node("Payload Length", str(payload_length), offset + 4, 2, "IPv6 负载长度"),
                cls._node("Next Header", cls._ip_protocol_name(next_header), offset + 6, 1, "下一头部协议"),
                cls._node("Source", src_ip, offset + 8, 16, "源 IPv6 地址"),
                cls._node("Destination", dst_ip, offset + 24, 16, "目的 IPv6 地址"),
            ],
        )
        return {
            "node": node,
            "source": src_ip,
            "destination": dst_ip,
            "protocol_number": next_header,
            "next_offset": offset + 40,
        }

    @classmethod
    def _parse_udp(cls, raw_bytes: bytes, offset: int, src_ip: str, dst_ip: str) -> Dict[str, Any]:
        if len(raw_bytes) < offset + 8:
            return {
                "node": cls._node("UDP", "Truncated", offset, max(0, len(raw_bytes) - offset), "UDP 头部不完整"),
                "source": src_ip,
                "destination": dst_ip,
                "payload_offset": len(raw_bytes),
            }

        src_port = int.from_bytes(raw_bytes[offset:offset + 2], "big")
        dst_port = int.from_bytes(raw_bytes[offset + 2:offset + 4], "big")
        length = int.from_bytes(raw_bytes[offset + 4:offset + 6], "big")
        node = cls._node(
            "UDP",
            "",
            offset,
            8,
            "UDP 头部",
            [
                cls._node("Source Port", str(src_port), offset, 2, "源端口"),
                cls._node("Destination Port", str(dst_port), offset + 2, 2, "目的端口"),
                cls._node("Length", str(length), offset + 4, 2, "UDP 长度字段"),
            ],
        )
        return {
            "node": node,
            "source": f"{src_ip}:{src_port}",
            "destination": f"{dst_ip}:{dst_port}",
            "payload_offset": offset + 8,
        }

    @classmethod
    def _parse_tcp(cls, raw_bytes: bytes, offset: int, src_ip: str, dst_ip: str) -> Dict[str, Any]:
        if len(raw_bytes) < offset + 20:
            return {
                "node": cls._node("TCP", "Truncated", offset, max(0, len(raw_bytes) - offset), "TCP 头部不完整"),
                "source": src_ip,
                "destination": dst_ip,
                "payload_offset": len(raw_bytes),
            }

        src_port = int.from_bytes(raw_bytes[offset:offset + 2], "big")
        dst_port = int.from_bytes(raw_bytes[offset + 2:offset + 4], "big")
        seq = int.from_bytes(raw_bytes[offset + 4:offset + 8], "big")
        ack = int.from_bytes(raw_bytes[offset + 8:offset + 12], "big")
        data_offset = ((raw_bytes[offset + 12] >> 4) & 0x0F) * 4
        node = cls._node(
            "TCP",
            "",
            offset,
            data_offset,
            "TCP 头部",
            [
                cls._node("Source Port", str(src_port), offset, 2, "源端口"),
                cls._node("Destination Port", str(dst_port), offset + 2, 2, "目的端口"),
                cls._node("Sequence Number", str(seq), offset + 4, 4, "序列号"),
                cls._node("Acknowledgment Number", str(ack), offset + 8, 4, "确认号"),
                cls._node("Header Length", f"{data_offset} bytes", offset + 12, 1, "TCP 头长度"),
            ],
        )
        return {
            "node": node,
            "source": f"{src_ip}:{src_port}",
            "destination": f"{dst_ip}:{dst_port}",
            "payload_offset": offset + max(data_offset, 20),
        }

    @classmethod
    def _parse_application_payload(
        cls,
        payload: bytes,
        payload_offset: int,
        source: str,
        destination: str,
        transport_protocol: str,
    ) -> Dict[str, Any]:
        if not payload:
            return {
                "protocol": transport_protocol,
                "summary": f"{transport_protocol} Empty Payload",
                "nodes": [cls._node("Payload", "<empty>", payload_offset, 0, "空负载")],
            }

        if len(payload) >= 16 and payload[:4] == b"\xFF\xFF\x81\x00":
            return cls._parse_someip_sd(payload, payload_offset, source, destination)

        if len(payload) >= 16:
            someip_result = cls._parse_someip(payload, payload_offset, source, destination)
            if someip_result["nodes"]:
                return someip_result

        preview = cls._format_preview(payload)
        return {
            "protocol": transport_protocol if transport_protocol != "RAW" else "RAW",
            "summary": f"{transport_protocol if transport_protocol != 'RAW' else 'Raw'} Payload {preview}",
            "nodes": [],
            "data_text": cls.format_hex_dump(payload),
        }

    @classmethod
    def _parse_someip(
        cls,
        payload: bytes,
        base_offset: int,
        source: str,
        destination: str,
    ) -> Dict[str, Any]:
        service_id = f"0x{int.from_bytes(payload[0:2], 'big'):04X}"
        method_id = f"0x{int.from_bytes(payload[2:4], 'big'):04X}"
        length = int.from_bytes(payload[4:8], "big")
        client_id = f"0x{int.from_bytes(payload[8:10], 'big'):04X}"
        session_id = f"0x{int.from_bytes(payload[10:12], 'big'):04X}"
        interface_version = payload[13]
        message_type = payload[14]
        return_code = payload[15]
        payload_bytes = payload[16:16 + max(0, min(len(payload) - 16, length - 8))]

        matrix_info = cls._resolve_matrix_info(service_id)
        payload_rules = get_payload_rules(service_id, method_id, message_type=message_type)
        service_name = "未匹配矩阵服务"
        
        if payload_rules:
            service_name = next((rule.get("service_interface_name") for rule in payload_rules if rule.get("service_interface_name")), None) or service_name
        if service_name == "未匹配矩阵服务" and matrix_info:
            service_name = matrix_info.get("service_interface_name") or "未匹配矩阵服务"

        method_name = next((rule.get("method_name") for rule in payload_rules if rule.get("method_name")), method_id)
        matrix_hit = bool(matrix_info or payload_rules)
        matrix_label = "字段已解析" if payload_rules else ("服务命中" if matrix_info else "未命中")

        payload_nodes, payload_text = cls._decode_payload_by_rules(payload_bytes, payload_rules, base_offset + 16)
        if not payload_nodes:
            payload_nodes = [
                cls._node(
                    "Payload",
                    cls._format_preview(payload_bytes),
                    base_offset + 16,
                    len(payload_bytes),
                    "SOME/IP 载荷数据",
                    data_text=cls.format_hex_dump(payload_bytes),
                ),
            ]

        root_title = f"{'✅' if matrix_hit else '❌'} {service_name}"
        info_lines = [
            ("矩阵状态", matrix_label),
            ("服务接口", service_name),
            ("Service ID", service_id),
            ("Method", method_name),
            ("Method ID", method_id),
            ("Source", source),
            ("Destination", destination),
        ]
        if payload_text:
            info_lines.append(("Payload 解析", "见下方字段"))

        nodes = [
            cls._node(
                root_title,
                method_name,
                description="矩阵中匹配到的服务接口",
                data_text=cls._build_text_block(info_lines + ([('解析结果', payload_text)] if payload_text else [])),
                children=[
                    cls._node("矩阵状态", matrix_label, description="当前报文是否命中矩阵"),
                    cls._node("方法", method_name, description="矩阵中的方法/事件名称"),
                    cls._node(
                        "Payload结构",
                        f"{len(payload_nodes)} 个字段",
                        description="按矩阵规则解析的 payload 字段",
                        children=payload_nodes,
                    ),
                ],
            )
        ]

        return {
            "protocol": "SOME/IP",
            "summary": f"{'[矩阵]' if matrix_hit else '[原始]'} {service_name} {method_id} ({len(payload_bytes)} bytes)",
            "matrix_hit": matrix_hit,
            "matrix_label": matrix_label,
            "nodes": nodes,
            "data_text": payload_text or cls.format_hex_dump(payload_bytes),
        }

    @classmethod
    def _parse_someip_sd(
        cls,
        payload: bytes,
        base_offset: int,
        source: str,
        destination: str,
    ) -> Dict[str, Any]:
        message_id = int.from_bytes(payload[0:4], "big")
        length = int.from_bytes(payload[4:8], "big")
        request_id = int.from_bytes(payload[8:12], "big")
        protocol_version = payload[12]
        interface_version = payload[13]
        message_type = payload[14]
        return_code = payload[15]

        children = [
            cls._node("Message ID", f"0x{message_id:08X}", base_offset, 4, "SOME/IP Message ID"),
            cls._node("Length", str(length), base_offset + 4, 4, "SOME/IP 长度字段"),
            cls._node("Request ID", f"0x{request_id:08X}", base_offset + 8, 4, "请求 ID"),
            cls._node("Protocol Version", str(protocol_version), base_offset + 12, 1, "协议版本"),
            cls._node("Interface Version", str(interface_version), base_offset + 13, 1, "接口版本"),
            cls._node("Message Type", f"0x{message_type:02X}", base_offset + 14, 1, "消息类型"),
            cls._node("Return Code", f"0x{return_code:02X}", base_offset + 15, 1, "返回码"),
        ]
        someip_node = cls._node("SOME/IP Header", "", base_offset, 16, "SOME/IP 报文头", children)

        sd_nodes: List[Dict[str, Any]] = []
        summary = f"SOME/IP-SD {source} → {destination}"
        if len(payload) >= 24:
            flags = payload[16]
            entries_len = int.from_bytes(payload[20:24], "big")
            entries_start = 24
            entries_end = min(entries_start + entries_len, len(payload))
            entries_bytes = payload[entries_start:entries_end]
            options_len_offset = entries_end
            options_len = 0
            options_bytes = b""
            if len(payload) >= options_len_offset + 4:
                options_len = int.from_bytes(payload[options_len_offset:options_len_offset + 4], "big")
                options_start = options_len_offset + 4
                options_end = min(options_start + options_len, len(payload))
                options_bytes = payload[options_start:options_end]
            else:
                options_start = options_len_offset + 4

            options_map = PcapUtils._parse_sd_options(options_bytes)
            entries = PcapUtils._parse_sd_entries(entries_bytes, options_map)

            entries_node = cls._node(
                "Entries",
                str(len(entries)),
                base_offset + entries_start,
                len(entries_bytes),
                "服务发现条目列表",
                [cls._build_sd_entry_node(entry, idx, base_offset + entries_start + idx * 16) for idx, entry in enumerate(entries, start=0)],
            )
            options_node = cls._node(
                "Options",
                str(len(options_map)),
                base_offset + options_start,
                len(options_bytes),
                "SOME/IP-SD 选项列表",
                [cls._build_sd_option_node(option, idx, base_offset + options_start) for idx, option in options_map.items()],
            )
            sd_nodes.append(
                cls._node(
                    "SOME/IP-SD",
                    "",
                    base_offset + 16,
                    max(0, len(payload) - 16),
                    "SOME/IP Service Discovery 负载",
                    [
                        cls._node("Flags", f"0x{flags:02X}", base_offset + 16, 1, "SD Flags"),
                        cls._node("Entries Length", str(entries_len), base_offset + 20, 4, "Entries 区段长度"),
                        entries_node,
                        cls._node("Options Length", str(options_len), base_offset + options_len_offset, 4, "Options 区段长度"),
                        options_node,
                    ],
                )
            )
            if entries:
                first_entry = entries[0]
                summary = (
                    f"{first_entry.get('entry_type_name', 'SOME/IP-SD')} "
                    f"{first_entry.get('service_id', '-')}/{first_entry.get('instance_id', '-')}"
                )
                endpoint = first_entry.get("endpoint")
                if endpoint:
                    summary = f"{summary} -> {endpoint}"
                if len(entries) > 1:
                    summary = f"{summary} (+{len(entries) - 1})"

        return {
            "protocol": "SOME/IP-SD",
            "summary": summary,
            "matrix_hit": False,
            "matrix_label": "SD",
            "nodes": cls._build_sd_matrix_nodes(sd_nodes, summary),
            "data_text": cls.format_hex_dump(payload),
        }

    @classmethod
    def build_tree_nodes(cls, packet: Dict[str, Any]) -> List[Dict[str, Any]]:
        analysis = cls.ensure_packet_analysis(packet)
        return list(analysis.get("nodes", []))

    @classmethod
    def packet_data_text(cls, packet: Dict[str, Any]) -> str:
        analysis = cls.ensure_packet_analysis(packet)
        text = analysis.get("data_text")
        if text:
            return str(text)
        return cls.format_hex_dump(packet.get("raw_bytes", b""))

    @classmethod
    def packet_properties(cls, packet: Dict[str, Any]) -> List[Tuple[str, str]]:
        return [
            ("序号", str(packet.get("no", "-"))),
            ("时间戳", str(packet.get("timestamp", "-"))),
            ("源", str(packet.get("source", "-"))),
            ("目的", str(packet.get("destination", "-"))),
            ("协议", str(packet.get("protocol", "-"))),
            ("长度", f"{packet.get('length', 0)} bytes"),
            ("摘要", str(packet.get("summary", "-"))),
        ]

    @staticmethod
    def node_properties(node: Dict[str, Any]) -> List[Tuple[str, str]]:
        offset = node.get("offset")
        length = node.get("length")
        return [
            ("字段", str(node.get("field", "-"))),
            ("值", str(node.get("value", "-"))),
            ("偏移", "-" if offset is None else f"0x{int(offset):04X} ({int(offset)})"),
            ("长度", "-" if length is None else f"{int(length)} bytes"),
            ("说明", str(node.get("description", "-"))),
        ]

    @staticmethod
    def node_data_text(node: Dict[str, Any]) -> str:
        if not node:
            return ""
        if node.get("data_text"):
            return str(node.get("data_text"))
        return "\n".join([
            f"字段: {node.get('field', '-')}",
            f"值: {node.get('value', '-')}",
            f"说明: {node.get('description', '-')}",
        ])

    @staticmethod
    def format_hex_dump(raw_bytes: bytes, width: int = 16) -> str:
        if not raw_bytes:
            return ""

        lines: List[str] = []
        for offset in range(0, len(raw_bytes), width):
            chunk = raw_bytes[offset:offset + width]
            hex_part = " ".join(f"{byte:02X}" for byte in chunk)
            ascii_part = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
            lines.append(f"{offset:04X}  {hex_part:<{width * 3 - 1}}  {ascii_part}")
        return "\n".join(lines)

    @staticmethod
    def _format_timestamp(timestamp: Optional[float]) -> str:
        if timestamp in (None, ""):
            return "-"
        try:
            return datetime.fromtimestamp(float(timestamp)).strftime("%Y-%m-%d %H:%M:%S.%f")
        except (TypeError, ValueError, OSError, OverflowError):
            return "-"

    @staticmethod
    def _format_mac(raw_mac: bytes) -> str:
        return ":".join(f"{byte:02X}" for byte in raw_mac)

    @staticmethod
    def _format_ipv6(raw_ip: bytes) -> str:
        groups = [f"{int.from_bytes(raw_ip[i:i + 2], 'big'):x}" for i in range(0, 16, 2)]
        return ":".join(groups)

    @staticmethod
    def _format_preview(payload: bytes, limit: int = 24) -> str:
        if not payload:
            return "<empty>"
        preview = " ".join(f"{byte:02X}" for byte in payload[:limit])
        if len(payload) > limit:
            preview += " ..."
        return preview

    @staticmethod
    def _ip_protocol_name(protocol_number: int) -> str:
        mapping = {
            6: "TCP",
            17: "UDP",
            1: "ICMP",
            58: "ICMPv6",
        }
        return mapping.get(protocol_number, f"Unknown({protocol_number})")

    @classmethod
    def _build_sd_entry_node(cls, entry: Dict[str, Any], index: int, offset: int) -> Dict[str, Any]:
        children = [
            cls._node("Entry Type", entry.get("entry_type_name", "-"), offset, 1, "服务发现条目类型"),
            cls._node("Service ID", entry.get("service_id", "-"), offset + 4, 2, "服务 ID"),
            cls._node("Instance ID", entry.get("instance_id", "-"), offset + 6, 2, "实例 ID"),
            cls._node("Version", entry.get("version", "-"), offset + 8, 4, "主/次版本"),
            cls._node("TTL", str(entry.get("ttl", "-")), offset + 9, 3, "生存时间"),
        ]
        if entry.get("endpoint"):
            children.append(cls._node("Endpoint", entry.get("endpoint", "-"), description="服务端点"))
        if entry.get("eventgroup_id"):
            children.append(cls._node("Event Group ID", entry.get("eventgroup_id", "-"), description="事件组 ID"))
        if entry.get("config_texts"):
            for text in entry.get("config_texts", []):
                children.append(cls._node("Configuration", text, description="配置字符串"))

        return cls._node(
            f"Entry[{index + 1}]",
            entry.get("entry_type_name", "-"),
            offset,
            16,
            "SOME/IP-SD Entry",
            children,
        )

    @classmethod
    def _build_sd_option_node(cls, option: Dict[str, Any], index: int, offset: int) -> Dict[str, Any]:
        children = [
            cls._node("Type", option.get("type", "Unknown"), description="选项类型"),
        ]
        if option.get("ip"):
            children.append(cls._node("IP", str(option.get("ip")), description="选项中的 IP 地址"))
        if option.get("port") not in (None, ""):
            children.append(cls._node("Port", str(option.get("port")), description="选项中的端口号"))
        if option.get("l4_proto"):
            children.append(cls._node("L4 Proto", str(option.get("l4_proto")), description="传输层协议"))
        for text in option.get("text", []) or []:
            children.append(cls._node("Text", text, description="配置文本"))

        return cls._node(
            f"Option[{index + 1}]",
            option.get("type", "Unknown"),
            offset,
            None,
            "SOME/IP-SD Option",
            children,
        )

    @classmethod
    def _build_sd_matrix_nodes(cls, sd_nodes: List[Dict[str, Any]], summary: str) -> List[Dict[str, Any]]:
        if not sd_nodes:
            return [cls._node("SOME/IP-SD", summary, description="未解析到可展示的矩阵结构", data_text=summary)]
        return [
            cls._node(
                "服务发现结构",
                summary,
                description="基于 SOME/IP-SD 提取的结构体信息",
                data_text=summary,
                children=sd_nodes,
            )
        ]

    @classmethod
    def _resolve_matrix_info(cls, service_id: str) -> Optional[Dict[str, Any]]:
        try:
            cache = import_someip_matrix()
        except Exception:
            return None

        fingerprint = None
        if isinstance(cache, dict):
            raw_fingerprint = cache.get("fingerprint")
            if isinstance(raw_fingerprint, dict):
                fingerprint = (raw_fingerprint.get("mtime"), raw_fingerprint.get("size"))

        if cls._matrix_service_index is None or cls._matrix_fingerprint != fingerprint:
            services = cache.get("services", {}) if isinstance(cache, dict) else {}
            cls._matrix_service_index = {}
            for item in services.values():
                if isinstance(item, dict) and item.get("service_id"):
                    cls._matrix_service_index[str(item.get("service_id"))] = item
            cls._matrix_fingerprint = fingerprint

        if cls._matrix_service_index and service_id in cls._matrix_service_index:
            return cls._matrix_service_index[service_id]

        try:
            return get_service_info(service_id, "")
        except Exception:
            return None

    @classmethod
    def _extract_packet_context(cls, raw_bytes: bytes) -> Dict[str, Any]:
        payload_offset = 0
        payload_bytes = raw_bytes
        src_endpoint = "-"
        dst_endpoint = "-"
        transport_protocol = "RAW"

        if cls._looks_like_ethernet_frame(raw_bytes):
            src_endpoint = cls._format_mac(raw_bytes[6:12])
            dst_endpoint = cls._format_mac(raw_bytes[0:6])
            ether_type = int.from_bytes(raw_bytes[12:14], "big")
            offset = 14

            if ether_type in {0x8100, 0x88A8} and len(raw_bytes) >= 18:
                ether_type = int.from_bytes(raw_bytes[16:18], "big")
                offset = 18

            payload_offset = offset

            if ether_type == 0x0800 and len(raw_bytes) >= offset + 20:
                version_ihl = raw_bytes[offset]
                ihl = (version_ihl & 0x0F) * 4
                if ihl >= 20 and len(raw_bytes) >= offset + ihl:
                    src_endpoint = ".".join(str(part) for part in raw_bytes[offset + 12:offset + 16])
                    dst_endpoint = ".".join(str(part) for part in raw_bytes[offset + 16:offset + 20])
                    protocol_number = raw_bytes[offset + 9]
                    payload_offset = offset + ihl

                    if protocol_number == 17 and len(raw_bytes) >= payload_offset + 8:
                        src_port = int.from_bytes(raw_bytes[payload_offset:payload_offset + 2], "big")
                        dst_port = int.from_bytes(raw_bytes[payload_offset + 2:payload_offset + 4], "big")
                        src_endpoint = f"{src_endpoint}:{src_port}"
                        dst_endpoint = f"{dst_endpoint}:{dst_port}"
                        payload_offset += 8
                        transport_protocol = "UDP"
                    elif protocol_number == 6 and len(raw_bytes) >= payload_offset + 20:
                        src_port = int.from_bytes(raw_bytes[payload_offset:payload_offset + 2], "big")
                        dst_port = int.from_bytes(raw_bytes[payload_offset + 2:payload_offset + 4], "big")
                        header_length = ((raw_bytes[payload_offset + 12] >> 4) & 0x0F) * 4
                        src_endpoint = f"{src_endpoint}:{src_port}"
                        dst_endpoint = f"{dst_endpoint}:{dst_port}"
                        payload_offset += max(header_length, 20)
                        transport_protocol = "TCP"
                    else:
                        transport_protocol = f"IP-{protocol_number}"

                    payload_offset = min(payload_offset, len(raw_bytes))
                    payload_bytes = raw_bytes[payload_offset:]
            elif ether_type == 0x86DD and len(raw_bytes) >= offset + 40:
                next_header = raw_bytes[offset + 6]
                src_endpoint = cls._format_ipv6(raw_bytes[offset + 8:offset + 24])
                dst_endpoint = cls._format_ipv6(raw_bytes[offset + 24:offset + 40])
                payload_offset = offset + 40

                if next_header == 17 and len(raw_bytes) >= payload_offset + 8:
                    src_port = int.from_bytes(raw_bytes[payload_offset:payload_offset + 2], "big")
                    dst_port = int.from_bytes(raw_bytes[payload_offset + 2:payload_offset + 4], "big")
                    src_endpoint = f"{src_endpoint}:{src_port}"
                    dst_endpoint = f"{dst_endpoint}:{dst_port}"
                    payload_offset += 8
                    transport_protocol = "UDP"
                elif next_header == 6 and len(raw_bytes) >= payload_offset + 20:
                    src_port = int.from_bytes(raw_bytes[payload_offset:payload_offset + 2], "big")
                    dst_port = int.from_bytes(raw_bytes[payload_offset + 2:payload_offset + 4], "big")
                    header_length = ((raw_bytes[payload_offset + 12] >> 4) & 0x0F) * 4
                    src_endpoint = f"{src_endpoint}:{src_port}"
                    dst_endpoint = f"{dst_endpoint}:{dst_port}"
                    payload_offset += max(header_length, 20)
                    transport_protocol = "TCP"
                else:
                    transport_protocol = f"IP-{next_header}"

                payload_offset = min(payload_offset, len(raw_bytes))
                payload_bytes = raw_bytes[payload_offset:]
            else:
                payload_bytes = raw_bytes[offset:]
                transport_protocol = "Ethernet"

        return {
            "payload_offset": payload_offset,
            "payload": payload_bytes,
            "source": src_endpoint,
            "destination": dst_endpoint,
            "transport_protocol": transport_protocol,
        }

    @classmethod
    def _summarize_someip_sd(cls, payload: bytes) -> str:
        if len(payload) < 24:
            return "SOME/IP-SD"
        try:
            entries_len = int.from_bytes(payload[20:24], "big")
            entries_start = 24
            entries_end = min(entries_start + entries_len, len(payload))
            entries_bytes = payload[entries_start:entries_end]

            options_bytes = b""
            if len(payload) >= entries_end + 4:
                options_len = int.from_bytes(payload[entries_end:entries_end + 4], "big")
                options_start = entries_end + 4
                options_end = min(options_start + options_len, len(payload))
                options_bytes = payload[options_start:options_end]

            options_map = PcapUtils._parse_sd_options(options_bytes)
            entries = PcapUtils._parse_sd_entries(entries_bytes, options_map)
            if entries:
                first_entry = entries[0]
                summary = f"{first_entry.get('entry_type_name', 'SOME/IP-SD')} {first_entry.get('service_id', '-')}/{first_entry.get('instance_id', '-')}"
                if len(entries) > 1:
                    summary += f" (+{len(entries) - 1})"
                return summary
        except Exception:
            pass
        return "SOME/IP-SD"

    @staticmethod
    def _build_text_block(items: List[Tuple[str, Any]]) -> str:
        return "\n".join(f"{key}: {value}" for key, value in items)

    @classmethod
    def _decode_payload_by_rules(
        cls,
        payload: bytes,
        rules: List[Dict[str, Any]],
        base_offset: int,
    ) -> Tuple[List[Dict[str, Any]], str]:
        if not rules:
            return [], ""

        if any("schema" in rule for rule in rules):
            return cls._decode_payload_by_schema_rules(payload, rules, base_offset)

        nodes: List[Dict[str, Any]] = []
        lines: List[str] = []
        for rule in rules:
            field_name = str(rule.get("field_name") or "UnnamedField")
            byte_offset = int(rule.get("byte_offset", 0) or 0)
            bit_offset = int(rule.get("bit_offset", 0) or 0)
            bit_length = int(rule.get("bit_length", 8) or 8)
            value_text, raw_hex = cls._decode_rule_value(payload, byte_offset, bit_offset, bit_length, rule)
            description = str(rule.get("data_type") or "")
            method_name = str(rule.get("method_name") or "")
            if method_name:
                description = f"{method_name} / {description}" if description else method_name
            nodes.append(
                cls._node(
                    field_name,
                    value_text,
                    base_offset + byte_offset,
                    max(1, (bit_length + 7) // 8),
                    description,
                    data_text=cls._build_text_block([
                        ("字段", field_name),
                        ("值", value_text),
                        ("原始", raw_hex),
                        ("类型", rule.get("data_type", "")),
                        ("单位", rule.get("unit", "")),
                        ("字节偏移", byte_offset),
                        ("位偏移", bit_offset),
                        ("位长度", bit_length),
                    ]),
                )
            )
            lines.append(f"{field_name}: {value_text} (raw={raw_hex})")
        return nodes, "\n".join(lines)

    @classmethod
    def _decode_payload_by_schema_rules(
        cls,
        payload: bytes,
        rules: List[Dict[str, Any]],
        base_offset: int,
    ) -> Tuple[List[Dict[str, Any]], str]:
        nodes: List[Dict[str, Any]] = []
        lines: List[str] = []
        cursor = 0

        for index, rule in enumerate(rules, start=1):
            field_name = str(rule.get("field_name") or f"Param{index}")
            schema = rule.get("schema") if isinstance(rule.get("schema"), dict) else {}
            node, next_cursor, field_lines = cls._decode_schema_field(
                payload,
                cursor,
                schema,
                field_name,
                base_offset,
                rule,
            )
            nodes.append(node)
            lines.extend(field_lines)
            if next_cursor <= cursor:
                next_cursor = len(payload)
            cursor = min(len(payload), next_cursor)

        if cursor < len(payload):
            remaining = payload[cursor:]
            nodes.append(
                cls._node(
                    "RemainingPayload",
                    cls._format_preview(remaining),
                    base_offset + cursor,
                    len(remaining),
                    "未被矩阵字段覆盖的剩余载荷",
                    data_text=cls.format_hex_dump(remaining),
                )
            )
            lines.append(f"RemainingPayload: {cls._format_preview(remaining)}")

        return nodes, "\n".join(lines)

    @classmethod
    def _decode_schema_field(
        cls,
        payload: bytes,
        cursor: int,
        schema: Dict[str, Any],
        field_name: str,
        base_offset: int,
        rule: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], int, List[str]]:
        schema = schema if isinstance(schema, dict) else {}
        category = str(schema.get("category") or "primitive").strip().lower()
        description_parts = [str(rule.get("parameter_description") or "").strip(), str(schema.get("description") or "").strip()]
        data_type_name = str(rule.get("data_type") or schema.get("type_name") or schema.get("data_type") or "").strip()
        if data_type_name:
            description_parts.append(data_type_name)
        description = " / ".join(part for part in description_parts if part)

        if category == "struct":
            return cls._decode_struct_schema(payload, cursor, schema, field_name, description, base_offset)
        if category == "array":
            return cls._decode_array_schema(payload, cursor, schema, field_name, description, base_offset)
        if category == "string":
            return cls._decode_string_schema(payload, cursor, schema, field_name, description, base_offset)
        return cls._decode_primitive_schema(payload, cursor, schema, field_name, description, base_offset)

    @classmethod
    def _decode_struct_schema(
        cls,
        payload: bytes,
        cursor: int,
        schema: Dict[str, Any],
        field_name: str,
        description: str,
        base_offset: int,
    ) -> Tuple[Dict[str, Any], int, List[str]]:
        start_cursor = cursor
        has_length_prefix = bool(schema.get("has_length_prefix", False))
        length_field_size = max(0, int(schema.get("length_field_size_bits", 32) or 32) // 8)
        declared_length: Optional[int] = None

        if has_length_prefix and length_field_size > 0:
            if cursor + length_field_size <= len(payload):
                declared_length = int.from_bytes(payload[cursor:cursor + length_field_size], "big")
                cursor += length_field_size
            else:
                remaining = payload[start_cursor:]
                node = cls._node(
                    field_name,
                    "<truncated struct length>",
                    base_offset + start_cursor,
                    len(remaining),
                    description or "结构体长度字段不完整",
                    data_text=cls.format_hex_dump(remaining),
                )
                return node, len(payload), [f"{field_name}: <truncated struct length>"]

        body_limit = len(payload) if declared_length is None else min(len(payload), cursor + declared_length)
        body_cursor = cursor
        children: List[Dict[str, Any]] = []
        lines: List[str] = []

        for member in schema.get("members", []) or []:
            member_name = str(member.get("name") or member.get("type_name") or "member")
            member_schema = member.get("schema") if isinstance(member.get("schema"), dict) else {}
            member_rule = {
                "parameter_description": member.get("description", ""),
                "data_type": member.get("type_name") or member_schema.get("type_name") or member_schema.get("data_type") or "",
            }
            child_node, next_cursor, child_lines = cls._decode_schema_field(
                payload[:body_limit],
                body_cursor,
                member_schema,
                member_name,
                base_offset,
                member_rule,
            )
            children.append(child_node)
            lines.extend([f"{field_name}.{line}" for line in child_lines])
            if next_cursor <= body_cursor:
                break
            body_cursor = next_cursor
            if body_cursor >= body_limit:
                break

        if body_cursor < body_limit:
            remainder = payload[body_cursor:body_limit]
            children.append(
                cls._node(
                    "TrailingBytes",
                    cls._format_preview(remainder),
                    base_offset + body_cursor,
                    len(remainder),
                    "结构体中未解析的剩余字节",
                    data_text=cls.format_hex_dump(remainder),
                )
            )

        consumed_end = body_limit if declared_length is not None else body_cursor
        value = f"{len(children)} fields"
        if declared_length is not None:
            value = f"{value}, len={declared_length}"
        raw_segment = payload[start_cursor:consumed_end]
        node = cls._node(
            field_name,
            value,
            base_offset + start_cursor,
            max(0, consumed_end - start_cursor),
            description,
            children=children,
            data_text=cls._build_text_block([
                ("字段", field_name),
                ("类型", schema.get("type_name") or "struct"),
                ("长度前缀", "yes" if has_length_prefix else "no"),
                ("声明长度", declared_length if declared_length is not None else "-"),
                ("实际长度", consumed_end - start_cursor),
                ("原始数据", cls._format_preview(raw_segment, limit=48)),
            ]),
        )
        return node, consumed_end, lines or [f"{field_name}: {value}"]

    @classmethod
    def _decode_array_schema(
        cls,
        payload: bytes,
        cursor: int,
        schema: Dict[str, Any],
        field_name: str,
        description: str,
        base_offset: int,
    ) -> Tuple[Dict[str, Any], int, List[str]]:
        start_cursor = cursor
        length_type = str(schema.get("length_type") or "").strip().lower()
        length_field_size = max(0, int(schema.get("length_field_size_bits", 32) or 32) // 8)
        declared_count: Optional[int] = None

        if length_type == "dynamic" and length_field_size > 0:
            if cursor + length_field_size <= len(payload):
                declared_count = int.from_bytes(payload[cursor:cursor + length_field_size], "big")
                cursor += length_field_size
            else:
                remaining = payload[start_cursor:]
                node = cls._node(
                    field_name,
                    "<truncated array length>",
                    base_offset + start_cursor,
                    len(remaining),
                    description or "数组长度字段不完整",
                    data_text=cls.format_hex_dump(remaining),
                )
                return node, len(payload), [f"{field_name}: <truncated array length>"]
        elif length_type == "fixed":
            declared_count = max(int(schema.get("max_length", 0) or 0), int(schema.get("min_length", 0) or 0))

        element_schema = schema.get("element_schema") if isinstance(schema.get("element_schema"), dict) else {}
        element_name = str(schema.get("element_name") or "item")
        children: List[Dict[str, Any]] = []
        lines: List[str] = []
        index = 0

        while cursor < len(payload) and (declared_count is None or index < declared_count):
            child_field_name = f"{element_name}[{index}]"
            child_rule = {
                "parameter_description": description,
                "data_type": element_schema.get("type_name") or element_schema.get("data_type") or "",
            }
            child_node, next_cursor, child_lines = cls._decode_schema_field(
                payload,
                cursor,
                element_schema,
                child_field_name,
                base_offset,
                child_rule,
            )
            children.append(child_node)
            lines.extend([f"{field_name}.{line}" for line in child_lines])
            if next_cursor <= cursor:
                break
            cursor = next_cursor
            index += 1

        value = f"{len(children)} items"
        if declared_count is not None:
            value = f"{len(children)}/{declared_count} items"
        raw_segment = payload[start_cursor:cursor]
        node = cls._node(
            field_name,
            value,
            base_offset + start_cursor,
            max(0, cursor - start_cursor),
            description,
            children=children,
            data_text=cls._build_text_block([
                ("字段", field_name),
                ("类型", schema.get("type_name") or "array"),
                ("长度类型", length_type or "-"),
                ("声明个数", declared_count if declared_count is not None else "-"),
                ("实际个数", len(children)),
                ("原始数据", cls._format_preview(raw_segment, limit=48)),
            ]),
        )
        return node, cursor, lines or [f"{field_name}: {value}"]

    @classmethod
    def _decode_string_schema(
        cls,
        payload: bytes,
        cursor: int,
        schema: Dict[str, Any],
        field_name: str,
        description: str,
        base_offset: int,
    ) -> Tuple[Dict[str, Any], int, List[str]]:
        start_cursor = cursor
        length_type = str(schema.get("length_type") or "").strip().lower()
        length_field_size = max(0, int(schema.get("length_field_size_bits", 32) or 32) // 8)

        if length_type == "dynamic" and length_field_size > 0:
            if cursor + length_field_size <= len(payload):
                byte_length = int.from_bytes(payload[cursor:cursor + length_field_size], "big")
                cursor += length_field_size
            else:
                byte_length = 0
        else:
            byte_length = max(int(schema.get("max_length", 0) or 0), int(schema.get("min_length", 0) or 0))

        end_cursor = min(len(payload), cursor + max(0, byte_length))
        raw_value = payload[cursor:end_cursor]
        encoding = str(schema.get("encoding") or "utf-8").replace("Unicode(", "").replace(")", "").strip() or "utf-8"
        try:
            value_text = raw_value.decode(encoding.lower().replace("-", "-"), errors="ignore").rstrip("\x00")
        except LookupError:
            value_text = raw_value.decode("utf-8", errors="ignore").rstrip("\x00")
        next_cursor = end_cursor
        node = cls._node(
            field_name,
            value_text,
            base_offset + start_cursor,
            max(0, next_cursor - start_cursor),
            description,
            data_text=cls._build_text_block([
                ("字段", field_name),
                ("值", value_text),
                ("类型", schema.get("type_name") or "string"),
                ("编码", encoding),
                ("长度", byte_length),
                ("原始", raw_value.hex(" ").upper()),
            ]),
        )
        return node, next_cursor, [f"{field_name}: {value_text}"]

    @classmethod
    def _decode_primitive_schema(
        cls,
        payload: bytes,
        cursor: int,
        schema: Dict[str, Any],
        field_name: str,
        description: str,
        base_offset: int,
    ) -> Tuple[Dict[str, Any], int, List[str]]:
        data_type = str(schema.get("data_type") or schema.get("type_name") or "uint8").strip()
        byte_length = cls._primitive_byte_length(data_type)
        if byte_length <= 0:
            byte_length = 1
        end_cursor = min(len(payload), cursor + byte_length)
        raw_value_bytes = payload[cursor:end_cursor]
        raw_hex = raw_value_bytes.hex(" ").upper()

        decoded_value, numeric_value = cls._decode_primitive_value(raw_value_bytes, data_type)
        value_text = cls._format_schema_value(decoded_value, numeric_value, schema, raw_value_bytes)
        node = cls._node(
            field_name,
            value_text,
            base_offset + cursor,
            max(0, end_cursor - cursor),
            description,
            data_text=cls._build_text_block([
                ("字段", field_name),
                ("值", value_text),
                ("类型", schema.get("type_name") or data_type),
                ("基础类型", data_type),
                ("原始", raw_hex),
                ("单位", schema.get("unit") or ""),
                ("分辨率", schema.get("resolution") or ""),
                ("偏移", schema.get("offset") or ""),
                ("枚举/离散值", ", ".join(f"0x{int(k):X}={v}" for k, v in (schema.get("enum_map", {}) or {}).items() if str(k).lstrip("-").isdigit()) if schema.get("enum_map") else "-"),
            ]),
        )
        return node, end_cursor, [f"{field_name}: {value_text}"]

    @classmethod
    def _decode_primitive_value(cls, raw_value_bytes: bytes, data_type: str) -> Tuple[Any, Optional[float]]:
        if not raw_value_bytes:
            return "", None

        normalized = data_type.strip().lower()
        bit_size = cls._primitive_byte_length(normalized) * 8
        numeric_value: Optional[float] = None

        if any(token in normalized for token in ["bool", "boolean"]):
            value = raw_value_bytes[0] != 0
            numeric_value = float(int(value))
            return value, numeric_value

        if normalized in {"float", "float32"} and len(raw_value_bytes) >= 4:
            value = struct.unpack(">f", raw_value_bytes[:4])[0]
            return value, float(value)
        if normalized in {"double", "float64"} and len(raw_value_bytes) >= 8:
            value = struct.unpack(">d", raw_value_bytes[:8])[0]
            return value, float(value)

        raw_int = int.from_bytes(raw_value_bytes, byteorder="big", signed=False)
        if any(token in normalized for token in ["sint", "signed"]) or (normalized.startswith("int") and not normalized.startswith("uint")):
            value = cls._to_signed(raw_int, bit_size)
            numeric_value = float(value)
            return value, numeric_value

        numeric_value = float(raw_int)
        return raw_int, numeric_value

    @classmethod
    def _format_schema_value(
        cls,
        decoded_value: Any,
        numeric_value: Optional[float],
        schema: Dict[str, Any],
        raw_value_bytes: bytes,
    ) -> str:
        if isinstance(decoded_value, bool):
            return "True" if decoded_value else "False"

        adjusted_value: Any = decoded_value
        if numeric_value is not None:
            resolution = cls._to_float(schema.get("resolution"))
            offset = cls._to_float(schema.get("offset"))
            adjusted_numeric = numeric_value
            if resolution is not None:
                adjusted_numeric *= resolution
            if offset is not None:
                adjusted_numeric += offset
            adjusted_value = int(adjusted_numeric) if adjusted_numeric.is_integer() else adjusted_numeric

        enum_map = schema.get("enum_map") if isinstance(schema.get("enum_map"), dict) else {}
        if numeric_value is not None:
            enum_key = int(numeric_value)
            enum_val = enum_map.get(enum_key) or enum_map.get(str(enum_key))
            if enum_val is not None:
                return f"{enum_val} (0x{enum_key:0{max(2, len(raw_value_bytes) * 2)}X})"

        text = str(adjusted_value)
        unit = str(schema.get("unit") or "").strip()
        if unit:
            text = f"{text} {unit}"
        return text

    @staticmethod
    def _primitive_byte_length(data_type: str) -> int:
        normalized = str(data_type or "").strip().lower()
        if normalized in {"bool", "boolean", "char", "int8", "uint8", "sint8"}:
            return 1
        if normalized in {"int16", "uint16", "sint16"}:
            return 2
        if normalized in {"int32", "uint32", "sint32", "float", "float32"}:
            return 4
        if normalized in {"int64", "uint64", "sint64", "double", "float64"}:
            return 8
        match = re.search(r"(u?int|sint)(\d+)", normalized)
        if match:
            return max(1, int(match.group(2)) // 8)
        return 1

    @classmethod
    def _decode_rule_value(
        cls,
        payload: bytes,
        byte_offset: int,
        bit_offset: int,
        bit_length: int,
        rule: Dict[str, Any],
    ) -> Tuple[str, str]:
        bit_start = byte_offset * 8 + bit_offset
        raw_value = cls._extract_bits(payload, bit_start, bit_length)
        raw_hex = f"0x{raw_value:0{max(2, (bit_length + 3) // 4)}X}"
        data_type = str(rule.get("data_type") or "").strip().lower()

        value: Any
        if "bool" in data_type:
            value = bool(raw_value)
        elif any(token in data_type for token in ["sint", "int", "signed"]) and "uint" not in data_type:
            value = cls._to_signed(raw_value, bit_length)
        elif any(token in data_type for token in ["char", "string", "ascii"]):
            byte_length = max(1, (bit_length + 7) // 8)
            data = payload[byte_offset:byte_offset + byte_length]
            value = data.decode("utf-8", errors="ignore").rstrip("\x00")
        else:
            value = raw_value

        if isinstance(value, (int, float)):
            factor = cls._to_float(rule.get("factor"))
            offset_value = cls._to_float(rule.get("offset_value"))
            if factor is not None:
                value = value * factor
            if offset_value is not None:
                value = value + offset_value

        unit = str(rule.get("unit") or "").strip()
        text = str(value)
        if unit:
            text = f"{text} {unit}"
        return text, raw_hex

    @staticmethod
    def _extract_bits(payload: bytes, bit_start: int, bit_length: int) -> int:
        if bit_length <= 0:
            return 0
        total_bits = len(payload) * 8
        if bit_start >= total_bits:
            return 0
        end_bit = min(total_bits, bit_start + bit_length)
        if end_bit <= bit_start:
            return 0
        value = int.from_bytes(payload, byteorder="big", signed=False)
        shift = total_bits - end_bit
        mask = (1 << (end_bit - bit_start)) - 1
        return (value >> shift) & mask

    @staticmethod
    def _to_signed(value: int, bit_length: int) -> int:
        if bit_length <= 0:
            return value
        sign_bit = 1 << (bit_length - 1)
        return value - (1 << bit_length) if value & sign_bit else value

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            match = re.search(r"-?\d+(?:\.\d+)?", text)
            if not match:
                return None
            try:
                return float(match.group(0))
            except ValueError:
                return None

    @staticmethod
    def _reader_position(reader: Any) -> Optional[int]:
        try:
            if hasattr(reader, "f") and hasattr(reader.f, "tell"):
                return int(reader.f.tell())
            if hasattr(reader, "wrapped") and hasattr(reader.wrapped, "f") and hasattr(reader.wrapped.f, "tell"):
                return int(reader.wrapped.f.tell())
        except Exception:
            return None
        return None

    @classmethod
    def _resolve_batch_settings(
        cls,
        batch_size: int,
        initial_batch_size: Optional[int],
        flush_interval_ms: int,
    ) -> Tuple[int, int, float]:
        steady_batch_size = max(1, int(batch_size or cls.DEFAULT_BATCH_SIZE))
        requested_initial_batch_size = cls.DEFAULT_INITIAL_BATCH_SIZE if initial_batch_size is None else initial_batch_size
        first_batch_size = max(1, min(steady_batch_size, int(requested_initial_batch_size)))
        flush_interval_seconds = max(0.0, float(flush_interval_ms) / 1000.0)
        return first_batch_size, steady_batch_size, flush_interval_seconds

    @staticmethod
    def _should_flush_batch(
        packets: List[Dict[str, Any]],
        target_batch_size: int,
        last_flush_time: float,
        flush_interval_seconds: float,
    ) -> bool:
        if not packets:
            return False
        if len(packets) >= max(1, target_batch_size):
            return True
        if flush_interval_seconds <= 0:
            return True
        return (time.perf_counter() - last_flush_time) >= flush_interval_seconds

    @staticmethod
    def _report_progress(
        progress_callback: Optional[Callable[[int, str], None]],
        value: int,
        message: str,
    ) -> None:
        if not progress_callback:
            return
        try:
            progress_callback(max(0, min(100, int(value))), message)
        except Exception:
            pass

    @staticmethod
    def _node(
        field: str,
        value: str = "",
        offset: Optional[int] = None,
        length: Optional[int] = None,
        description: str = "",
        children: Optional[List[Dict[str, Any]]] = None,
        data_text: str = "",
    ) -> Dict[str, Any]:
        return {
            "field": field,
            "value": value,
            "offset": offset,
            "length": length,
            "description": description,
            "children": children or [],
            "data_text": data_text,
        }

