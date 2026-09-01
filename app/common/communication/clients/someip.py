#!/usr/bin/env python3
"""SOME/IP 多 Client / 多 Service 集成测试入口。

默认在回环网卡启动多个逻辑 Service，并用多个 :class:`SomeIPClient`
执行服务发现和 RPC Request/Response。也支持将服务端和客户端分开运行：

	python -m app.common.communication.clients.someip --role all
	python -m app.common.communication.clients.someip --role service
	python -m app.common.communication.clients.someip --role client --target-ip 127.0.0.2

这里的 Service Provider 是测试桩，只实现本测试所需的 SOME/IP-SD OfferService
和 UDP RPC Response；生产客户端行为全部复用 ``SomeIPClient`` 的公开方法。
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

try:
	from .Someip_Client import SomeIPClient
except ImportError:  # 兼容直接执行当前文件
	from Someip_Client import SomeIPClient

from scapy.contrib.automotive.someip import (
	SD as SOMEIP_SD,
	SDEntry_Service,
	SDOption_IP4_EndPoint,
	SOMEIP,
)


logger = logging.getLogger("SomeIPMultiTest")


@dataclass
class ServiceConfig:
	"""一个逻辑 SOME/IP 服务的测试配置。"""

	service_id: int
	instance_id: int
	endpoint_port: int
	method_id: int = 0x0001
	major_version: int = 1
	minor_version: int = 0
	ttl: int = 3
	event_group_id: int = 0x0001
	request_payload: bytes = b""
	expected_response: Optional[bytes] = None
	response_payload: Optional[bytes] = None
	expected_requests: int = 0


@dataclass
class ClientConfig:
	"""一个 SOME/IP 客户端实例的测试配置。"""

	client_id: int
	local_port: int
	vlan_id: Optional[int] = None
	client_mac: Optional[str] = None
	target_mac: Optional[str] = None


@dataclass
class RequestResult:
	"""一条 Client -> Service 测试结果。"""

	client_id: int
	service_id: int
	method_id: int
	success: bool
	elapsed: float
	response: Optional[bytes] = None
	error: str = ""


@dataclass
class DiscoveryResult:
	"""一次服务发现的结果。"""

	client_id: int
	service_id: int
	found: bool
	udp_endpoints: List[Tuple[str, int]] = None
	tcp_endpoints: List[Tuple[str, int]] = None
	instance_id: int = 0xFFFF
	major_version: int = 0
	minor_version: int = 0
	elapsed: float = 0.0
	error: str = ""


ResponseHandler = Callable[[ServiceConfig, Any, bytes], bytes]


def _default_response_handler(config: ServiceConfig, packet: Any, payload: bytes) -> bytes:
	"""返回包含 Service ID 的 ACK，便于验证响应来自正确服务。"""

	if config.response_payload is not None:
		return config.response_payload
	return f"ACK-{config.service_id:04X}:".encode("ascii") + payload


class SomeIPTestService:
	"""一个进程内承载多个逻辑 Service 的轻量 UDP Provider。

	所有服务共享一个 SD socket，每个服务使用独立业务 socket。这样既符合
	SOME/IP 的 Endpoint 广告模型，也避免 Windows 对多个 socket 同时绑定
	SD 端口时可能只把数据交给其中一个 socket 的问题。
	"""

	def __init__(
		self,
		local_ip: str,
		services: Sequence[ServiceConfig],
		multicast_ip: str = SomeIPClient.DEFAULT_SD_MULTICAST_IP,
		sd_port: int = SomeIPClient.DEFAULT_SD_MULTICAST_PORT,
		response_handler: Optional[ResponseHandler] = None,
	) -> None:
		if not services:
			raise ValueError("至少需要配置一个 Service")

		service_ids = [item.service_id for item in services]
		endpoint_ports = [item.endpoint_port for item in services if item.endpoint_port != 0]
		if len(service_ids) != len(set(service_ids)):
			raise ValueError("Service ID 必须唯一")
		if len(endpoint_ports) != len(set(endpoint_ports)):
			raise ValueError("Service endpoint 端口必须唯一")

		self.local_ip = local_ip
		self.multicast_ip = multicast_ip
		self.sd_port = sd_port
		self.services = list(services)
		self.response_handler = response_handler or _default_response_handler

		self.running = False
		self._sd_socket: Optional[socket.socket] = None
		self._service_sockets: Dict[int, socket.socket] = {}
		self._threads: List[threading.Thread] = []
		self._stats_lock = threading.Lock()
		self._request_count: Dict[int, int] = {item.service_id: 0 for item in services}

	@property
	def request_count(self) -> Dict[int, int]:
		with self._stats_lock:
			return dict(self._request_count)

	def start(self) -> bool:
		"""绑定 SD/业务端口并启动接收线程。"""

		if self.running:
			return True

		try:
			self._sd_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			self._sd_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			self._sd_socket.settimeout(0.2)
			# 固定绑定本地 IP，确保单播 Offer 的源 IP 是 Provider IP，而不是
			# Windows 路由表选择出的其他地址（客户端会过滤自己的源 IP）。
			self._sd_socket.bind((self.local_ip, self.sd_port))
			try:
				membership = socket.inet_aton(self.multicast_ip) + socket.inet_aton(self.local_ip)
				self._sd_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
			except OSError as exc:
				# 单播发现仍可工作，因此组播加入失败不阻止测试桩启动。
				logger.warning("Service 加入组播组失败，将保留单播发现: %s", exc)

			for config in self.services:
				service_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
				service_socket.settimeout(0.2)
				service_socket.bind((self.local_ip, config.endpoint_port))
				if config.endpoint_port == 0:
					config.endpoint_port = service_socket.getsockname()[1]
				self._service_sockets[config.service_id] = service_socket

			self.running = True
			self._start_thread(self._sd_loop, "someip-test-sd")
			for config in self.services:
				self._start_thread(
					lambda item=config: self._service_loop(item),
					f"someip-service-{config.service_id:04X}",
				)

			endpoints = ", ".join(
				f"0x{item.service_id:04X}@{self.local_ip}:{item.endpoint_port}"
				for item in self.services
			)
			logger.info("测试 Service 已启动: %s (SD=%s:%s)", endpoints, self.multicast_ip, self.sd_port)
			return True
		except Exception as exc:
			logger.error("测试 Service 启动失败: %s", exc)
			self.stop()
			return False

	def stop(self) -> None:
		"""幂等地停止所有 Service socket 和线程。"""

		self.running = False
		sockets = [self._sd_socket, *self._service_sockets.values()]
		for current_socket in sockets:
			if current_socket is not None:
				try:
					current_socket.close()
				except OSError:
					pass
		self._sd_socket = None
		self._service_sockets.clear()

		current_thread = threading.current_thread()
		for thread in self._threads:
			if thread is not current_thread:
				thread.join(timeout=0.5)
		self._threads.clear()

	def _start_thread(self, target: Callable[[], None], name: str) -> None:
		thread = threading.Thread(target=target, name=name, daemon=True)
		self._threads.append(thread)
		thread.start()

	def _sd_loop(self) -> None:
		while self.running and self._sd_socket is not None:
			try:
				data, sender = self._sd_socket.recvfrom(65535)
				requested = self._parse_find_service(data)
				if requested is None:
					continue
				for config in self.services:
					if requested in (0xFFFF, config.service_id):
						self._send_offer(config, sender)
			except socket.timeout:
				continue
			except OSError:
				if self.running:
					logger.exception("SD socket 接收失败")
				break
			except Exception:
				logger.exception("处理 FindService 失败")

	@staticmethod
	def _parse_find_service(data: bytes) -> Optional[int]:
		try:
			packet = SOMEIP(data)
			if packet.srv_id != 0xFFFF or packet.sub_id != 0x8100:
				return None
			sd_packet = packet.payload
			if not isinstance(sd_packet, SOMEIP_SD) and hasattr(sd_packet, "load"):
				sd_packet = SOMEIP_SD(sd_packet.load)
			if not isinstance(sd_packet, SOMEIP_SD):
				return None
			for entry in sd_packet.entry_array:
				if entry.type == 0x00:
					return int(entry.srv_id)
		except Exception:
			logger.debug("忽略无法解析的 SD 数据包", exc_info=True)
		return None

	def _send_offer(self, config: ServiceConfig, sender: Tuple[str, int]) -> None:
		if self._sd_socket is None:
			return

		option = SDOption_IP4_EndPoint(
			type=0x04,
			addr=self.local_ip,
			l4_proto=0x11,
			port=config.endpoint_port,
		)
		entry = SDEntry_Service(
			type=0x01,
			index_1=0,
			n_opt_1=1,
			srv_id=config.service_id,
			inst_id=config.instance_id,
			major_ver=config.major_version,
			ttl=config.ttl,
			minor_ver=config.minor_version,
		)
		sd_packet = SOMEIP_SD(flags=0x80, entry_array=[entry], option_array=[option])
		packet = SOMEIP(
			srv_id=0xFFFF,
			sub_id=0x8100,
			client_id=0,
			session_id=1,
			msg_type=0x02,
		) / sd_packet
		self._sd_socket.sendto(bytes(packet), sender)
		logger.debug("OfferService 0x%04X -> %s:%s", config.service_id, *sender)

	def _service_loop(self, config: ServiceConfig) -> None:
		service_socket = self._service_sockets[config.service_id]
		while self.running:
			try:
				data, sender = service_socket.recvfrom(65535)
				request = SOMEIP(data)
				if request.srv_id != config.service_id or request.msg_type != 0x00:
					continue
				if request.sub_id != config.method_id:
					self._send_error(service_socket, request, sender, retcode=0x03)
					continue

				payload = bytes(request.payload)
				response_payload = self.response_handler(config, request, payload)
				response = SOMEIP(
					srv_id=request.srv_id,
					sub_id=request.sub_id,
					client_id=request.client_id,
					session_id=request.session_id,
					proto_ver=request.proto_ver,
					iface_ver=request.iface_ver,
					msg_type=0x80,
					retcode=0x00,
				) / response_payload
				service_socket.sendto(bytes(response), sender)
				with self._stats_lock:
					self._request_count[config.service_id] += 1
			except socket.timeout:
				continue
			except OSError:
				if self.running:
					logger.exception("Service 0x%04X socket 失败", config.service_id)
				break
			except Exception:
				logger.exception("Service 0x%04X 处理请求失败", config.service_id)

	@staticmethod
	def _send_error(
		service_socket: socket.socket,
		request: Any,
		sender: Tuple[str, int],
		retcode: int,
	) -> None:
		response = SOMEIP(
			srv_id=request.srv_id,
			sub_id=request.sub_id,
			client_id=request.client_id,
			session_id=request.session_id,
			msg_type=0x81,
			retcode=retcode,
		)
		service_socket.sendto(bytes(response), sender)


class MultiSomeIPTestRunner:
	"""创建多个 ``SomeIPClient`` 并完成 Client × Service 矩阵测试。"""

	def __init__(
		self,
		local_ip: str,
		target_ip: str,
		clients: Sequence[ClientConfig],
		services: Sequence[ServiceConfig],
		multicast_ip: str = SomeIPClient.DEFAULT_SD_MULTICAST_IP,
		sd_port: int = SomeIPClient.DEFAULT_SD_MULTICAST_PORT,
		timeout: float = 2.0,
	) -> None:
		self.local_ip = local_ip
		self.target_ip = target_ip
		self.client_configs = list(clients)
		self.services = list(services)
		self.multicast_ip = multicast_ip
		self.sd_port = sd_port
		self.timeout = timeout
		self.clients: List[SomeIPClient] = []

	def start_clients(self) -> bool:
		"""通过 ``SomeIPClient.start`` 启动所有客户端。"""

		if self.clients:
			return True
		try:
			for config in self.client_configs:
				client = SomeIPClient(
					local_ip=self.local_ip,
					local_port=config.local_port,
					client_id=config.client_id,
					multicast_ip=self.multicast_ip,
					multicast_port=self.sd_port,
					vlan_id=config.vlan_id,
					client_mac=config.client_mac,
					target_mac=config.target_mac,
				)
				if not client.start():
					raise RuntimeError(f"Client 0x{config.client_id:04X} 启动失败")
				self.clients.append(client)
			return True
		except Exception:
			logger.exception("启动测试 Client 失败")
			self.stop_clients()
			return False

	def stop_clients(self) -> None:
		for client in self.clients:
			client.stop(source="MultiSomeIPTestRunner.stop_clients", reason="test_finished")
		self.clients.clear()

	def check_connectivity(self, discovery_timeout: float = 3.0) -> List[DiscoveryResult]:
		"""轻量级连通性检查：仅执行 FindService/OfferService，不发送业务请求。

		对每个 Client × Service 组合进行服务发现，返回发现结果列表。
		适合在正式测试前快速验证网络可达性和服务可用性。
		"""

		if not self.start_clients():
			return []

		all_results: List[DiscoveryResult] = []
		result_lock = threading.Lock()

		def check_one_client(client: SomeIPClient) -> None:
			client_results: List[DiscoveryResult] = []
			for service in self.services:
				started_at = time.perf_counter()
				found = False
				udp_eps: List[Tuple[str, int]] = []
				tcp_eps: List[Tuple[str, int]] = []
				inst_id = 0xFFFF
				major_ver = 0
				minor_ver = 0
				error = ""

				found_offer = threading.Event()

				def on_sd(entries, options, _svc=service):
					nonlocal found, udp_eps, tcp_eps, inst_id, major_ver, minor_ver
					for entry in entries:
						if entry.type == 0x01 and entry.srv_id == _svc.service_id:
							if hasattr(entry, 'inst_id'):
								inst_id = entry.inst_id
							if hasattr(entry, 'major_ver'):
								major_ver = entry.major_ver
							if hasattr(entry, 'minor_ver'):
								minor_ver = entry.minor_ver
							eps = client._extract_endpoints(entry, options)
							if eps[0] or eps[1]:
								tcp_eps.extend(eps[0])
								udp_eps.extend(eps[1])
								found = True
								found_offer.set()

				client.register_sd_callback(on_sd)
				try:
					# 策略 A: 组播 Find
					client.find_service(service.service_id)
					if not found_offer.wait(timeout=discovery_timeout / 2):
						# 策略 B: 单播 Find
						if self.target_ip:
							client.find_service(service.service_id, override_ip=self.target_ip)
							found_offer.wait(timeout=discovery_timeout / 2)
				except Exception as exc:
					error = str(exc)
				finally:
					client.unregister_sd_callback(on_sd)

				client_results.append(DiscoveryResult(
					client_id=client.client_id,
					service_id=service.service_id,
					found=found,
					udp_endpoints=udp_eps,
					tcp_endpoints=tcp_eps,
					instance_id=inst_id,
					major_version=major_ver,
					minor_version=minor_ver,
					elapsed=time.perf_counter() - started_at,
					error=error,
				))

			with result_lock:
				all_results.extend(client_results)

		threads = [
			threading.Thread(
				target=check_one_client,
				args=(client,),
				name=f"someip-check-{client.client_id:04X}",
			)
			for client in self.clients
		]
		for t in threads:
			t.start()
		for t in threads:
			t.join()

		return sorted(all_results, key=lambda r: (r.client_id, r.service_id))

	def discover_services(self, wildcard_timeout: float = 3.0) -> List[DiscoveryResult]:
		"""通配服务发现：发送 FindService(0xFFFF) 枚举设备上所有可用服务。

		只使用第一个 Client 执行通配发现，返回所有收到的 Offer 信息。
		"""

		if not self.start_clients():
			return []

		if not self.clients:
			return []

		client = self.clients[0]
		results: List[DiscoveryResult] = []
		seen_services: Dict[int, DiscoveryResult] = {}
		lock = threading.Lock()
		any_offer = threading.Event()

		def on_sd(entries, options):
			for entry in entries:
				if entry.type == 0x01:
					svc_id = int(entry.srv_id)
					eps = client._extract_endpoints(entry, options)
					inst = getattr(entry, 'inst_id', 0xFFFF)
					major = getattr(entry, 'major_ver', 0)
					minor = getattr(entry, 'minor_ver', 0)
					with lock:
						if svc_id not in seen_services:
							result = DiscoveryResult(
								client_id=client.client_id,
								service_id=svc_id,
								found=True,
								udp_endpoints=list(eps[1]),
								tcp_endpoints=list(eps[0]),
								instance_id=inst,
								major_version=major,
								minor_version=minor,
							)
							seen_services[svc_id] = result
							any_offer.set()

		client.register_sd_callback(on_sd)
		try:
			client.find_service(0xFFFF)
			any_offer.wait(timeout=wildcard_timeout / 2)
			if self.target_ip:
				client.find_service(0xFFFF, override_ip=self.target_ip)
				# 给第二次发现更多时间
				time.sleep(wildcard_timeout / 2)
		finally:
			client.unregister_sd_callback(on_sd)

		results = list(seen_services.values())
		return sorted(results, key=lambda r: r.service_id)

	def run(self) -> List[RequestResult]:
		"""并发运行多个 Client；每个 Client 依次访问全部 Service。"""

		if not self.start_clients():
			return []

		all_results: List[RequestResult] = []
		result_lock = threading.Lock()

		def run_one_client(client: SomeIPClient) -> None:
			current_results: List[RequestResult] = []
			for service in self.services:
				payload = service.request_payload or (
					f"client=0x{client.client_id:04X};service=0x{service.service_id:04X}".encode("ascii")
				)
				expected = service.expected_response
				if expected is None and self.target_ip.startswith("127."):
					expected = f"ACK-{service.service_id:04X}:".encode("ascii") + payload
				started_at = time.perf_counter()
				response: Optional[bytes] = None
				error = ""
				try:
					response = client.request_with_discovery(
						service_id=service.service_id,
						method_id=service.method_id,
						payload=payload,
						target_ip=self.target_ip,
						target_port=service.endpoint_port,
						event_group_id=service.event_group_id,
						timeout=self.timeout,
					)
					if response is None:
						error = "未收到 Response/Notification"
					elif expected is not None and response != expected:
						error = f"响应不匹配: expected={expected!r}, actual={response!r}"
				except Exception as exc:
					error = str(exc)
					logger.exception(
						"Client 0x%04X -> Service 0x%04X 异常",
						client.client_id,
						service.service_id,
					)
				current_results.append(
					RequestResult(
						client_id=client.client_id,
						service_id=service.service_id,
						method_id=service.method_id,
						success=not error,
						elapsed=time.perf_counter() - started_at,
						response=response,
						error=error,
					)
				)
			with result_lock:
				all_results.extend(current_results)

		threads = [
			threading.Thread(
				target=run_one_client,
				args=(client,),
				name=f"someip-client-test-{client.client_id:04X}",
			)
			for client in self.clients
		]
		for thread in threads:
			thread.start()
		for thread in threads:
			thread.join()

		return sorted(all_results, key=lambda item: (item.client_id, item.service_id))


def build_service_configs(count: int, base_service_id: int, base_port: int) -> List[ServiceConfig]:
	if count < 1:
		raise ValueError("services 必须大于 0")
	return [
		ServiceConfig(
			service_id=base_service_id + index,
			instance_id=index + 1,
			endpoint_port=base_port + index,
		)
		for index in range(count)
	]


def build_client_configs(count: int, base_client_id: int, base_port: int) -> List[ClientConfig]:
	if count < 1:
		raise ValueError("clients 必须大于 0")
	return [
		ClientConfig(client_id=base_client_id + index, local_port=base_port + index)
		for index in range(count)
	]


def _parse_int(value: Any, field_name: str) -> int:
	if isinstance(value, bool):
		raise ValueError(f"{field_name} 不能是布尔值")
	try:
		return int(value, 0) if isinstance(value, str) else int(value)
	except (TypeError, ValueError) as exc:
		raise ValueError(f"{field_name} 不是有效整数: {value!r}") from exc


def _parse_hex_bytes(value: Any, field_name: str) -> Optional[bytes]:
	if value is None:
		return None
	if not isinstance(value, str):
		raise ValueError(f"{field_name} 必须是十六进制字符串")
	text = value.strip().replace(" ", "").replace("_", "")
	if text.lower().startswith("0x"):
		text = text[2:]
	try:
		return bytes.fromhex(text)
	except ValueError as exc:
		raise ValueError(f"{field_name} 不是有效十六进制: {value!r}") from exc


def _service_from_dict(item: Dict[str, Any], prefix: str) -> ServiceConfig:
	return ServiceConfig(
		service_id=_parse_int(item["service_id"], f"{prefix}.service_id"),
		instance_id=_parse_int(item.get("instance_id", 0xFFFF), f"{prefix}.instance_id"),
		endpoint_port=_parse_int(item["endpoint_port"], f"{prefix}.endpoint_port"),
		method_id=_parse_int(item.get("method_id", 1), f"{prefix}.method_id"),
		major_version=_parse_int(item.get("major_version", 1), f"{prefix}.major_version"),
		minor_version=_parse_int(item.get("minor_version", 0), f"{prefix}.minor_version"),
		ttl=_parse_int(item.get("ttl", 3), f"{prefix}.ttl"),
		event_group_id=_parse_int(item.get("event_group_id", 1), f"{prefix}.event_group_id"),
		request_payload=_parse_hex_bytes(item.get("request_payload_hex", ""), f"{prefix}.request_payload_hex") or b"",
		expected_response=_parse_hex_bytes(item.get("expected_response_hex"), f"{prefix}.expected_response_hex"),
		response_payload=_parse_hex_bytes(item.get("response_payload_hex"), f"{prefix}.response_payload_hex"),
		expected_requests=_parse_int(item.get("expected_requests", 0), f"{prefix}.expected_requests"),
	)


def load_device_config(path: str) -> Dict[str, Any]:
	"""加载真实设备双向测试配置，ID 字段同时支持十进制和 ``0x`` 字符串。"""

	config_path = Path(path)
	try:
		raw = json.loads(config_path.read_text(encoding="utf-8"))
	except (OSError, json.JSONDecodeError) as exc:
		raise ValueError(f"无法读取配置 {config_path}: {exc}") from exc

	network = raw.get("network", {})
	clients = [
		ClientConfig(
			client_id=_parse_int(item["client_id"], f"clients[{index}].client_id"),
			local_port=_parse_int(item["local_port"], f"clients[{index}].local_port"),
			vlan_id=(
				None
				if item.get("vlan_id") is None
				else _parse_int(item["vlan_id"], f"clients[{index}].vlan_id")
			),
			client_mac=item.get("client_mac"),
			target_mac=item.get("target_mac"),
		)
		for index, item in enumerate(raw.get("clients", []))
	]
	remote_services = [
		_service_from_dict(item, f"remote_services[{index}]")
		for index, item in enumerate(raw.get("remote_services", []))
	]
	provided_services = [
		_service_from_dict(item, f"provided_services[{index}]")
		for index, item in enumerate(raw.get("provided_services", []))
	]

	return {
		"local_ip": network.get("local_ip", "127.0.0.1"),
		"target_ip": network.get("device_ip", "127.0.0.2"),
		"multicast_ip": network.get("multicast_ip", SomeIPClient.DEFAULT_SD_MULTICAST_IP),
		"sd_port": _parse_int(network.get("sd_port", 30490), "network.sd_port"),
		"timeout": float(raw.get("timeout", 2.0)),
		"duration": float(raw.get("duration", 10.0)),
		"clients": clients,
		"remote_services": remote_services,
		"provided_services": provided_services,
	}


def print_connectivity_summary(results: Iterable[DiscoveryResult]) -> bool:
	result_list = list(results)
	print("\n=== SOME/IP 连通性检查 ===")
	for r in result_list:
		state = "OK" if r.found else "FAIL"
		ep_info = ""
		if r.found:
			parts = []
			if r.udp_endpoints:
				parts.append(f"UDP={r.udp_endpoints}")
			if r.tcp_endpoints:
				parts.append(f"TCP={r.tcp_endpoints}")
			ep_info = f" | {', '.join(parts)}" if parts else ""
			ep_info += f" | v{r.major_version}.{r.minor_version}"
		detail = "" if r.found else f" | {r.error}" if r.error else ""
		print(
			f"[{state}] Client=0x{r.client_id:04X} -> "
			f"Service=0x{r.service_id:04X} "
			f"({r.elapsed:.3f}s){ep_info}{detail}"
		)
	found_count = sum(r.found for r in result_list)
	print(f"汇总: {found_count}/{len(result_list)} 可达")
	return bool(result_list) and found_count == len(result_list)


def print_discovery_summary(results: Iterable[DiscoveryResult]) -> None:
	result_list = list(results)
	print("\n=== SOME/IP 服务发现 ===")
	if not result_list:
		print("未发现任何服务")
		return
	for r in result_list:
		parts = []
		if r.udp_endpoints:
			parts.append(f"UDP={r.udp_endpoints}")
		if r.tcp_endpoints:
			parts.append(f"TCP={r.tcp_endpoints}")
		ep_str = ', '.join(parts) if parts else "无端点"
		print(
			f"  Service=0x{r.service_id:04X} Instance=0x{r.instance_id:04X} "
			f"v{r.major_version}.{r.minor_version} | {ep_str}"
		)
	print(f"共发现 {len(result_list)} 个服务")


def print_summary(results: Iterable[RequestResult]) -> bool:
	result_list = list(results)
	print("\n=== SOME/IP 多实例测试结果 ===")
	for result in result_list:
		state = "PASS" if result.success else "FAIL"
		detail = "" if result.success else f" | {result.error}"
		print(
			f"[{state}] Client=0x{result.client_id:04X} -> "
			f"Service=0x{result.service_id:04X}/Method=0x{result.method_id:04X} "
			f"({result.elapsed:.3f}s){detail}"
		)
	passed = sum(item.success for item in result_list)
	print(f"汇总: {passed}/{len(result_list)} 通过")
	return bool(result_list) and passed == len(result_list)


def print_provider_summary(provider: SomeIPTestService) -> bool:
	counts = provider.request_count
	print("\n=== 设备 Client -> 本地 Service 测试结果 ===")
	passed = True
	for service in provider.services:
		actual = counts.get(service.service_id, 0)
		success = actual >= service.expected_requests
		passed = passed and success
		state = "PASS" if success else "FAIL"
		print(
			f"[{state}] Service=0x{service.service_id:04X}/Method=0x{service.method_id:04X} "
			f"收到请求={actual}, 最低要求={service.expected_requests}"
		)
	return passed


def create_argument_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="SOME/IP 多 Client / 多 Service 测试")
	parser.add_argument("--role", choices=("all", "service", "client", "device", "check"), default=None)
	parser.add_argument("--config", help="真实设备测试 JSON；指定后默认使用 device 双向模式")
	parser.add_argument("--local-ip", default="127.0.0.1", help="Client 本地绑定 IP")
	parser.add_argument(
		"--target-ip",
		default="127.0.0.2",
		help="Service 绑定/目标 IP；需与 Client IP 不同，以便接收 Offer",
	)
	parser.add_argument("--multicast-ip", default=SomeIPClient.DEFAULT_SD_MULTICAST_IP)
	parser.add_argument("--sd-port", type=int, default=SomeIPClient.DEFAULT_SD_MULTICAST_PORT)
	parser.add_argument("--clients", type=int, default=3)
	parser.add_argument("--services", type=int, default=2)
	parser.add_argument("--base-client-id", type=lambda value: int(value, 0), default=0x7001)
	parser.add_argument("--base-service-id", type=lambda value: int(value, 0), default=0x1050)
	parser.add_argument("--base-client-port", type=int, default=30810)
	parser.add_argument("--base-service-port", type=int, default=30500)
	parser.add_argument("--timeout", type=float, default=2.0)
	parser.add_argument(
		"--duration",
		type=float,
		default=0.0,
		help="service 模式运行秒数；0 表示运行到 Ctrl+C",
	)
	parser.add_argument("--debug", action="store_true")
	return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
	"""主入口: 直接执行 VLAN 多角色 SOME/IP 仿真测试。"""
	return vlan_main()


# ============================================================================
# VLAN L2 直连测试 (针对 ICC 等带 VLAN 标签的车载设备)
# ============================================================================

import random

from scapy.layers.l2 import Ether, Dot1Q
from scapy.layers.inet import IP, UDP, TCP
from scapy.sendrecv import sendp, sniff
from scapy.arch import get_if_list, get_if_addr, get_if_hwaddr
from scapy.contrib.automotive.someip import SDEntry_EventGroup


class VLANSomeIPTestRunner:
	"""基于 Scapy L2 收发的 VLAN SOME/IP 连通性测试。

	适用于 ICC 等车载 ECU 使用 802.1Q VLAN 标签通信的场景。
	Windows socket 层无法收到 tagged 帧，必须用 Scapy 在 L2 层收发。

	用法::

		runner = VLANSomeIPTestRunner(
			target_ip="192.168.62.129",
			vlan_id=62,
			sd_mcast="239.0.0.255",
		)
		runner.run()
	"""

	# ICC 服务定义 (从 Excel "ICC SOMEIP Services Interface Description V4.400" 完整解析)
	# 通信行为定义: Server=ICC_8155_Android(192.168.62.31), ServerPort=30500, VLAN=62
	# SD 全局: Multicast=239.0.0.255:30490 (UDP)
	# 格式: svc_id -> {name, instance_id, major_version, server_ip, server_port, transport,
	#         events: [(event_id, eventgroup_id, proto)], rpcs: [(method_id, proto)]}
	ICC_SERVICES = {
		0xA994: {  # eHMI_ParkingUI (UDP&TCP)
			"name": "eHMI_ParkingUI",
			"instance_id": 0x0001,
			"major_version": 1,
			"server_ip": "192.168.62.31",
			"server_port": 30500,
			"transport": "UDP&TCP",
			"events": [
				(0x8001, 0x0001, "UDP"),  # NtfParkingFuncModReq
				(0x8002, 0x0001, "UDP"),  # NtfApaRpaFcnOperating
				(0x8003, 0x0001, "UDP"),  # NtfHpaFcnOperating
				(0x8004, 0x0001, "TCP"),  # NtfVpaFcnOperating
				(0x8005, 0x0001, "UDP"),  # NtfMraFcnOperating
				(0x8006, 0x0001, "UDP"),  # NtfSVSStatus
				(0x8007, 0x0001, "UDP"),  # NtfApaRpaFcnOperating_2
				(0x8008, 0x0001, "UDP"),  # NtfHpaFcnOperating_2
			],
			"rpcs": [],
		},
		0xA995: {  # eHMI_ADASSetting (UDP)
			"name": "eHMI_ADASSetting",
			"instance_id": 0x0001,
			"major_version": 1,
			"server_ip": "192.168.62.31",
			"server_port": 30500,
			"transport": "UDP",
			"events": [
				(0x8001, 0x0001, "UDP"),  # NtfADASSettingInfo
				(0x8002, 0x0001, "UDP"),  # NtfADASSettingInfo_2
				(0x8003, 0x0001, "UDP"),  # NtfADASSettingInfo_3
			],
			"rpcs": [],
		},
		0xA99F: {  # eHMI_DVRSet (TCP)
			"name": "eHMI_DVRSet",
			"instance_id": 0x0001,
			"major_version": 1,
			"server_ip": "192.168.62.31",
			"server_port": 30500,
			"transport": "TCP",
			"events": [
				(0x8001, 0x0001, "TCP"),  # notifyDVRRequest
			],
			"rpcs": [],
		},
		0xAC04: {  # ICC_Aom (UDP&TCP)
			"name": "ICC_Aom",
			"instance_id": 0x0001,
			"major_version": 1,
			"server_ip": "192.168.62.31",
			"server_port": 30500,
			"transport": "UDP&TCP",
			"events": [
				(0x8001, 0x0001, "UDP"),  # notifyADCC_Command
			],
			"rpcs": [
				(0x0001, "TCP"),  # GetRenderDBInfo
			],
		},
		0xAC05: {  # ICC_Android_OutService (UDP)
			"name": "ICC_Android_OutService",
			"instance_id": 0x0001,
			"major_version": 1,
			"server_ip": "192.168.62.31",
			"server_port": 30500,
			"transport": "UDP",
			"events": [
				(0x8003, 0x0001, "UDP"),  # notifyEcallMdoeFed
			],
			"rpcs": [],
		},
		0xAC06: {  # ICC_SDmapInfo (UDP)
			"name": "ICC_SDmapInfo",
			"instance_id": 0x0001,
			"major_version": 1,
			"server_ip": "192.168.62.31",
			"server_port": 30500,
			"transport": "UDP",
			"events": [
				(0x8001, 0x0001, "UDP"),  # NtfSDmapInfo
				(0x8002, 0x0001, "UDP"),  # notifyNOA_SDMapPosInfo
				(0x8003, 0x0001, "UDP"),  # notifyNOA_SDMapStubInfo
				(0x8004, 0x0001, "UDP"),  # notifyNOA_SDMapSegmentInfo
				(0x8005, 0x0001, "UDP"),  # notifyNOA_SDMapShortInfo
				(0x8006, 0x0001, "UDP"),  # notifyNOA_SDMapLongInfo
				(0x8007, 0x0001, "UDP"),  # notifyNOA_SDMapMetaInfo
				(0x8008, 0x0001, "UDP"),  # NtfSDmapInfo_international
				(0x8009, 0x0001, "UDP"),  # NtfSDmapLaneInfo
			],
			"rpcs": [],
		},
		0xAC0C: {  # ICC_SDmapInfo_2 (UDP&TCP)
			"name": "ICC_SDmapInfo_2",
			"instance_id": 0x0001,
			"major_version": 1,
			"server_ip": "192.168.62.31",
			"server_port": 30500,
			"transport": "UDP&TCP",
			"events": [
				(0x8001, 0x0001, "TCP"),  # NtfSDmapRouteInfo
				(0x8002, 0x0001, "TCP"),  # NtfSDmapTBTNaviInfo
				(0x8003, 0x0001, "TCP"),  # NtfSDmapNaviCameraInfo
				(0x8004, 0x0001, "UDP"),  # NtfSDmapCruiseFacilityInfo
				(0x8005, 0x0001, "TCP"),  # NtfSDmapTrafficLightCDInfo
				(0x8006, 0x0001, "TCP"),  # NtfSDmapNaviIntCamDynInfo
				(0x8007, 0x0001, "TCP"),  # NtfSDmapNaviWeatherInfo
				(0x8008, 0x0001, "TCP"),  # NtfSDmapNaviCongestionInfo
				(0x8009, 0x0001, "TCP"),  # NtfSDmapNaviGreenWaveCarSpd
				(0x800A, 0x0001, "UDP"),  # notifySDmapLaneInfo
				(0x800B, 0x0001, "UDP"),  # NtfSDmapMixForkInfo
				(0x800C, 0x0001, "UDP"),  # NtfSDmapMyLocationInfo
				(0x800D, 0x0001, "UDP"),  # NtfSDmapNaviStatusInfo
				(0x800E, 0x0001, "UDP"),  # NtfSDmapSoundInfo
				(0x800F, 0x0001, "UDP"),  # NtfSDmapRouteOption
				(0x8010, 0x0001, "UDP"),  # NtfSDmapCruiseInfo
				(0x8011, 0x0001, "UDP"),  # NtfSDmapNaviRoadInfo
				(0x8012, 0x0001, "TCP"),  # NtfSDmapAheadLaneInfo
				(0x8013, 0x0001, "UDP"),  # NtfSDmapTollGateInfo
				(0x8014, 0x0001, "UDP"),  # NtfSDmapServiceAreaInfo
				(0x8015, 0x0001, "UDP"),  # NtfSDmapTunnelInfo
				(0x8016, 0x0001, "UDP"),  # NtfSDmapRampInfo
				(0x8017, 0x0001, "UDP"),  # NtfSDmapFacilityInfo
				(0x8018, 0x0001, "UDP"),  # NtfSDmapLocMatchInfo
				(0x8019, 0x0001, "UDP"),  # notifySDmapTollGateLaneInfo
				(0x801A, 0x0001, "UDP"),  # notifySDmapNavArriveAim
			],
			"rpcs": [],
		},
		0xAC0E: {  # TBOX_SystemInfo_ICC (UDP, Server=ICC_8155_QNX 192.168.62.32)
			"name": "TBOX_SystemInfo_ICC",
			"instance_id": 0x0001,
			"major_version": 1,
			"server_ip": "192.168.62.32",
			"server_port": 30500,
			"transport": "UDP",
			"events": [
				(0x8001, 0x0001, "UDP"),  # TBOX SystemInfo event
			],
			"rpcs": [
				(0x0003, "UDP"),
				(0x0004, "UDP"),
				(0x000D, "UDP"),
				(0x0011, "UDP"),
			],
		},
		0xAC0F: {  # IVI_UnixTimestamp (UDP)
			"name": "IVI_UnixTimestamp",
			"instance_id": 0x0001,
			"major_version": 1,
			"server_ip": "192.168.62.31",
			"server_port": 30500,
			"transport": "UDP",
			"events": [
				(0x8001, 0x0001, "UDP"),  # notifyUnixTimestamp
			],
			"rpcs": [],
		},
	}

	# Excel 定义的所有 Client ECU 身份 (用于多角色仿真)
	CLIENT_PROFILES = {
		"ADCC": {"ip": "192.168.62.11", "port": 30501, "id": 0x0000},
		"FCM":  {"ip": "192.168.62.15", "port": 30501, "id": 0x0000},
		"TBOX": {"ip": "192.168.62.1",  "port": 30501, "id": 0x0000},
	}

	# ICC 作为 Client 时消费的外部 Server 服务 (Excel 通信行为定义)
	# Server=TBOX(192.168.62.1), Client=ICC_8155_Android(192.168.62.31)
	EXTERNAL_SERVER_SERVICES = {
		0xAA02: {"name": "TBOX_TimeManagement", "server_ip": "192.168.62.1", "server_port": 30500,
				 "client_ip": "192.168.62.31", "client_port": 30501,
				 "events": [(0x8001, 0x0001, "UDP")]},
		0xAA09: {"name": "TBOX_ResSwtSts", "server_ip": "192.168.62.1", "server_port": 30500,
				 "client_ip": "192.168.62.31", "client_port": 30501,
				 "events": [(0x8001, 0x0001, "UDP")]},
		0xAA0A: {"name": "TBOX_SystemInfo", "server_ip": "192.168.62.1", "server_port": 30500,
				 "client_ip": "192.168.62.31", "client_port": 30501,
				 "events": [(0x8001, 0x0001, "UDP")]},
	}

	def __init__(
		self,
		target_ip: str = "192.168.62.129",
		vlan_id: int = 62,
		sd_mcast: str = "239.0.0.255",
		sd_port: int = 30490,
		biz_port: int = 30500,
		client_profiles: Dict[str, Dict] = None,
		passive_listen_sec: float = 8.0,
		rpc_wait_sec: float = 3.0,
	) -> None:
		self.target_ip = target_ip
		self.vlan_id = vlan_id
		self.sd_mcast = sd_mcast
		self.sd_port = sd_port
		self.biz_port = biz_port
		# 多 Client 身份: 默认包含 ADCC + FCM + TBOX
		self.client_profiles = client_profiles or self.CLIENT_PROFILES
		# 向后兼容: 默认使用第一个 profile
		first = next(iter(self.client_profiles.values()))
		self.client_ip = first["ip"]
		self.client_port = first["port"]
		self.client_id = first["id"]
		self.passive_listen_sec = passive_listen_sec
		self.rpc_wait_sec = rpc_wait_sec

		# 自动检测本地接口
		self.local_ip: Optional[str] = None
		self.local_mac: Optional[str] = None
		self.iface: Optional[str] = None
		self._detect_interface()

		# 解析目标 MAC (通过 ARP)
		self.target_mac: Optional[str] = None
		self._resolve_target_mac()

		# 运行时状态
		self._running = False
		self._discovered: Dict[int, Dict] = {}
		self._offer_count = 0
		self._responses: List[Dict] = []
		self._lock = threading.Lock()
		self._session_id = 0

	def _detect_interface(self) -> None:
		"""自动检测 192.168.62.x 子网对应的 Npcap 接口。"""
		for iface in get_if_list():
			try:
				addr = get_if_addr(iface)
				if addr.startswith("192.168.62."):
					self.iface = iface
					self.local_ip = addr
					self.local_mac = get_if_hwaddr(iface)
					return
			except Exception:
				pass
		raise RuntimeError(
			"未找到 192.168.62.x 子网的网络接口，请检查网卡配置"
		)

	def _resolve_target_mac(self) -> None:
		"""通过 ARP 解析目标设备的 MAC 地址。"""
		try:
			import subprocess
			# 先 ping 一下触发 ARP 解析
			subprocess.run(
				["ping", "-n", "1", "-w", "1000", self.target_ip],
				capture_output=True, timeout=5,
			)
			# 查 ARP 表
			r = subprocess.run(
				["arp", "-a", "-N", self.local_ip],
				capture_output=True, text=True, timeout=5,
			)
			for line in r.stdout.splitlines():
				if self.target_ip in line:
					parts = line.split()
					for p in parts:
						# 匹配 MAC 地址格式 xx-xx-xx-xx-xx-xx
						if len(p) == 17 and p.count("-") == 5:
							self.target_mac = p.replace("-", ":").lower()
							return
		except Exception:
			pass

	# ---- 包处理 ----

	def _next_session(self) -> int:
		self._session_id += 1
		return self._session_id

	def _process_packet(self, pkt) -> None:
		"""Scapy sniff 回调：解析 VLAN-tagged SOME/IP 包。"""
		if not self._running:
			return
		try:
			if Dot1Q not in pkt or pkt[Dot1Q].vlan != self.vlan_id:
				return
			if IP not in pkt:
				return
			src_ip = pkt[IP].src
			# 过滤自己发送的包: 检查源 MAC 是否为本地 MAC
			src_mac = pkt[Ether].src if Ether in pkt else None
			if src_mac and src_mac == self.local_mac:
				return  # 忽略自己发送的包 (L2 层精确过滤)

			# 支持 UDP 和 TCP
			udp_payload = None
			if UDP in pkt:
				udp_payload = bytes(pkt[UDP].payload)
			elif TCP in pkt:
				udp_payload = bytes(pkt[TCP].payload)
			else:
				return

			if len(udp_payload) < 16:
				return
			someip_pkt = SOMEIP(udp_payload)

			src_mac = pkt[Ether].src if Ether in pkt else None

			# SD 包 (srv_id=0xFFFF, method_id=0x8100)
			if someip_pkt.srv_id == 0xFFFF and someip_pkt.sub_id == 0x8100:
				self._handle_sd(someip_pkt, src_ip, src_mac)
			else:
				# 业务 Response / Notification / SubscribeAck
				entry = {
					"type": "response",
					"src": src_ip,
					"srv_id": someip_pkt.srv_id,
					"method_id": someip_pkt.sub_id,
					"msg_type": someip_pkt.msg_type,
					"payload": bytes(someip_pkt.payload).hex()[:120],
				}
				with self._lock:
					self._responses.append(entry)
				type_name = {0x80: "Response", 0x81: "Error", 0x02: "Notification", 0x00: "Request"}.get(someip_pkt.msg_type, f"Type=0x{someip_pkt.msg_type:02X}")
				print(f"  [Biz] Srv=0x{someip_pkt.srv_id:04X} Mth=0x{someip_pkt.sub_id:04X} {type_name} len={len(udp_payload)}")
		except Exception:
			pass

	def _handle_sd(self, someip_pkt, src_ip: str, src_mac: str = None) -> None:
		"""解析 SD Entry，提取 OfferService / SubscribeAck。"""
		try:
			if isinstance(someip_pkt.payload, SOMEIP_SD):
				sd_pkt = someip_pkt.payload
			elif hasattr(someip_pkt.payload, "load"):
				sd_pkt = SOMEIP_SD(someip_pkt.payload.load)
			else:
				return

			for entry in sd_pkt.entry_array:
				if entry.type == 0x01:  # OfferService
					svc_id = int(entry.srv_id)
					inst_id = int(getattr(entry, "inst_id", 0xFFFF))
					tcp_eps, udp_eps = [], []
					for opt in sd_pkt.option_array:
						if isinstance(opt, SDOption_IP4_EndPoint):
							ep = (opt.addr, opt.port)
							if opt.l4_proto == 0x06:
								tcp_eps.append(ep)
							elif opt.l4_proto == 0x11:
								udp_eps.append(ep)
					with self._lock:
						self._discovered[svc_id] = {
							"ip": src_ip,
							"mac": src_mac,
							"udp_eps": udp_eps,
							"tcp_eps": tcp_eps,
							"inst_id": inst_id,
						}
						self._offer_count += 1
				elif entry.type == 0x07:  # SubscribeAck
					svc_id = int(entry.srv_id)
					eg_id = getattr(entry, "eventgroup_id", 0)
					ttl = getattr(entry, "ttl", 0)
					entry_data = {
						"type": "sub_ack",
						"src": src_ip,
						"srv_id": svc_id,
						"eventgroup_id": eg_id,
						"ttl": ttl,
					}
					with self._lock:
						self._responses.append(entry_data)
					print(f"  [SubAck] Srv=0x{svc_id:04X} Grp=0x{eg_id:04X} TTL={ttl}")
		except Exception:
			pass

	# ---- 包构造与发送 ----

	def _build_vlan_pkt(self, someip_pkt, dst_mac: str, dst_ip: str, sport: int, dport: int, use_client_ip: bool = False):
		src_ip = self.client_ip if use_client_ip else self.local_ip
		return (
			Ether(src=self.local_mac, dst=dst_mac) /
			Dot1Q(vlan=self.vlan_id) /
			IP(src=src_ip, dst=dst_ip) /
			UDP(sport=sport, dport=dport) /
			someip_pkt
		)

	def _send_find_service(self, service_id: int = 0xFFFF, unicast: bool = False) -> None:
		sd = SOMEIP_SD(flags=0xC0, entry_array=[
			SDEntry_Service(type=0x00, srv_id=service_id, inst_id=0xFFFF, ttl=3)
		])
		someip_pkt = SOMEIP(
			srv_id=0xFFFF, sub_id=0x8100,
			client_id=self.client_id, session_id=self._next_session(),
			msg_type=0x02,
		) / sd
		if unicast:
			dst_ip = self.target_ip
			dst_mac = self.target_mac or "ff:ff:ff:ff:ff:ff"
		else:
			dst_ip = self.sd_mcast
			dst_mac = "01:00:5e:00:00:ff"
		pkt = self._build_vlan_pkt(someip_pkt, dst_mac, dst_ip, self.sd_port, self.sd_port)
		sendp(pkt, iface=self.iface, verbose=False)

	def _send_rpc(self, svc_id: int, method_id: int, target_port: int, payload: bytes = b"\x00",
				  src_ip: str = None, src_port: int = None, dst_ip: str = None,
				  client_id: int = None) -> None:
		"""发送 RPC Request，支持指定 Client IP/Port/目标 IP。"""
		_s_ip = src_ip or self.client_ip
		_s_port = src_port or self.client_port
		_d_ip = dst_ip or self.target_ip
		_cid = client_id if client_id is not None else self.client_id
		dst_mac = self.target_mac or "ff:ff:ff:ff:ff:ff"
		someip_pkt = SOMEIP(
			srv_id=svc_id, sub_id=method_id,
			client_id=_cid, session_id=self._next_session(),
			msg_type=0x00, retcode=0x00,
		) / payload
		pkt = self._build_vlan_pkt(
			someip_pkt, dst_mac,
			_d_ip, _s_port, target_port,
			use_client_ip=True,
		)
		# 覆盖 IP src
		pkt[IP].src = _s_ip
		sendp(pkt, iface=self.iface, verbose=False)
		print(f"    -> TX RPC: {_s_ip}:{_s_port} -> {_d_ip}:{target_port} "
			  f"svc=0x{svc_id:04X} mth=0x{method_id:04X}")

	def _send_subscribe(self, svc_id: int, eventgroup_id: int, dst_port: int = None,
					   inst_id: int = 0xFFFF, major_ver: int = 0xFF,
					   src_ip: str = None, src_port: int = None, dst_ip: str = None,
					   client_id: int = None) -> None:
		"""发送 SubscribeEventGroup。
		支持指定 Client IP/Port/目标 IP，用于多角色仿真。
		"""
		_s_ip = src_ip or self.client_ip
		_s_port = src_port or self.client_port
		_d_ip = dst_ip or self.target_ip
		_cid = client_id if client_id is not None else self.client_id
		target_port = dst_port or self.sd_port
		option = SDOption_IP4_EndPoint(
			type=0x04, addr=_s_ip, l4_proto=0x11, port=_s_port,
		)
		entry = SDEntry_EventGroup(
			type=0x06, srv_id=svc_id, inst_id=inst_id,
			major_ver=major_ver, ttl=0xFF, cnt=0, eventgroup_id=eventgroup_id,
		)
		entry.index_1 = 0
		entry.n_opt_1 = 1
		sd = SOMEIP_SD(flags=0xC0, entry_array=[entry], option_array=[option])
		someip_pkt = SOMEIP(
			srv_id=0xFFFF, sub_id=0x8100,
			client_id=_cid, session_id=self._next_session(),
			msg_type=0x02,
		) / sd
		dst_mac = self.target_mac or "ff:ff:ff:ff:ff:ff"
		pkt = self._build_vlan_pkt(
			someip_pkt, dst_mac,
			_d_ip, _s_port, target_port,
			use_client_ip=True,
		)
		pkt[IP].src = _s_ip
		sendp(pkt, iface=self.iface, verbose=False)
		print(f"    -> TX Subscribe: {_s_ip}:{_s_port} -> {_d_ip}:{target_port} "
			  f"svc=0x{svc_id:04X} inst=0x{inst_id:04X} major={major_ver} "
			  f"grp=0x{eventgroup_id:04X} dst_mac={dst_mac}")

	# ---- 测试流程 ----

	def _start_sniffer(self) -> threading.Thread:
		self._running = True
		t = threading.Thread(
			target=lambda: sniff(
				iface=self.iface, prn=self._process_packet,
				store=0, timeout=300,
			),
			daemon=True,
		)
		t.start()
		return t

	def _stop_sniffer(self) -> None:
		self._running = False

	def run(self) -> Dict[str, Any]:
		"""执行完整 VLAN SOME/IP 连通性测试。

		Returns:
			包含测试结果的字典。
		"""
		print("=" * 60)
		print("  VLAN SOME/IP 多角色连通性测试")
		print(f"  本地: {self.local_ip} (VLAN {self.vlan_id})")
		print(f"  目标 ICC: {self.target_ip}")
		print(f"  模拟 Client 身份:")
		for name, prof in self.client_profiles.items():
			print(f"    {name}: {prof['ip']}:{prof['port']} (ID=0x{prof['id']:04X})")
		print(f"  接口: {self.iface}")
		print(f"  MAC:  {self.local_mac} -> target: {self.target_mac or 'unknown'}")
		print(f"  SD:   {self.sd_mcast}:{self.sd_port}")
		print("=" * 60)

		# Phase 1: 启动 L2 监听
		print(f"\n[1] 启动 VLAN {self.vlan_id} L2 监听 ...")
		sniff_thread = self._start_sniffer()
		time.sleep(0.5)

		# Phase 2: 被动监听 SD Offer
		print(f"\n[2] 被动监听 ICC SD Offer ({self.passive_listen_sec}s) ...")
		time.sleep(self.passive_listen_sec)
		with self._lock:
			passive_count = self._offer_count
			passive_services = dict(self._discovered)
		print(f"  被动发现 {passive_count} 个 Offer, {len(passive_services)} 个服务")
		for sid in sorted(passive_services):
			svc_def = self.ICC_SERVICES.get(sid, {"name": "未知"})
			name = svc_def["name"] if isinstance(svc_def, dict) else svc_def
			info = passive_services[sid]
			print(f"    0x{sid:04X} ({name}) -> {info['ip']} UDP={info['udp_eps']} TCP={info['tcp_eps']}")

		# 自动修正: 从 Offer 中提取 ICC 实际 IP 和 MAC，更新 target
		if passive_services:
			first_svc = next(iter(passive_services.values()))
			actual_ip = first_svc["ip"]
			actual_mac = first_svc.get("mac")
			if actual_ip != self.target_ip:
				print(f"\n  [修正] ICC 实际 IP={actual_ip} (配置值={self.target_ip})，自动更新")
				self.target_ip = actual_ip
			if actual_mac and actual_mac != self.target_mac:
				print(f"  [修正] 目标 MAC 从 Offer 帧提取: {actual_mac} (原值={self.target_mac})")
				self.target_mac = actual_mac
			elif not self.target_mac:
				self._resolve_target_mac()
				print(f"  [修正] 目标 MAC 更新为: {self.target_mac or 'unknown'}")

		# Phase 3: 主动 FindService
		print(f"\n[3] 发送 FindService (组播+单播) ...")
		for _ in range(5):
			self._send_find_service(0xFFFF, unicast=False)
			self._send_find_service(0xFFFF, unicast=True)
			time.sleep(0.5)
		time.sleep(5)

		with self._lock:
			active_services = dict(self._discovered)
			total_offers = self._offer_count
		print(f"  共发现 {len(active_services)} 个服务, {total_offers} 个 Offer:")
		for sid in sorted(active_services):
			svc_def = self.ICC_SERVICES.get(sid, {"name": "未知"})
			name = svc_def["name"] if isinstance(svc_def, dict) else svc_def
			info = active_services[sid]
			print(f"    0x{sid:04X} ({name}) -> {info['ip']} UDP={info['udp_eps']} TCP={info['tcp_eps']}")

		# Phase 4: 多 Client 身份 Event 订阅测试
		print(f"\n[4] 多 Client 身份 Event 订阅测试 ...")
		sub_results = []
		for svc_id, svc_def in self.ICC_SERVICES.items():
			if svc_id not in active_services:
				continue
			name = svc_def["name"]
			events = svc_def.get("events", [])
			if not events:
				print(f"  [SKIP] 0x{svc_id:04X} ({name}) - 无事件定义")
				continue
			info = active_services[svc_id]
			actual_inst = info.get("inst_id", 0xFFFF)
			actual_major = 0x01
			evt_id, eg_id, proto = events[0]
			# 遍历所有 Client 身份订阅同一服务
			for prof_name, prof in self.client_profiles.items():
				before = len(self._responses)
				print(f"  [SUB][{prof_name}] 0x{svc_id:04X} ({name}) "
					  f"client={prof['ip']}:{prof['port']} "
					  f"inst=0x{actual_inst:04X} grp=0x{eg_id:04X}")
				# 发送 2 次
				for _ in range(2):
					self._send_subscribe(
						svc_id, eg_id, self.sd_port,
						inst_id=actual_inst, major_ver=actual_major,
						src_ip=prof["ip"], src_port=prof["port"],
						client_id=prof["id"],
					)
					time.sleep(1)
				time.sleep(3)
				after = len(self._responses)
				got_notification = after > before
				sub_results.append({
					"svc_id": svc_id, "name": name,
					"client": prof_name, "client_ip": prof["ip"],
					"eventgroup_id": eg_id,
					"notification": got_notification,
					"count": after - before,
				})
				print(f"    {'OK' if got_notification else 'NO NOTIFICATION'} (收到 {after - before} 个通知)")

		# Phase 5: 被动事件监听 (检查 ICC 是否主动推送事件)
		print(f"\n[5] 被动事件监听 (10s) ...")
		before_passive = len(self._responses)
		time.sleep(10)
		after_passive = len(self._responses)
		passive_events = after_passive - before_passive
		if passive_events > 0:
			print(f"  收到 {passive_events} 个被动事件通知!")
		else:
			print(f"  未收到任何被动事件通知")
			print(f"  (ICC 可能处于预运行状态，仅发送 SD Offer 但不推送事件数据)")

		# Phase 6: RPC 测试 (仅对有 RPC 方法的服务)
		print(f"\n[6] RPC 连通性测试 ...")
		rpc_results = []
		has_rpc = any(svc_def.get("rpcs") for svc_def in self.ICC_SERVICES.values())
		if not has_rpc:
			print("  所有服务均无 RPC 方法定义 (全部为 Event 类型)")
		for svc_id, svc_def in self.ICC_SERVICES.items():
			if svc_id not in active_services:
				continue
			name = svc_def["name"]
			rpcs = svc_def.get("rpcs", [])
			if not rpcs:
				continue
			info = active_services[svc_id]
			target_port = info["udp_eps"][0][1] if info["udp_eps"] else self.biz_port
			for method_id, proto in rpcs:
				before = len(self._responses)
				print(f"  [RPC] 0x{svc_id:04X} ({name}) Method=0x{method_id:04X} -> {self.target_ip}:{target_port}")
				self._send_rpc(svc_id, method_id, target_port)
				time.sleep(self.rpc_wait_sec)
				got_response = len(self._responses) > before
				rpc_results.append({"svc_id": svc_id, "name": name, "response": got_response})
				print(f"    {'OK' if got_response else 'NO RESPONSE'}")

		# Phase 7: 模拟 ICC 作为 Client 向外部 Server 发起订阅
		print(f"\n[7] 模拟 ICC 作为 Client 向外部 Server (TBOX) 发起订阅 ...")
		ext_results = []
		for svc_id, ext_def in self.EXTERNAL_SERVER_SERVICES.items():
			name = ext_def["name"]
			events = ext_def.get("events", [])
			if not events:
				continue
			evt_id, eg_id, proto = events[0]
			before = len(self._responses)
			print(f"  [EXT] 0x{svc_id:04X} ({name}) "
				  f"Server={ext_def['server_ip']}:{ext_def['server_port']} "
				  f"Client(ICC)={ext_def['client_ip']}:{ext_def['client_port']}")
			# 发送 FindService 单播到外部 Server
			for _ in range(3):
				self._send_find_service(svc_id, unicast=True)
				time.sleep(0.3)
			time.sleep(2)
			# 发送 Subscribe
			for _ in range(2):
				self._send_subscribe(
					svc_id, eg_id, self.sd_port,
					inst_id=0x0001, major_ver=0x01,
					src_ip=ext_def["client_ip"],
					src_port=ext_def["client_port"],
					dst_ip=ext_def["server_ip"],
				)
				time.sleep(1)
			time.sleep(3)
			after = len(self._responses)
			got_response = after > before
			ext_results.append({
				"svc_id": svc_id, "name": name,
				"server": ext_def["server_ip"],
				"response": got_response, "count": after - before,
			})
			print(f"    {'OK' if got_response else 'NO RESPONSE'} (收到 {after - before} 个回复)")

		# Phase 8: 总结
		self._stop_sniffer()
		time.sleep(0.5)

		print(f"\n{'=' * 60}")
		print(f"  测试总结")
		print(f"{'=' * 60}")
		print(f"  被动发现: {len(passive_services)} 个服务")
		print(f"  主动发现: {len(active_services)} 个服务")
		print(f"  SD Offer: {total_offers} 个")
		print(f"  被动事件: {passive_events} 个")
		if sub_results:
			sub_ok = sum(1 for r in sub_results if r["notification"])
			print(f"  多 Client 事件订阅: {sub_ok}/{len(sub_results)} 收到通知")
			for r in sub_results:
				state = "OK" if r["notification"] else "FAIL"
				print(f"    [{state}] [{r['client']:4s}] 0x{r['svc_id']:04X} ({r['name']}) "
					  f"Group=0x{r['eventgroup_id']:04X} 通知数={r['count']}")
		else:
			print(f"  事件订阅: 未执行")
		if rpc_results:
			print(f"  RPC 回复: {sum(1 for r in rpc_results if r['response'])}/{len(rpc_results)}")
		if ext_results:
			ext_ok = sum(1 for r in ext_results if r["response"])
			print(f"  外部 Server 订阅: {ext_ok}/{len(ext_results)} 收到回复")
			for r in ext_results:
				state = "OK" if r["response"] else "FAIL"
				print(f"    [{state}] 0x{r['svc_id']:04X} ({r['name']}) "
					  f"Server={r['server']} 回复数={r['count']}")
		print(f"\n  已发现 ICC 服务:")
		for sid, info in sorted(active_services.items()):
			svc_def = self.ICC_SERVICES.get(sid, {"name": "未知"})
			name = svc_def["name"] if isinstance(svc_def, dict) else svc_def
			print(f"    0x{sid:04X} ({name}): UDP={info['udp_eps']} TCP={info['tcp_eps']}")
		print(f"{'=' * 60}")

		return {
			"passive_services": passive_services,
			"active_services": active_services,
			"total_offers": total_offers,
			"passive_events": passive_events,
			"sub_results": sub_results,
			"rpc_results": rpc_results,
			"ext_results": ext_results,
			"all_responses": self._responses,
		}


def vlan_main() -> int:
	"""VLAN SOME/IP 测试主入口。直接运行 python someip.py --vlan 调用。"""

	logging.getLogger().setLevel(logging.INFO)
	try:
		runner = VLANSomeIPTestRunner(
			target_ip="192.168.62.129",
			vlan_id=62,
			sd_mcast="239.0.0.255",
		)
		result = runner.run()
		return 0 if result["active_services"] else 1
	except RuntimeError as exc:
		logger.error("VLAN 测试失败: %s", exc)
		return 1
	except KeyboardInterrupt:
		logger.info("用户中断")
		return 130


if __name__ == "__main__":
	raise SystemExit(main())
