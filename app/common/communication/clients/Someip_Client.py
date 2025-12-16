#!/usr/bin/env python3
"""
SOME/IP 客户端 (最终测试版)
流程:
1. 策略 A: 发送组播 FindService
2. 策略 B: 发送单播 FindService (如果 A 失败)
3. 策略 C: 直接盲发业务 Request (如果 A/B 都无 Offer)
"""

import socket
import threading
import time
import struct
import logging
from typing import Callable, Dict, List, Optional, Tuple

# Scapy 导入与配置
try:
    from scapy.config import conf

    conf.contribs['automotive.someip'] = True
    from scapy.contrib.automotive.someip import (
        SOMEIP,
        SD as SOMEIP_SD,
        SDEntry_Service,
        SDEntry_EventGroup,
        SDOption_IP4_EndPoint
    )
except ImportError:
    print("错误: 未找到 Scapy。请安装: pip install scapy")
    exit(1)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("SomeIPClient")


class SomeIPClient:
    # 默认标准 SD 组播地址
    DEFAULT_SD_MULTICAST_IP = "224.224.224.245"
    DEFAULT_SD_MULTICAST_PORT = 30490

    def __init__(self,
                 local_ip: str,
                 local_port: int = 0,
                 client_id: int = 0x1234,
                 multicast_ip: str = DEFAULT_SD_MULTICAST_IP,
                 multicast_port: int = DEFAULT_SD_MULTICAST_PORT):

        self.local_ip = local_ip
        self.local_port = local_port
        self.client_id = client_id
        self.multicast_ip = multicast_ip
        self.multicast_port = multicast_port

        self.udp_socket: Optional[socket.socket] = None
        self.tcp_socket: Optional[socket.socket] = None
        self.use_tcp = False

        self.session_id = 1
        self.running = False
        self.recv_thread = None
        self.tcp_recv_thread = None

        self.send_lock = threading.Lock()

        # 回调存储
        self.message_callbacks: Dict[Tuple[int, int], Callable] = {}
        self.sd_callbacks: List[Callable] = []

    def start(self) -> bool:
        """启动客户端"""
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # 绑定本地
            self.udp_socket.bind((self.local_ip, self.local_port))

            if self.local_port == 0:
                self.local_port = self.udp_socket.getsockname()[1]

            # 设置组播出口网卡
            if self.local_ip != "0.0.0.0" and self.local_ip != "127.0.0.1":
                try:
                    self.udp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                                               socket.inet_aton(self.local_ip))
                except Exception as e:
                    logger.warning(f"设置组播出口失败: {e}")

            self.running = True
            self.recv_thread = threading.Thread(target=self._receive_loop_udp, daemon=True)
            self.recv_thread.start()

            logger.info(f"客户端启动成功 @ {self.local_ip}:{self.local_port} (Client ID: 0x{self.client_id:04X})")
            return True
        except Exception as e:
            logger.error(f"启动失败: {e}")
            self.stop()
            return False

    def stop(self):
        self.running = False
        if self.udp_socket:
            try:
                self.udp_socket.close()
            except:
                pass
        self._close_tcp()
        logger.info("客户端停止")

    def _close_tcp(self):
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except:
                pass
            self.tcp_socket = None
        self.use_tcp = False

    def _get_next_session_id(self):
        """生成循环 Session ID"""
        sid = self.session_id
        self.session_id += 1
        if self.session_id > 0xFFFF:
            self.session_id = 1
        return sid

    def register_callback(self, service_id, method_id, callback):
        """注册业务消息回调"""
        self.message_callbacks[(service_id, method_id)] = callback

    def register_sd_callback(self, callback):
        """注册 SD 消息回调"""
        self.sd_callbacks.append(callback)

    def _receive_loop_udp(self):
        while self.running and self.udp_socket:
            try:
                data, addr = self.udp_socket.recvfrom(4096)
                self._process_packet(data, addr)
            except (socket.timeout, OSError):
                continue
            except Exception as e:
                logger.error(f"UDP Error: {e}")

    def _recv_exact(self, sock, size):
        """TCP 辅助读取函数"""
        buf = b""
        while len(buf) < size:
            try:
                chunk = sock.recv(size - len(buf))
                if not chunk: return None
                buf += chunk
            except:
                return None
        return buf

    def _receive_loop_tcp(self):
        """TCP 接收循环 (含粘包处理)"""
        logger.info("TCP 接收线程启动")
        while self.running and self.tcp_socket:
            try:
                header = self._recv_exact(self.tcp_socket, 16)
                if not header: break

                _, length_val = struct.unpack(">II", header[0:8])
                payload_len = length_val - 8

                body = b""
                if payload_len > 0:
                    body = self._recv_exact(self.tcp_socket, payload_len)
                    if not body: break

                self._process_packet(header + body, ("TCP", 0))

            except Exception as e:
                logger.error(f"TCP Error: {e}")
                break

        logger.info("TCP 连接断开")
        self._close_tcp()

    def _process_packet(self, data: bytes, addr):
        try:
            pkt = SOMEIP(data)
            if pkt.srv_id == 0xFFFF and pkt.sub_id == 0x8100:
                self._handle_sd_packet(pkt, addr)
            else:
                self._handle_app_packet(pkt)
        except Exception:
            pass

    def _handle_sd_packet(self, pkt, addr):
        if isinstance(pkt.payload, SOMEIP_SD):
            sd_pkt = pkt.payload
        elif hasattr(pkt.payload, 'load'):
            try:
                sd_pkt = SOMEIP_SD(pkt.payload.load)
            except:
                return
        else:
            return

        logger.debug(f"收到 SD 消息来自 {addr}")
        for cb in self.sd_callbacks:
            cb(sd_pkt.entry_array, sd_pkt.option_array)

    def _handle_app_packet(self, pkt):
        key = (pkt.srv_id, pkt.sub_id)
        if key in self.message_callbacks:
            self.message_callbacks[key](pkt)
        else:
            logger.info(f"收到未注册消息: Srv=0x{pkt.srv_id:04X} Method=0x{pkt.sub_id:04X}")

    def connect_tcp(self, ip, port):
        """手动建立 TCP 连接"""
        if self.tcp_socket: return
        try:
            logger.info(f"连接 TCP {ip}:{port}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            sock.connect((ip, port))
            sock.settimeout(None)
            self.tcp_socket = sock
            self.use_tcp = True

            self.tcp_recv_thread = threading.Thread(target=self._receive_loop_tcp, daemon=True)
            self.tcp_recv_thread.start()
            logger.info("TCP 连接成功")
        except Exception as e:
            logger.error(f"TCP 连接失败: {e}")

    def send_request(self, service_id, method_id, payload=b'', target_ip=None, target_port=30500):
        """发送请求"""
        pkt = SOMEIP(
            srv_id=service_id,
            sub_id=method_id,
            client_id=self.client_id,
            session_id=self._get_next_session_id(),
            msg_type=0x00,  # REQUEST
            retcode=0x00
        ) / payload

        with self.send_lock:
            if self.use_tcp and self.tcp_socket:
                try:
                    self.tcp_socket.sendall(bytes(pkt))
                    logger.info(f"发送 TCP Req -> Service=0x{service_id:04X}")
                except Exception as e:
                    logger.error(f"TCP 发送失败: {e}")
                    self._close_tcp()
            elif target_ip:
                try:
                    self.udp_socket.sendto(bytes(pkt), (target_ip, target_port))
                    logger.info(f"发送 UDP Req -> {target_ip}:{target_port}")
                except Exception as e:
                    logger.error(f"UDP 发送失败: {e}")
            else:
                logger.error("发送失败: 未建立 TCP 连接且未提供 UDP 目标 IP")

    def find_service(self, service_id=0xFFFF, instance_id=0xFFFF, override_ip=None):
        """发送 FindService"""
        sd = SOMEIP_SD(flags=0x80, entry_array=[
            SDEntry_Service(type=0x00, srv_id=service_id, inst_id=instance_id, ttl=3600)
        ])
        pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=self.client_id,
                     session_id=self._get_next_session_id(), msg_type=0x02) / sd

        dest_ip = override_ip if override_ip else self.multicast_ip

        try:
            self.udp_socket.sendto(bytes(pkt), (dest_ip, self.multicast_port))
            logger.info(f"发送 FindService (0x{service_id:04X}) to {dest_ip}:{self.multicast_port}")
        except Exception as e:
            logger.error(f"发送 FindService 失败: {e}")


# ==========================================
# 测试流程
# ==========================================
class TestRunner:
    def __init__(self):
        self.found = threading.Event()
        self.received = threading.Event()
        self.target = {}

    def run(self):
        print("\n=== 启动测试 (三步策略) ===")

        # --- 配置 ---
        CLIENT_IP = "10.1.0.99"
        ECU_UNICAST_IP = "10.1.0.79"  # 控制器 IP
        STD_MCAST_IP = "224.224.224.245"  # 标准组播 IP

        # 必须确保这两个 ID 和控制器数据库(ARXML)一致
        SERVICE_ID = 0x106E
        METHOD_ID = 0x0001

        # 盲测时的默认端口 (通常是 30500, 30501, 30491 等)
        BLIND_PORT = 30500
        # ------------

        client = SomeIPClient(local_ip=CLIENT_IP, client_id=0x1234, multicast_ip=STD_MCAST_IP)
        if not client.start(): return

        # 1. 注册 SD 回调
        def on_sd(entries, options):
            for entry in entries:
                if entry.type == 0x01 and entry.srv_id == SERVICE_ID:  # OfferService
                    if self.found.is_set(): return

                    # 尝试解析 IP
                    t_ip, t_port, proto = ECU_UNICAST_IP, BLIND_PORT, 'UDP'
                    for opt in options:
                        if isinstance(opt, SDOption_IP4_EndPoint):
                            t_ip = opt.addr
                            t_port = opt.port
                            proto = 'TCP' if opt.l4_proto == 0x06 else 'UDP'

                    print(f"\n[SUCCESS] 收到 Offer! Endpoint: {t_ip}:{t_port} ({proto})")
                    self.target = {'ip': t_ip, 'port': t_port, 'proto': proto}

                    if proto == 'TCP':
                        client.connect_tcp(t_ip, t_port)

                    self.found.set()

        client.register_sd_callback(on_sd)

        # 2. 注册业务回调
        def on_msg(pkt):
            print(
                f"\n[SUCCESS] 收到业务回复! Payload: {pkt.payload.load.hex() if hasattr(pkt.payload, 'load') else 'Empty'}")
            self.received.set()

        client.register_callback(SERVICE_ID, METHOD_ID, on_msg)

        try:
            # --- 策略 A: 组播 FindService ---
            print(f"策略 A: 发送标准组播 FindService ({STD_MCAST_IP})...")
            client.find_service(SERVICE_ID)

            # --- 策略 B: 单播 FindService (如果 A 超时) ---
            if not self.found.wait(timeout=3):
                print(f"策略 B: 超时未收到 Offer，尝试发送单播 FindService ({ECU_UNICAST_IP})...")
                client.find_service(SERVICE_ID, override_ip=ECU_UNICAST_IP)

            # 等待结果或执行策略 C
            target_ip = None
            target_port = None

            if self.found.wait(timeout=5):
                print(f"--> [SD成功] 服务已就绪，准备发送请求...")
                target_ip = self.target['ip']
                target_port = self.target['port']
            else:
                # --- 策略 C: 盲测直接访问 (如果 A/B 都失败) ---
                print(f"策略 C: 始终未收到 Offer，尝试直接发送业务请求 (盲测)...")
                target_ip = ECU_UNICAST_IP
                target_port = BLIND_PORT

                # 发送请求
            print(f"发送 Request -> {target_ip}:{target_port}")
            # 注意: 盲测时默认使用 UDP，如果知道是 TCP 服务需要修改代码调用 connect_tcp
            client.send_request(
                service_id=SERVICE_ID,
                method_id=METHOD_ID,
                payload=b'\x01\x02',
                target_ip=target_ip,
                target_port=target_port
            )

            if self.received.wait(timeout=5):
                print("测试通过！(收到业务回复)")
            else:
                print("测试失败: SD无响应 且 盲发请求无回复。")

        except KeyboardInterrupt:
            print("停止")
        finally:
            client.stop()


if __name__ == "__main__":
    TestRunner().run()