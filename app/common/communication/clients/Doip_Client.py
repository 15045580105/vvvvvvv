#!/usr/bin/env python3
"""
DoIP客户端实现
支持网口选择、连接管理和DoIP报文收发
基于python-doipclient库实现
"""

import socket
import psutil
from doipclient import DoIPClient
from doipclient.messages import RoutingActivationRequest
import logging
import time
from typing import Optional, Tuple, List
from typing import Any, Union

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DoIPClientHandler:
    """
    DoIP客户端处理器，支持网口选择和连接管理
    """

    def __init__(self):
        self.doip_client: Optional[DoIPClient] = None
        self.connected = False
        self.interface_ip = None
        # 新增：本机(测试器)逻辑地址/源地址，默认0x0E80，可由外部修改
        self.client_logical_address: int = 0x0E80

    def get_network_interfaces(self) -> List[Tuple[str, str]]:
        """
        获取可用的网络接口列表
        返回: [(接口名称, IP地址)]
        """
        interfaces = []
        for interface_name, addresses in psutil.net_if_addrs().items():
            for addr in addresses:
                if addr.family == socket.AF_INET and not addr.address.startswith('127.'):
                    interfaces.append((interface_name, addr.address))
        return interfaces

    def select_network_interface(self, interface_ip: str = None) -> bool:
        """
        选择网络接口
        Args:
            interface_ip: 指定的接口IP地址，如果为None则自动选择
        Returns:
            bool: 选择是否成功
        """
        interfaces = self.get_network_interfaces()

        if not interfaces:
            logger.error("未找到可用的网络接口")
            return False

        # 优先策略：如果调用方指定了 interface_ip，则按指定匹配
        if interface_ip:
            for iface_name, ip_addr in interfaces:
                if ip_addr == interface_ip:
                    self.interface_ip = interface_ip
                    logger.info(f"已选择接口: {iface_name} ({interface_ip})")
                    return True
            logger.error(f"未找到IP地址为 {interface_ip} 的网络接口")
            return False
        else:
            # 首选IP或接口名（按用户要求：以太网4 -> 10.1.0.99）
            preferred_ips = ["10.1.0.99"]
            preferred_names = ["以太网4", "Ethernet 4"]

            # 先按首选IP查找
            for iface_name, ip_addr in interfaces:
                if ip_addr in preferred_ips:
                    self.interface_ip = ip_addr
                    logger.info(f"已选择首选接口: {iface_name} ({ip_addr})")
                    return True

            # 再按接口名匹配（包含匹配）
            for iface_name, ip_addr in interfaces:
                for pname in preferred_names:
                    if pname in iface_name:
                        self.interface_ip = ip_addr
                        logger.info(f"已选择首选接口: {iface_name} ({ip_addr})")
                        return True

            # 回退到原有自动选择（第一个非回环接口）
            iface_name, ip_addr = interfaces[0]
            self.interface_ip = ip_addr
            logger.info(f"自动选择接口: {iface_name} ({ip_addr})")
            return True

    def connect(self, ecu_ip: str, ecu_logical_address: int = 0x004F,
                tcp_port: int = 13400, activation_type: Any = RoutingActivationRequest.ActivationType.Default,
                protocol_version: int = 0x02,
                client_logical_address: Optional[int] = 0x0E80) -> bool:
        """连接到DoIP服务器(ECU)
        Args:
            ecu_ip: ECU的IP地址
            ecu_logical_address: ECU逻辑地址(目标地址)
            tcp_port: TCP端口号
            activation_type: 路由激活类型
            protocol_version: DoIP协议版本
            client_logical_address: 本机(测试器)逻辑地址/源地址，None时使用handler中保存的值
        Returns:
            bool: 连接是否成功
        """
        try:
            if not self.interface_ip:
                if not self.select_network_interface():
                    return False

            # 如果调用方没有传，则使用 handler 中的默认值
            if client_logical_address is None:
                client_logical_address = self.client_logical_address
            else:
                # 同步到 handler 字段，方便后续查看
                self.client_logical_address = client_logical_address

            logger.info(
                f"正在连接到ECU: {ecu_ip}:{tcp_port}, 目标地址(ECU逻辑地址): 0x{ecu_logical_address:04X}, 本机源地址: 0x{client_logical_address:04X}"
            )

            # 创建DoIP客户端实例，同时显式指定客户端逻辑地址(源地址)
            self.doip_client = DoIPClient(
                ecu_ip_address=ecu_ip,
                ecu_logical_address=ecu_logical_address,
                tcp_port=tcp_port,
                client_ip_address=self.interface_ip,  # 绑定到指定网口
                activation_type=activation_type,
                protocol_version=protocol_version,
                auto_reconnect_tcp=True,
                client_logical_address=client_logical_address,
            )

            # 测试连接
            logger.info("执行路由激活...")
            # Ensure activation_type is of correct enum type if possible
            try:
                if not isinstance(activation_type, RoutingActivationRequest.ActivationType):
                    activation_type = RoutingActivationRequest.ActivationType(activation_type)
            except Exception:
                # leave as-is; the underlying library may accept int or enum
                pass
            activation_response = self.doip_client.request_activation(activation_type)
            logger.info(f"路由激活响应: {activation_response}")

            # 获取实体状态验证连接
            entity_status = self.doip_client.request_entity_status()
            logger.info(f"实体状态: {entity_status}")

            self.connected = True
            logger.info("DoIP连接建立成功")
            return True

        except Exception as e:
            logger.error(f"连接失败: {str(e)}")
            self.connected = False
            return False

    def send_doip_message(self, payload: bytes, timeout: float = 1.0, *, response_index: Optional[int] = None,
                          target_did: Optional[int] = None, prefer_last: bool = False, return_all: bool = False) -> Union[Optional[bytes], List[bytes]]:
        """
        发送DoIP诊断报文并接收响应
        Args:
            payload: 诊断负载数据
            timeout: 超时时间(秒)
            response_index: 如果对方返回多条消息，可指定索引（支持负数，-1 为最后一条），None 表示按智能匹配选择
            target_did: 如果期望某个 DID 的响应，传入 DID（如 0xF180），函数会在多响应中尝试匹配
            prefer_last: 如果为 True，在未指定其他匹配条件时优先返回最后一条响应（许多实现把重要响应放在后面）
            return_all: 是否返回所有归一化响应，默认为 False
        Returns:
            bytes: 响应数据，失败返回None
        """
        if not self.connected or not self.doip_client:
            logger.error("客户端未连接")
            return None

        try:
            logger.info(f"发送DoIP报文: {payload.hex()}")
            # 首先等待 Positive ACK，但不占用全部 timeout（给后续实际 DiagnosticMessage 留出时间）
            ack_timeout = min(0.5, timeout) if timeout else 0.5
            try:
                self.doip_client.send_diagnostic(bytearray(payload), timeout=ack_timeout)
            except TimeoutError:
                logger.warning("send_diagnostic 超时（未收到 Positive ACK）")
                # 仍然尝试接收诊断消息（有些 ECUs 可能不发 ACK 但直接返回数据）
            except IOError as e:
                logger.error(f"send_diagnostic 返回 IO 错误: {e}")
                return None if not return_all else []

            # 发送后在 timeout 窗口内循环接收 DiagnosticMessage，以收集多条回复
            start_recv = time.time()
            responses = []
            while True:
                elapsed = time.time() - start_recv
                if timeout and elapsed >= timeout:
                    break
                remaining = timeout - elapsed if timeout else None
                try:
                    resp = self.doip_client.receive_diagnostic(timeout=remaining)
                    
                    # 记录类型与 repr 便于调试
                    logger.debug(f"receive_diagnostic 返回: type={type(resp)}, repr={repr(resp)}")
                    # 若能拿到内部 parser 缓冲也打印，帮助定位解析问题
                    try:
                        if hasattr(self.doip_client, '_tcp_parser'):
                            buf = getattr(self.doip_client._tcp_parser, 'rx_buffer', None)
                            if buf:
                                logger.debug(f"_tcp_parser.rx_buffer (hex): {bytes(buf).hex()}")
                    except Exception:
                        pass

                    flattened = self._flatten_responses(resp)
                    if flattened:
                        responses.extend(flattened)
                        break
                    # 继续循环，直到 timeout
                except TimeoutError:
                    # 没有更多响应，退出循环
                    break

            # 去重（按接收顺序保留）并保持顺序
            seen = set()
            uniq_responses = []
            for r in responses:
                if r not in seen:
                    seen.add(r)
                    uniq_responses.append(r)
            responses = uniq_responses

            # 再次去重
            seen = set()
            uniq_responses = []
            for r in responses:
                if r not in seen:
                    seen.add(r)
                    uniq_responses.append(r)
            responses = uniq_responses

            logger.info(f"收到 {len(responses)} 条归一化响应 (bytes)")
            for i, r in enumerate(responses):
                logger.info(f"  [{i}] {r.hex()}")

            selected = None

            # 1) 如果指定了 target_did，优先查找能成功解析且 DID 匹配的响应
            if target_did is not None and responses:
                for r in responses:
                    parsed = parse_read_did_response(r, target_did)
                    if parsed.get("ok"):
                        selected = r
                        logger.info(f"按 target_did 匹配到响应: {r.hex()}")
                        break

            # 2) 如果指定了 response_index，则按索引选择
            if selected is None and response_index is not None and responses:
                try:
                    selected = responses[response_index]
                    logger.info(f"按 response_index={response_index} 选中响应: {selected.hex()}")
                except Exception:
                    logger.warning(f"response_index={response_index} 超出范围")

            # 3) 若未指定，且 prefer_last 为 True，则返回最后一条
            if selected is None and prefer_last and responses:
                selected = responses[-1]
                logger.info("优先选择最后一条响应")

            # 4) 回退到默认（第一条），如果存在
            if selected is None and responses:
                selected = responses[0]
                logger.info("回退选择第一条响应")

            if selected is None:
                logger.info("未收到可解析的响应")
                return None if not return_all else []

            if return_all:
                return responses

            return selected

        except Exception as e:
            logger.error(f"发送DoIP报文失败: {str(e)}")
            return None

    def _normalize_response(self, raw_response) -> Optional[bytes]:
        """将 doipclient 返回的各种格式归一化为 bytes 或 None"""
        if raw_response is None:
            return None

        # 1. 处理 doipclient 特定的消息对象
        if hasattr(raw_response, 'user_data'):
            # DiagnosticMessage 等类型的响应，user_data 包含实际诊断数据
            user_data = getattr(raw_response, 'user_data')
            return self._normalize_response(user_data)

        # 2. 处理 DoIP 消消息负载
        if hasattr(raw_response, 'payload'):
            payload = getattr(raw_response, 'payload')
            normalized = self._normalize_response(payload)
            if normalized is not None:
                return normalized

        # 3. 处理 DoIP 响应对象（如 RoutingActivationResponse）
        if hasattr(raw_response, 'response_code') and hasattr(raw_response, 'data'):
            # 这类对象通常包含响应代码和附加数据
            response_code = getattr(raw_response, 'response_code')
            data = getattr(raw_response, 'data', b'')
            # 将响应代码和数据组合成字节序列
            result = bytes([response_code]) + data
            return result if result else None

        # 4. 处理标准的字节类型
        if isinstance(raw_response, (bytes, bytearray)):
            return bytes(raw_response)

        if isinstance(raw_response, memoryview):
            return raw_response.tobytes()

        # 5. 处理列表/元组
        if isinstance(raw_response, (list, tuple)):
            # 保持旧行为，返回第一个可解析的元素（向后兼容）
            for item in raw_response:
                normalized = self._normalize_response(item)
                if normalized is not None:
                    return normalized
            return None

        # 6. 最后尝试转换为字节
        try:
            return bytes(raw_response)
        except (TypeError, ValueError):
            logger.warning(f"无法解析的响应类型: {type(raw_response)}, 值: {raw_response}")
            return None

    def _flatten_responses(self, raw_response) -> list:
        """将可能的嵌套响应结构展平为 bytes 列表

        目的:
        - 有的 doipclient 实现会返回 list/tuple、或消息对象列表
        - 我们需要获取到特定序号或包含 UDS 的那一条响应
        """
        results = []
        if raw_response is None:
            return results

        # 递归处理不同类型
        if hasattr(raw_response, 'user_data'):
            return self._flatten_responses(getattr(raw_response, 'user_data'))

        if hasattr(raw_response, 'payload'):
            return self._flatten_responses(getattr(raw_response, 'payload'))

        if hasattr(raw_response, 'response_code') and hasattr(raw_response, 'data'):
            response_code = getattr(raw_response, 'response_code')
            data = getattr(raw_response, 'data', b'')
            r = bytes([response_code]) + data
            return [r]

        if isinstance(raw_response, (bytes, bytearray)):
            return [bytes(raw_response)]

        if isinstance(raw_response, memoryview):
            return [raw_response.tobytes()]

        if isinstance(raw_response, (list, tuple)):
            for item in raw_response:
                results.extend(self._flatten_responses(item))
            return results

        # 最后尝试直接转换为 bytes
        try:
            b = bytes(raw_response)
            return [b]
        except Exception:
            logger.warning(f"无法展平响应类型: {type(raw_response)}, 值: {raw_response}")
            return []

    def disconnect(self):
        """断开连接"""
        if self.doip_client:
            try:
                self.doip_client.close()
                logger.info("DoIP连接已关闭")
            except Exception as e:
                logger.error(f"关闭连接时出错: {str(e)}")
            finally:
                self.doip_client = None
                self.connected = False

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.connected and self.doip_client is not None

    def _dump_socket_and_parser_state(self):
        """调试帮助：打印 socket 与 parser 的状态（非破坏性）"""
        try:
            if self.doip_client is None:
                logger.debug("doip_client is None")
                return
            try:
                if hasattr(self.doip_client, '_tcp_sock') and self.doip_client._tcp_sock is not None:
                    try:
                        local = self.doip_client._tcp_sock.getsockname()
                        peer = self.doip_client._tcp_sock.getpeername()
                        logger.debug(f"TCP socket local={local} peer={peer} timeout={self.doip_client._tcp_sock.gettimeout()}")
                    except Exception as e:
                        logger.debug(f"读取 TCP socket 信息失败: {e}")
            except Exception:
                pass

            try:
                if hasattr(self.doip_client, '_tcp_parser') and self.doip_client._tcp_parser is not None:
                    buf = getattr(self.doip_client._tcp_parser, 'rx_buffer', None)
                    if buf:
                        logger.debug(f"_tcp_parser.rx_buffer (len={len(buf)}): {bytes(buf).hex()}")
                    else:
                        logger.debug("_tcp_parser.rx_buffer empty or not present")
            except Exception as e:
                logger.debug(f"读取 parser 状态失败: {e}")
        except Exception:
            pass


def parse_read_did_response(response: bytes, did: int) -> dict:
    """简单解析 ReadDataByIdentifier 响应，用于调试输出.

    Args:
        response: 原始UDS响应数据
        did: 请求的DID(例如 0xF180)
    Returns:
        dict: {"ok": bool, "reason": str, "service": int, "did": int, "data": bytes, "raw": bytes}
    """
    result = {
        "ok": False,
        "reason": "未知错误",
        "service": None,
        "did": did,
        "data": b"",
        "raw": response,
    }

    if response is None:
        result["reason"] = "无响应(超时或连接异常)"
        return result

    if len(response) < 3:
        result["reason"] = f"响应长度过短: {len(response)} 字节"
        return result

    # 尝试查找UDS服务字节(0x62或0x7F)，以适应不同的DoIP库响应格式
    uds_service_offset = 0
    if response[0] == 0x62:
        uds_service_offset = 0
    elif response[0] == 0x7F and len(response) >= 3:
        uds_service_offset = 2  # 跳过负响应的原服务和NRC
    else:
        # 尝试在数据中查找0x62或0x7F
        for i in range(min(8, len(response))):
            if response[i] == 0x62:
                uds_service_offset = i
                break
            if response[i] == 0x7F and len(response) > i + 2:
                uds_service_offset = i + 2
                break

    # 提取服务ID
    service = response[uds_service_offset]
    result["service"] = service

    # 负响应 0x7F
    if service == 0x7F:
        if len(response) >= uds_service_offset + 3:
            orig_service = response[uds_service_offset + 1]
            nrc = response[uds_service_offset + 2]
            result["reason"] = f"负响应, 原服务: 0x{orig_service:02X}, NRC: 0x{nrc:02X}"
        else:
            result["reason"] = "负响应格式错误"
        return result

    # 正响应应为 0x22 + 0x40 = 0x62
    if service != 0x62:
        result["reason"] = f"未知服务ID: 0x{service:02X}"
        return result

    # 提取DID
    did_high = (did >> 8) & 0xFF
    did_low = did & 0xFF
    if response[uds_service_offset + 1] != did_high or response[uds_service_offset + 2] != did_low:
        result["reason"] = (
            f"DID不匹配, 期望: 0x{did:04X}, 实际: 0x{response[uds_service_offset + 1]:02X}{response[uds_service_offset + 2]:02X}"
        )
        return result

    # 提取数据
    data = response[uds_service_offset + 3:]
    result["data"] = data
    result["ok"] = True
    result["reason"] = "成功"
    return result


def test_connection():
    """测试连接功能: 建立DoIP连接并读取 DID F180"""
    print("=" * 50)
    print("DoIP客户端测试 - 读取DID F180")
    print("=" * 50)

    # 创建客户端实例
    client_handler = DoIPClientHandler()

    # 显示可用网络接口
    interfaces = client_handler.get_network_interfaces()
    print("可用的网络接口:")
    for i, (iface_name, ip_addr) in enumerate(interfaces):
        print(f"  {i + 1}. {iface_name}: {ip_addr}")

    if not interfaces:
        print("未找到可用的网络接口")
        return

    # 选择接口（优先使用以太网4 / 10.1.0.99）
    if client_handler.select_network_interface():
        print(f"已选择接口: {client_handler.interface_ip}")
    else:
        print("接口选择失败")
        return

    # 测试连接参数（这些参数需要根据实际ECU配置修改）
    test_ecu_ip = "10.1.0.79"   # ECU IP(目标IP)
    test_target_logical_address = 0x004F  # ECU 逻辑地址(目标地址)
    test_source_logical_address = 0x0E80  # 本机测试器逻辑地址(源地址)，现在可配置

    print(f"\n测试连接参数:")
    print(f"  ECU IP: {test_ecu_ip}")
    print(f"  目标逻辑地址(ECU): 0x{test_target_logical_address:04X}")
    print(f"  源逻辑地址(Tester): 0x{test_source_logical_address:04X}")
    print(f"  本地接口: {client_handler.interface_ip}")

    try:
        # 尝试连接时同时指定目标地址和源地址
        if client_handler.connect(
            test_ecu_ip,
            test_target_logical_address,
            client_logical_address=test_source_logical_address,
        ):
            print("✓ 连接测试成功")

            # 发送 ReadDataByIdentifier 0xF180
            did = 0xF180
            read_did_msg = bytes([0x22, 0xF1, 0x80])
            print(f"\n发送读取DID F180请求: {read_did_msg.hex()}")

            response = client_handler.send_doip_message(read_did_msg, timeout=3.0)
            if response:
                print(f"原始响应: {response.hex()}")
            else:
                print("未收到响应或超时")

            # 解析响应
            parsed = parse_read_did_response(response, did)
            if parsed["ok"]:
                data = parsed["data"]
                print("✓ 读取DID F180成功")
                print(f"  数据长度: {len(data)} 字节")
                print(f"  数据(HEX): {data.hex()}")
                # 尝试按ASCII打印一份，方便查看是否为可读字符串
                try:
                    ascii_str = data.decode("ascii")
                    # 只在大部分为可见字符时输出
                    if any(32 <= ord(c) <= 126 for c in ascii_str):
                        print(f"  数据(ASCII): {ascii_str}")
                except Exception:
                    pass
            else:
                print("✗ 读取DID F180失败")
                print(f"  原因: {parsed['reason']}")
                if parsed["raw"] is not None:
                    try:
                        print(f"  原始数据: {parsed['raw'].hex()}")
                    except Exception:
                        print("  原始数据无法以HEX显示")
        else:
            print("✗ 连接测试失败")

    except Exception as e:
        print(f"测试过程中发生错误: {str(e)}")
        print("请检查:")
        print("  1. ECU IP地址是否正确")
        print("  2. 网络连接是否正常")
        print("  3. ECU是否支持DoIP协议和DID F180")
        print("  4. 防火墙设置是否允许连接")

    finally:
        # 断开连接
        client_handler.disconnect()
        print("\n测试完成")


def interactive_test():
    """交互式测试功能"""
    client_handler = DoIPClientHandler()

    print("交互式DoIP客户端")
    print("可用命令: connect, send, readf180, disconnect, status, interfaces, exit")

    while True:
        try:
            cmd = input("\n> ").strip().lower()

            if cmd == "exit":
                break

            elif cmd == "interfaces":
                interfaces = client_handler.get_network_interfaces()
                for i, (iface_name, ip_addr) in enumerate(interfaces):
                    print(f"  {i + 1}. {iface_name}: {ip_addr}")

            elif cmd == "connect":
                ecu_ip = input("ECU IP地址: ").strip()
                logical_addr = input("目标逻辑地址(ECU, 16进制, 如0x004F): ").strip()
                source_addr = input("源逻辑地址(Tester, 16进制, 回车使用默认0x0E80): ").strip()
                interface_ip = input("本地接口IP(回车自动选择): ").strip() or None

                if interface_ip:
                    client_handler.select_network_interface(interface_ip)

                try:
                    target_logical_addr_int = int(logical_addr, 16)
                    if source_addr:
                        source_logical_addr_int = int(source_addr, 16)
                    else:
                        source_logical_addr_int = client_handler.client_logical_address

                    if client_handler.connect(
                        ecu_ip,
                        target_logical_addr_int,
                        client_logical_address=source_logical_addr_int,
                    ):
                        print("连接成功")
                    else:
                        print("连接失败")
                except ValueError:
                    print("逻辑地址格式错误")

            elif cmd == "send":
                if not client_handler.is_connected():
                    print("未连接，请先执行connect命令")
                    continue

                hex_str = input("输入16进制报文(如3E00): ").strip()
                try:
                    payload = bytes.fromhex(hex_str.replace(" ", ""))
                    response = client_handler.send_doip_message(payload)
                    if response:
                        print(f"响应: {response.hex()}")
                    else:
                        print("无响应或超时")
                except ValueError:
                    print("报文格式错误")

            elif cmd == "sendall":
                # 发送并列出所有归一化响应，便于查看第N条
                if not client_handler.is_connected():
                    print("未连接，请先执行connect命令")
                    continue
                hex_str = input("输入16进制报文(如22F180): ").strip()
                try:
                    payload = bytes.fromhex(hex_str.replace(" ", ""))
                    responses = client_handler.send_doip_message(payload, timeout=5.0, return_all=True)
                    if responses:
                        print(f"收到 {len(responses)} 条响应:")
                        for i, r in enumerate(responses):
                            try:
                                s = r.hex() if isinstance(r, (bytes, bytearray, memoryview)) else repr(r)
                            except Exception:
                                s = repr(r)
                            print(f"  [{i}] {s}")
                    else:
                        print("未收到响应或超时")
                except ValueError:
                    print("报文格式错误")

            elif cmd == "readf180":
                if not client_handler.is_connected():
                    print("未连接，请先执行connect命令")
                    continue

                did = 0xF180
                payload = bytes([0x22,0xF1,0x80])
                print(f"发送读取DID F180请求: {payload.hex()}")
                response = client_handler.send_doip_message(payload, timeout=3.0)
                if response:
                    print(f"原始响应: {response.hex()}")
                else:
                    print("未收到响应或超时")

                parsed = parse_read_did_response(response, did)
                if parsed["ok"]:
                    data = parsed["data"]
                    print("✓ 读取DID F180成功")
                    print(f"  数据长度: {len(data)} 字节")
                    print(f"  数据(HEX): {data.hex()}")
                    try:
                        ascii_str = data.decode("ascii")
                        if any(32 <= ord(c) <= 126 for c in ascii_str):
                            print(f"  数据(ASCII): {ascii_str}")
                    except Exception:
                        pass
                else:
                    print("✗ 读取DID F180失败")
                    print(f"  原因: {parsed['reason']}")
                    if parsed["raw"] is not None:
                        try:
                            print(f"  原始数据: {parsed['raw'].hex()}")
                        except Exception:
                            print("  原始数据无法以HEX显示")

            elif cmd == "disconnect":
                client_handler.disconnect()
                print("已断开连接")

            elif cmd == "status":
                print(f"连接状态: {'已连接' if client_handler.is_connected() else '未连接'}")
                if client_handler.interface_ip:
                    print(f"使用接口: {client_handler.interface_ip}")
                # 新增：打印当前源/目标逻辑地址
                try:
                    if client_handler.doip_client is not None:
                        print(f"源逻辑地址(Tester): 0x{client_handler.client_logical_address:04X}")
                except Exception:
                    pass

            elif cmd == "help":
                print("connect - 连接到ECU")
                print("send - 发送DoIP报文")
                print("readf180 - 读取DID F180 (22 F1 80)")
                print("disconnect - 断开连接")
                print("status - 查看连接状态")
                print("interfaces - 显示网络接口")
                print("exit - 退出")

            else:
                print("未知命令，输入help查看帮助")

        except KeyboardInterrupt:
            print("\n退出交互模式")
            break
        except Exception as e:
            print(f"错误: {str(e)}")

    client_handler.disconnect()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DoIP客户端工具")
    parser.add_argument("--test", action="store_true", help="运行连接测试")
    parser.add_argument("--interactive", action="store_true", help="交互模式")

    args = parser.parse_args()

    if args.interactive:
        interactive_test()
    else:
        test_connection()