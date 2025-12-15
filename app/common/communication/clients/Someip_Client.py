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

    def __init__(self, local_ip: str, local_port: int = 30500, interface: str = None,
                 multicast_ip: str = SD_MULTICAST_IP, multicast_port: int = SD_MULTICAST_PORT):
        self.local_ip = local_ip
        self.local_port = local_port
        self.interface = interface
        self.multicast_ip = multicast_ip
        self.multicast_port = multicast_port

        self.client_id = 0x1234
        self.session_id = 1

        self.socket = None
        self.running = False
        self.recv_thread = None

        # 回调函数字典
        # Key: (service_id, method_id) -> Value: callback_function(packet)
        self.message_callbacks: Dict[tuple, Callable] = {}
        self.sd_callbacks: List[Callable] = []

    def start(self):
        """初始化 Socket 并启动接收线程。"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.local_ip, self.local_port))

            # 如果端口为 0，获取实际分配的端口
            if self.local_port == 0:
                self.local_port = self.socket.getsockname()[1]

            self.running = True
            self.recv_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.recv_thread.start()

            logger.info(f"SomeIPClient 已启动，监听地址: {self.local_ip}:{self.local_port}")
            return True
        except Exception as e:
            logger.error(f"启动客户端失败: {e}")
            return False

    def stop(self):
        """停止客户端。"""
        self.running = False
        if self.socket:
            self.socket.close()
        if self.recv_thread and self.recv_thread.is_alive():
            self.recv_thread.join(timeout=1.0)
        logger.info("SomeIPClient 已停止")

    def _receive_loop(self):
        """接收 UDP 数据包并解析的循环。"""
        while self.running:
            try:
                # 阻塞接收
                data, addr = self.socket.recvfrom(4096)
                self._process_packet(data, addr)
            except socket.timeout:
                continue
            except OSError:
                # Socket 已关闭
                break
            except Exception as e:
                logger.error(f"接收循环发生错误: {e}")

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
                for cb in self.sd_callbacks:
                    cb(entry, sd_pkt.option_array)
        except Exception as e:
            logger.error(f"解析 SD Payload 错误: {e}")

    def send_request(self, service_id, method_id, payload=b'', target_ip=None, target_port=30500):
        """发送 SOME/IP 请求。"""
        if target_ip is None:
            logger.error("必须指定目标 IP")
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

        self._send_udp(pkt, target_ip, target_port)

    def find_service(self, service_id=0xFFFF, instance_id=0xFFFF, multicast_ip=None, multicast_port=None):
        """
        发送 FindService SD 消息。

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
            self.socket.sendto(bytes(pkt), (ip, port))
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

    def run(self):
        print("开始 SomeIPClient 测试...")

        # 1. 初始化客户端
        # 使用回环地址进行测试
        client = SomeIPClient(local_ip="127.0.0.1", local_port=30500)
        if not client.start():
            return

        # 2. 注册回调
        def my_callback(pkt):
            payload_hex = pkt.payload.load.hex() if hasattr(pkt.payload, 'load') else 'Empty'
            print(f"回调触发! 收到 Payload: {payload_hex}")

        client.register_callback(service_id=0x1234, method_id=0x0001, callback=my_callback)

        # 3. 测试 Find Service
        print("\n[测试] 发送 FindService...")
        client.find_service(service_id=0x1234)
        time.sleep(0.5)

        # 4. 测试发送请求 (发送给自己以触发回调)
        print("\n[测试] 发送请求给自己...")
        client.send_request(
            service_id=0x1234,
            method_id=0x0001,
            payload=b'\xDE\xAD\xBE\xEF',
            target_ip="127.0.0.1",
            target_port=30500
        )
        time.sleep(0.5)

        # 5. 测试 Subscribe EventGroup
        print("\n[测试] 发送 SubscribeEventGroup...")
        client.subscribe_eventgroup(
            service_id=0x1234,
            instance_id=0x0001,
            eventgroup_id=0x8001,
            target_ip="127.0.0.1"
        )
        time.sleep(0.5)

        # 停止
        print("\n停止客户端...")
        client.stop()
        print("测试结束。")

if __name__ == "__main__":
    test = TestSomeIPClient()
    test.run()
