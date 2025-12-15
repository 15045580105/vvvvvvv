#!/usr/bin/env python3
"""
使用 Scapy 实现的 SOME/IP 客户端
支持:
- 服务发现 (FindService, SubscribeEventGroup)
- 发送请求 (Request)
- 接收响应/通知 (Response/Notification)
"""

import socket
import threading
import time
import logging
from typing import Callable, Dict, List

# Scapy 2.6.1+ 推荐的导入方式
# 确保加载了 automotive.someip 模块
from scapy.config import conf
conf.contribs['automotive.someip'] = True
from scapy.contrib.automotive.someip import (
    SOMEIP,
    SD as SOMEIP_SD,
    SDEntry_Service,
    SDEntry_EventGroup,
    SDOption_IP4_EndPoint
)

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SomeIPClient")

class SomeIPClient:
    """
    SOME/IP 客户端类，处理 SOME/IP 消息的发送和接收，以及服务发现 (SD) 消息。
    """

    SD_MULTICAST_IP = "239.255.0.1"
    SD_MULTICAST_PORT = 30490

    def __init__(self, local_ip: str, local_port: int = 0, interface: str = None,
                 multicast_ip: str = SD_MULTICAST_IP, multicast_port: int = SD_MULTICAST_PORT):
        """
        初始化 SOME/IP 客户端。

        :param local_ip: 本地绑定的 IP 地址
        :param local_port: 本地绑定的端口 (默认为 0，表示由操作系统自动分配随机端口)
        :param interface: 网络接口名称 (可选)
        :param multicast_ip: SD 组播 IP
        :param multicast_port: SD 组播端口
        """
        self.local_ip = local_ip
        self.local_port = local_port
        self.interface = interface
        self.multicast_ip = multicast_ip
        self.multicast_port = multicast_port

        # 自动管理的 Socket
        self.udp_socket = None # 用于 SD 和 UDP 通信
        self.tcp_socket = None # 用于 TCP 通信 (按需建立)
        self.use_tcp = False   # 标记是否使用 TCP

        self.client_id = 0x1234
        self.session_id = 1

        self.running = False
        self.recv_thread = None
        self.tcp_recv_thread = None

        # 回调函数字典
        # Key: (service_id, method_id) -> Value: callback_function(packet)
        self.message_callbacks: Dict[tuple, Callable] = {}
        self.sd_callbacks: List[Callable] = []

    def start(self):
        """初始化 Socket 并启动接收线程。"""
        try:
            # 默认始终创建 UDP Socket，因为服务发现 (SD) 依赖 UDP
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_socket.bind((self.local_ip, self.local_port))

            # 如果指定了本地 IP，设置组播出口接口，确保 SD 报文从正确网口发出
            if self.local_ip and self.local_ip != "0.0.0.0":
                try:
                    self.udp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(self.local_ip))
                    logger.info(f"已设置组播出口接口为: {self.local_ip}")
                except Exception as e:
                    logger.warning(f"设置组播出口接口失败 (可能不影响单播): {e}")

            # 如果端口为 0，获取实际分配的端口
            if self.local_port == 0:
                self.local_port = self.udp_socket.getsockname()[1]

            self.running = True
            # 启动 UDP 接收线程
            self.recv_thread = threading.Thread(target=self._receive_loop_udp, daemon=True)
            self.recv_thread.start()

            logger.info(f"SomeIPClient 已启动 (UDP)，监听地址: {self.local_ip}:{self.local_port}")
            return True
        except Exception as e:
            logger.error(f"启动客户端失败: {e}")
            return False

    def stop(self):
        """停止客户端。"""
        self.running = False

        # 关闭 UDP
        if self.udp_socket:
            self.udp_socket.close()

        # 关闭 TCP
        if self.tcp_socket:
            try:
                self.tcp_socket.shutdown(socket.SHUT_RDWR)
                self.tcp_socket.close()
            except Exception:
                pass

        if self.recv_thread and self.recv_thread.is_alive():
            self.recv_thread.join(timeout=1.0)
        if self.tcp_recv_thread and self.tcp_recv_thread.is_alive():
            self.tcp_recv_thread.join(timeout=1.0)

        logger.info("SomeIPClient 已停止")

    def _receive_loop_udp(self):
        """接收 UDP 数据包并解析的循环。"""
        while self.running:
            try:
                # 阻塞接收
                data, addr = self.udp_socket.recvfrom(4096)
                self._process_packet(data, addr)
            except socket.timeout:
                continue
            except OSError:
                # Socket 已关闭
                break
            except Exception as e:
                logger.error(f"UDP 接收循环发生错误: {e}")

    def _receive_loop_tcp(self):
        """接收 TCP 数据包并解析的循环。"""
        logger.info("TCP 接收线程已启动")
        while self.running and self.tcp_socket:
            try:
                # TCP 是流式协议，这里简化处理，假设每次 recv 都能收到完整的包或者包的一部分
                # 实际生产环境需要处理粘包/拆包，通常基于 SOME/IP 头部长度字段
                # 这里为了演示，读取一个较大的缓冲区
                data = self.tcp_socket.recv(4096)
                if not data:
                    logger.info("TCP 连接被对端关闭")
                    self.tcp_socket.close()
                    self.tcp_socket = None
                    self.use_tcp = False
                    break

                # 获取对端地址用于日志
                try:
                    addr = self.tcp_socket.getpeername()
                except:
                    addr = ("TCP_Server", 0)

                self._process_packet(data, addr)
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as e:
                logger.error(f"TCP 接收循环发生错误: {e}")
                break

    def _process_packet(self, data: bytes, addr):
        """解析并路由数据包。"""
        try:
            # 解析为 SOME/IP 包
            pkt = SOMEIP(data)

            # 检查是否为服务发现 (SD) 数据包
            # SD 使用 Service ID 0xFFFF 和 Method ID 0x8100
            if pkt.srv_id == 0xFFFF and pkt.sub_id == 0x8100:
                self._handle_sd_packet(pkt, addr)
            else:
                self._handle_someip_packet(pkt, addr)

        except Exception as e:
            logger.debug(f"无法解析来自 {addr} 的数据包: {e}")

    def _handle_someip_packet(self, pkt: SOMEIP, addr):
        """处理普通 SOME/IP 消息。"""
        logger.info(f"收到 SOME/IP 消息来自 {addr}: Service=0x{pkt.srv_id:04X}, Method=0x{pkt.sub_id:04X}")

        # 分发给回调函数
        key = (pkt.srv_id, pkt.sub_id)
        if key in self.message_callbacks:
            self.message_callbacks[key](pkt)

    def _handle_sd_packet(self, pkt: SOMEIP, addr):
        """处理 SD 消息。"""
        try:
            # 解析 Payload 为 SOMEIP_SD
            # 如果 Scapy 已经自动解析了 Payload，则直接使用，否则手动解析

            if isinstance(pkt.payload, SOMEIP_SD):
                sd_pkt = pkt.payload
            elif hasattr(pkt.payload, 'load'):
                sd_pkt = SOMEIP_SD(pkt.payload.load)
            else:
                # Payload 为空或无法解析
                return

            logger.info(f"收到 SD 数据包来自 {addr}")

            # 遍历 Entry 数组
            for entry in sd_pkt.entry_array:
                logger.debug(f"  SD Entry: {entry.show(dump=True)}")

                # 自动检测协议逻辑：检查 OfferService 中的 Endpoint
                if hasattr(entry, 'type') and entry.type == 0x01: # OfferService
                     for opt in sd_pkt.option_array:
                        # 检查 IPv4 Endpoint 选项
                        if isinstance(opt, SDOption_IP4_EndPoint):
                            # L4-Proto: 0x06 = TCP, 0x11 = UDP
                            if opt.l4_proto == 0x06:
                                logger.info(f"发现 TCP 服务 Endpoint: {opt.addr}:{opt.port}")
                                self._ensure_tcp_connection(opt.addr, opt.port)
                            elif opt.l4_proto == 0x11:
                                logger.info(f"发现 UDP 服务 Endpoint: {opt.addr}:{opt.port}")
                                # UDP 不需要连接，但可以标记偏好
                                pass

                for cb in self.sd_callbacks:
                    cb(entry, sd_pkt.option_array)
        except Exception as e:
            logger.error(f"解析 SD Payload 错误: {e}")

    def _ensure_tcp_connection(self, ip, port):
        """确保 TCP 连接已建立。"""
        if self.tcp_socket:
            return # 已经连接

        try:
            logger.info(f"正在尝试建立 TCP 连接到 {ip}:{port} ...")
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.connect((ip, port))
            self.use_tcp = True

            # 启动 TCP 接收线程
            self.tcp_recv_thread = threading.Thread(target=self._receive_loop_tcp, daemon=True)
            self.tcp_recv_thread.start()
            logger.info(f"TCP 连接建立成功")
        except Exception as e:
            logger.error(f"建立 TCP 连接失败: {e}")
            self.tcp_socket = None
            self.use_tcp = False

    def send_request(self, service_id, method_id, payload=b'', target_ip=None, target_port=30500):
        """发送 SOME/IP 请求。"""
        if target_ip is None and not self.use_tcp:
            logger.error("必须指定目标 IP (UDP模式)")
            return

        pkt = SOMEIP(
            srv_id=service_id,
            sub_id=method_id,
            client_id=self.client_id,
            session_id=self.session_id,
            msg_type=0x00, # REQUEST
            retcode=0x00
        ) / payload

        self.session_id += 1

        if self.use_tcp and self.tcp_socket:
            # 使用 TCP 发送
            try:
                self.tcp_socket.sendall(bytes(pkt))
                logger.info(f"已发送 TCP 请求 Service=0x{service_id:04X}")
            except Exception as e:
                logger.error(f"TCP 发送失败: {e}")
                # 可以在这里添加重连逻辑或回退到 UDP
        else:
            # 使用 UDP 发送
            self._send_udp(pkt, target_ip, target_port)

    def find_service(self, service_id=0xFFFF, instance_id=0xFFFF, multicast_ip=None, multicast_port=None):
        """
        发送 FindService SD 消消息。

        :param service_id: 服务 ID
        :param instance_id: 实例 ID
        :param multicast_ip: 组播 IP (默认使用类配置)
        :param multicast_port: 组播端口 (默认使用类配置)
        """
        # 使用参数提供的组播地址，如果未提供则使用实例默认值
        dest_ip = multicast_ip if multicast_ip else self.multicast_ip
        dest_port = multicast_port if multicast_port else self.multicast_port

        # SD 头部
        sd_header = SOMEIP(
            srv_id=0xFFFF,
            sub_id=0x8100,
            client_id=self.client_id,
            session_id=self.session_id,
            msg_type=0x02, # NOTIFICATION
            retcode=0x00
        )
        self.session_id += 1

        # SD Entry: FindService (Type 0x00)
        entry = SDEntry_Service(
            type=0x00,
            srv_id=service_id,
            inst_id=instance_id,
            major_ver=0xFF,
            ttl=3600
        )

        # SD Payload
        sd_payload = SOMEIP_SD(flags=0x80, entry_array=[entry])

        pkt = sd_header / sd_payload

        # 发送到组播地址
        self._send_udp(pkt, dest_ip, dest_port)
        logger.info(f"已发送 FindService，Service=0x{service_id:04X} 到 {dest_ip}:{dest_port}")

    def subscribe_eventgroup(self, service_id, instance_id, eventgroup_id, target_ip=None, target_port=None, multicast_ip=None, multicast_port=None):
        """
        发送 SubscribeEventGroup SD 消息。

        :param service_id: 服务 ID
        :param instance_id: 实例 ID
        :param eventgroup_id: 事件组 ID
        :param target_ip: 目标单播 IP (如果已知服务端 IP)
        :param target_port: 目标单播端口
        :param multicast_ip: 组播 IP (如果 target_ip 为空，则使用此地址或默认组播地址)
        :param multicast_port: 组播端口
        """
        # SD 头部
        sd_header = SOMEIP(
            srv_id=0xFFFF,
            sub_id=0x8100,
            client_id=self.client_id,
            session_id=self.session_id,
            msg_type=0x02, # NOTIFICATION
            retcode=0x00
        )
        self.session_id += 1

        # SD Entry: SubscribeEventGroup (Type 0x06)
        entry = SDEntry_EventGroup(
            type=0x06,
            srv_id=service_id,
            inst_id=instance_id,
            major_ver=0x01,
            ttl=10,
            cnt=0,
            eventgroup_id=eventgroup_id
        )

        # Endpoint Option (IPv4)
        # Type 0x04 = IPv4 Endpoint
        option = SDOption_IP4_EndPoint(
            type=0x04,
            len=0x0009,
            addr=self.local_ip,
            l4_proto=0x11, # UDP
            port=self.local_port
        )

        sd_payload = SOMEIP_SD(flags=0x80, entry_array=[entry], option_array=[option])

        pkt = sd_header / sd_payload

        # 确定目标地址：优先使用 target_ip (单播)，否则��用 multicast_ip (组播)
        if target_ip:
            dest_ip = target_ip
            dest_port = target_port if target_port else self.multicast_port # 如果未指定单播端口，可能需要回退到默认端口，或者应该由调用者指定
            # 注意：SD 消息通常发往 30490，即使是单播。除非服务端另有规定。
            if dest_port is None: dest_port = self.multicast_port
        else:
            dest_ip = multicast_ip if multicast_ip else self.multicast_ip
            dest_port = multicast_port if multicast_port else self.multicast_port

        self._send_udp(pkt, dest_ip, dest_port)
        logger.info(f"已发送 SubscribeEventGroup，Service=0x{service_id:04X}, EG=0x{eventgroup_id:04X} 到 {dest_ip}:{dest_port}")

    def _send_udp(self, pkt, ip, port):
        """发送 UDP 数据包的辅助方法。"""
        try:
            self.udp_socket.sendto(bytes(pkt), (ip, port))
        except Exception as e:
            logger.error(f"发送数据包到 {ip}:{port} 失败: {e}")

    def register_callback(self, service_id, method_id, callback):
        """注册特定服务/方法的回调函数。"""
        self.message_callbacks[(service_id, method_id)] = callback

    def register_sd_callback(self, callback):
        """注册 SD 消息的回调函数。"""
        self.sd_callbacks.append(callback)


class TestSomeIPClient:
    """SomeIPClient 的测试类。"""

    def __init__(self):
        self.found_event = threading.Event()
        self.target_service = None
        self.target_ip = None
        self.target_port = None

    def run(self):
        print("开始 SomeIPClient 测试...")

        # 配置测试参数
        LOCAL_IP = "10.1.0.99"
        # 默认目标 IP (如果服务发现未返回 IP，则使用此 IP)
        DEFAULT_TARGET_IP = "10.1.0.79"

        # 通用的读取信息的方法 ID (通常 0x0001 被用作 Get/Read)
        GENERIC_READ_METHOD_ID = 0x0001

        print(f"配置: 本地IP={LOCAL_IP}")

        # 1. 初始化客户端
        # 绑定到本地特定网口 IP，端口设为 0 让系统自动分配，避免端口冲突
        client = SomeIPClient(local_ip=LOCAL_IP, local_port=0)
        if not client.start():
            print("客户端启动失败，请检查 IP 是否存在于本机")
            return

        # 2. 注册 SD 回调以捕获 OfferService
        def sd_callback(entry, options):
            # 检查是否为 OfferService (Type 0x01)
            if hasattr(entry, 'type') and entry.type == 0x01:
                # 只要收到 Offer 就接受 (发现任意服务)
                if not self.found_event.is_set():
                    print(f"\n[SD回调] 发现服务! Service=0x{entry.srv_id:04X}, Instance=0x{entry.inst_id:04X}")

                    # 尝试从选项中获取 Endpoint
                    endpoint_ip = DEFAULT_TARGET_IP
                    endpoint_port = 30500

                    for opt in options:
                        if isinstance(opt, SDOption_IP4_EndPoint):
                            endpoint_ip = opt.addr
                            endpoint_port = opt.port
                            print(f"  Endpoint: {endpoint_ip}:{endpoint_port}")
                            break

                    self.target_service = entry.srv_id
                    self.target_ip = endpoint_ip
                    self.target_port = endpoint_port
                    self.found_event.set()

        client.register_sd_callback(sd_callback)

        # 3. 注册通用消息回调
        def response_callback(pkt):
            payload_hex = pkt.payload.load.hex() if hasattr(pkt.payload, 'load') else 'Empty'
            print(f"\n[回调] 收到回复! \n  Service=0x{pkt.srv_id:04X}, Method=0x{pkt.sub_id:04X}\n  Payload: {payload_hex}")

        try:
            # 4. 发送 FindService (Service=0xFFFF, Instance=0xFFFF) 寻找所有服务
            print(f"\n[1] 发送 FindService (Service=0xFFFF)...")
            client.find_service(service_id=0xFFFF, instance_id=0xFFFF)

            print("等待发现服务 (10秒)...")
            if self.found_event.wait(timeout=10):
                print(f"\n[2] 锁定目标服务: 0x{self.target_service:04X} @ {self.target_ip}:{self.target_port}")

                # 注册针对该服务的接收回调
                client.register_callback(service_id=self.target_service, method_id=GENERIC_READ_METHOD_ID, callback=response_callback)

                # 5. 发送读取请求
                print(f"发送读取请求 (Method=0x{GENERIC_READ_METHOD_ID:04X})...")
                client.send_request(
                    service_id=self.target_service,
                    method_id=GENERIC_READ_METHOD_ID,
                    payload=b'', # 空负载表示通用读取
                    target_ip=self.target_ip,
                    target_port=self.target_port
                )

                print("等待回复 (5秒)...")
                time.sleep(5)
            else:
                print("未收到 OfferService，尝试直接发送请求到默认目标 (假设 Service=0x1234)...")
                # 如果没发现服务，尝试直接发送给 0x1234 (作为 fallback)
                FALLBACK_SERVICE_ID = 0x1234
                client.register_callback(service_id=FALLBACK_SERVICE_ID, method_id=GENERIC_READ_METHOD_ID, callback=response_callback)
                client.send_request(
                    service_id=FALLBACK_SERVICE_ID,
                    method_id=GENERIC_READ_METHOD_ID,
                    payload=b'',
                    target_ip=DEFAULT_TARGET_IP,
                    target_port=30500
                )
                time.sleep(5)

        except KeyboardInterrupt:
            print("测试被用户中断")
        finally:
            # 停止
            print("\n停止客户端...")
            client.stop()
            print("测试结束。")

if __name__ == "__main__":
    test = TestSomeIPClient()
    test.run()
