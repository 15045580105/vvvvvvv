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
import random
from typing import Callable, Dict, List, Optional, Tuple

# Scapy 导入与配置
try:
    from scapy.config import conf

    # 强制关闭 Scapy 的混杂模式自动配置，防止与 Windows 驱动冲突
    conf.sniff_promisc = False

    from scapy.layers.l2 import Ether, Dot1Q, getmacbyip, ARP
    from scapy.layers.inet import IP, UDP
    from scapy.sendrecv import sendp, sniff, srp1
    from scapy.arch import get_if_list, get_if_addr, get_if_hwaddr

    conf.contribs['automotive.someip'] = True
    from scapy.contrib.automotive.someip import (
        SOMEIP,
        SD as SOMEIP_SD,
        SDEntry_Service,
        SDEntry_EventGroup,
        SDOption_IP4_EndPoint
    )
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False
    # Dummy defines to prevent linter errors in standard Python envs
    conf = None
    Ether = Dot1Q = getmacbyip = ARP = None
    IP = UDP = None
    sendp = sniff = srp1 = None
    get_if_list = get_if_addr = get_if_hwaddr = None
    SOMEIP = SOMEIP_SD = None
    SDEntry_Service = SDEntry_EventGroup = SDOption_IP4_EndPoint = None

    print("错误: 未找到 Scapy。请安装: pip install scapy")
    # exit(1) # Don't exit immediately to allow other imports if needed, but TestRunner will fail.

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("SomeIPClient")


class SomeIPClient:
    # 默认标准 SD 组播地址
    DEFAULT_SD_MULTICAST_IP = "239.71.0.2"
    DEFAULT_SD_MULTICAST_PORT = 30490

    def __init__(self,
                 local_ip: str,
                 local_port: int = 30813,
                 client_id: int = 30813,
                 multicast_ip: str = DEFAULT_SD_MULTICAST_IP,
                 multicast_port: int = DEFAULT_SD_MULTICAST_PORT,
                 vlan_id: int = None,
                 client_mac: str = None,
                 target_mac: str = None):

        if not SCAPY_AVAILABLE:
             raise RuntimeError("Scapy library is missing.")

        self.local_ip = local_ip

        self.local_port = local_port
        self.client_id = client_id
        self.multicast_ip = multicast_ip
        self.multicast_port = multicast_port
        self.vlan_id = vlan_id
        self.iface = None
        self.mac = client_mac
        self.target_mac = target_mac

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
        self._arp_cache = {}
        self._dedup_cache = {}
        self._dedup_lock = threading.Lock()

    def start(self) -> bool:
        """启动客户端"""
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # 绑定本地端口
            # 根据配置限制：Client Port 范围 1025-65534
            if self.local_port == 0:
                bound = False
                # 尝试多次随机绑定
                for _ in range(20):
                    port = random.randint(1025, 65534)
                    try:
                        self.udp_socket.bind((self.local_ip, port))
                        self.local_port = port
                        bound = True
                        break
                    except OSError:
                        continue

                if not bound:
                    logger.warning("无法在 1025-65534 范围内找到可用端口，尝试由系统自动分配")
                    self.udp_socket.bind((self.local_ip, 0))
                    self.local_port = self.udp_socket.getsockname()[1]
            else:
                # 如果用户指定了端口，检查是否在范围内
                if not (1025 <= self.local_port <= 65534):
                    logger.warning(f"指定的本地端口 {self.local_port} 不在配置范围 1025-65534 内")
                self.udp_socket.bind((self.local_ip, self.local_port))

            # 设置组播出口网卡
            if self.local_ip != "0.0.0.0" and self.local_ip != "127.0.0.1":
                try:
                    self.udp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                                               socket.inet_aton(self.local_ip))
                except Exception as e:
                    logger.warning(f"设置组播出口失败: {e}")

            # 如果启用了 VLAN，解析接口和 MAC
            if self.vlan_id is not None:
                try:
                    for iface in get_if_list():
                        # Windows 上 get_if_addr 可能需要 GUID，这里尝试匹配 IP
                        if get_if_addr(iface) == self.local_ip:
                            self.iface = iface
                            if self.mac is None:
                                self.mac = get_if_hwaddr(iface)
                            logger.info(f"VLAN模式: 绑定接口 {self.iface} ({self.mac}), VLAN ID={self.vlan_id}")
                            break
                    if not self.iface:
                        logger.warning(f"无法找到 IP {self.local_ip} 对应的网卡接口，VLAN 发送可能失败")
                except Exception as e:
                    logger.error(f"解析 VLAN 接口失败: {e}")

            # 加入组播组 (用于接收组播 Offer)
            try:
                mreq = struct.pack("4s4s",
                                   socket.inet_aton(self.multicast_ip),
                                   socket.inet_aton(self.local_ip))
                self.udp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                logger.info(f"已加入组播组: {self.multicast_ip}")
            except Exception as e:
                logger.warning(f"加入组播组失败 (可能无法收到组播 Offer): {e}")

            self.running = True

            # 启动 Scapy VLAN 接收线程 (重要: 修复通过 Scapy 接收 VLAN 流量)
            if self.vlan_id is not None:
                if self.iface:
                    self.scapy_recv_thread = threading.Thread(target=self._receive_loop_scapy_vlan, daemon=True)
                    self.scapy_recv_thread.start()
                    logger.info(f"已启动 VLAN {self.vlan_id} Scapy 监听线程 (Interface: {self.iface})")
                else:
                    logger.error("VLAN ID 已配置但未找到对应网卡接口，无法启动 VLAN 监听！请检查本地 IP 设置。")

            # 启动 Socket 接收线程
            self.recv_thread = threading.Thread(target=self._receive_loop_udp, daemon=True)
            self.recv_thread.start()

            # 发送启动成功信号，或者在这里阻塞直到连接建立 (如果用户需要)
            # 用户要求: "建立客户端方法到成功建立客户端就可以返回true了...类似测试程序打印出客户端启动成功就可以返回true了"
            # 这表明目前的行为 (非阻塞) 是正确的。

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

    def _extract_endpoints(self, entry, options) -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]]]:
        """
        安全解析 SD Entry 中的 Endpoint 选项
        :return: (tcp_endpoints, udp_endpoints)
        """
        found_opts = []
        tcp_eps = []
        udp_eps = []

        try:
            # 尝试获取索引字段 (适配不同 Scapy 版本)
            idx1 = getattr(entry, 'index_1', getattr(entry, 'index_1st_opts', None))
            num1 = getattr(entry, 'n_opt_1', getattr(entry, 'number_1st_opts', None))
            idx2 = getattr(entry, 'index_2', getattr(entry, 'index_2nd_opts', None))
            num2 = getattr(entry, 'n_opt_2', getattr(entry, 'number_2nd_opts', None))

            # 如果无法获取索引，则认为解析失败，不执行回退（避免误读）
            if idx1 is None or num1 is None:
                # 只有在确实无法解析时，才打印警告，且不匹配任何选项
                # logger.debug("无法解析 Entry 索引，跳过选项匹配")
                return [], []

            def collect_from_range(start, count):
                for k in range(start, start + count):
                    if k < len(options):
                        found_opts.append(options[k])

            collect_from_range(idx1, num1)
            collect_from_range(idx2, num2)

        except Exception as e:
            logger.warning(f"解析 SD Entry 出错: {e}")
            return [], []

        for opt in found_opts:
            if isinstance(opt, SDOption_IP4_EndPoint):
                ep = (opt.addr, opt.port)
                if opt.l4_proto == 0x06: # TCP
                    tcp_eps.append(ep)
                elif opt.l4_proto == 0x11: # UDP
                    udp_eps.append(ep)

        return tcp_eps, udp_eps

    def register_callback(self, service_id, method_id, callback):
        """注册业务消息回调"""
        self.message_callbacks[(service_id, method_id)] = callback

    def register_sd_callback(self, callback):
        """注册 SD 消息回调"""
        self.sd_callbacks.append(callback)

    def unregister_callback(self, service_id, method_id):
        """注销业务消息回调"""
        key = (service_id, method_id)
        if key in self.message_callbacks:
            del self.message_callbacks[key]

    def unregister_sd_callback(self, callback):
        """注销 SD 消消息回调"""
        if callback in self.sd_callbacks:
            self.sd_callbacks.remove(callback)

    def _receive_loop_scapy_vlan(self):
        """增强的 Scapy 接收循环"""
        logger.info(f"Scapy Sniffer 运行中 (过滤 {self.iface})...")

        def packet_handler(pkt):
            if not self.running: return

            if UDP not in pkt:
                return

            # 判断是否处理该包
            should_process = False
            src_ip = pkt[IP].src if IP in pkt else "0.0.0.0"
            if src_ip == self.local_ip: # 忽略自己发的包
                return

            # === 强力调试：监控所有来自目标网段的流量 ===
            # 如果源 IP 是 172.16.66.xx，无论端口是什么，都打印一下
            if src_ip.startswith("172.16.66."):
                 # 开启详细日志以排查问题
                 if logger.isEnabledFor(logging.DEBUG):
                     vlan_tag = pkt[Dot1Q].vlan if Dot1Q in pkt else 'None'
                     logger.debug(f"[RAW] 收到来自 {src_ip}:{pkt[UDP].sport} -> {pkt[UDP].dport} (VLAN={vlan_tag}) 的包")

            # 调试日志: 打印看到的流经端口 30490 的 VLAN 包
            debug_log = False
            if pkt[UDP].dport == self.multicast_port or pkt[UDP].sport == self.multicast_port:
                debug_log = True

            # 情况1: 带有 VLAN Tag 且 ID 匹配
            if Dot1Q in pkt:
                if pkt[Dot1Q].vlan == self.vlan_id:
                    should_process = True
                    if debug_log:
                        logger.debug(f"[Scapy-VLAN] 捕获 VLAN {self.vlan_id} 包: {src_ip} -> {pkt[UDP].dport}")

            # 情况2: 不带 VLAN Tag (可能被网卡驱动剥离了)，但端口匹配或者是组播
            elif self.vlan_id is not None:
                # 检查是否是我们关心的端口
                dport = pkt[UDP].dport
                # 30506 是组播端口, local_port 是单播接收端口,
                # 也可以检查源端口是否是服务端的常用端口 (如 30500)
                if dport == self.multicast_port or dport == self.local_port:
                    should_process = True
                    if debug_log:
                        logger.debug(f"[Scapy-NoTag] 捕获端口匹配包: {src_ip} -> {dport}")

            if should_process:
                try:
                    payload = bytes(pkt[UDP].payload)
                    src_port = pkt[UDP].sport

                    if len(payload) > 0:
                        self._process_packet(payload, (src_ip, src_port))
                except Exception as e:
                    pass

        # 移除 filter，全抓并在 Python 层过滤。
        # 这样可以规避 Windows Npcap 有时无法正确处理 'vlan' BPF 的问题

        while self.running:
            try:
                # sniff 是阻塞的，设置 timeout 以便通过 loop 检查 self.running
                sniff(iface=self.iface,
                      prn=packet_handler,
                      store=0,
                      timeout=0.5)
            except Exception as e:
                logger.error(f"Scapy Sniff 出错: {e}")
                time.sleep(1)

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

            # 去重逻辑: 防止 Socket 和 Scapy 同时收到同一个包导致打印两次
            sig = (pkt.srv_id, pkt.sub_id, pkt.client_id, pkt.session_id, pkt.msg_type)
            with self._dedup_lock:
                now = time.time()
                # 简单清理策略
                if len(self._dedup_cache) > 500:
                    self._dedup_cache.clear()

                if sig in self._dedup_cache:
                    if now - self._dedup_cache[sig] < 0.5:
                        return
                self._dedup_cache[sig] = now

            if pkt.srv_id == 0xFFFF and pkt.sub_id == 0x8100:
                self._handle_sd_packet(pkt, addr)
            else:
                self._handle_app_packet(pkt)
        except Exception:
            pass

    def _handle_sd_packet(self, pkt, addr):
        # addr is (ip, port) or ("TCP", 0) from TCP loop
        sender_ip = addr[0]

        # 严格过滤: 忽略来自本地的组播回环包
        if sender_ip == self.local_ip:
            return

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
            # Pass source IP to callback for stricter verification
            # (Adding sender_ip as a third argument if the callback supports it,
            # otherwise simplistic callbacks might fail.
            # To be safe, we rely on the filter above.
            # But actually TestRunner might want to know who sent it.)

            # Since existing signature is (entries, options), let's stick to that
            # but assume valid source because we filtered above.
            cb(sd_pkt.entry_array, sd_pkt.option_array)

    def _handle_app_packet(self, pkt):
        key = (pkt.srv_id, pkt.sub_id)
        if key in self.message_callbacks:
            self.message_callbacks[key](pkt)
        else:
            logger.info(f"收到未注册消息: Srv=0x{pkt.srv_id:04X} Method=0x{pkt.sub_id:04X}")

    def _resolve_mac(self, target_ip):
        """主动发送 ARP 请求获取 MAC (针对 VLAN 环境)"""
        # 如果配置了静态目标 MAC，直接使用
        if self.target_mac: return self.target_mac

        # 尝试查看 Scapy 的 ARP 缓存或系统缓存
        cached_mac = getmacbyip(target_ip)
        if cached_mac and cached_mac != "ff:ff:ff:ff:ff:ff":
            return cached_mac

        # 尝试内部缓存
        if hasattr(self, '_arp_cache') and target_ip in self._arp_cache:
            return self._arp_cache[target_ip]

        logger.info(f"正在通过 VLAN {self.vlan_id} 解析 {target_ip} 的 MAC 地址 (ARP)...")
        try:
            # 构造带 VLAN 的 ARP 请求
            arp_pkt = Ether(dst="ff:ff:ff:ff:ff:ff") / \
                      Dot1Q(vlan=self.vlan_id) / \
                      ARP(op=1, pdst=target_ip, hwsrc=self.mac, psrc=self.local_ip)

            # 使用 srp1 发送并等待回复 (Layer 2)
            resp = srp1(arp_pkt, iface=self.iface, timeout=1, verbose=0)
            if resp:
                mac = resp[ARP].hwsrc
                logger.info(f"ARP 解析成功: {target_ip} -> {mac}")
                if not hasattr(self, '_arp_cache'): self._arp_cache = {}
                self._arp_cache[target_ip] = mac
                return mac
            else:
                logger.warning(f"ARP 解析超时 ({target_ip})")
        except Exception as e:
            logger.warning(f"ARP 解析失败: {e}")

        return None

    def connect_tcp(self, ip, port):
        """手动建立 TCP 连接"""
        if self.tcp_socket: return
        try:
            logger.info(f"连接 TCP {ip}:{port}...")

            # 警告用户
            if self.vlan_id is not None:
                logger.error("【严重错误】检测到在手动 VLAN 模式下尝试建立 TCP 连接！")
                logger.error("  原因: Windows Socket 无法发送带 VLAN Tag 的 TCP 包，也无法利用 Scapy 建立完整 TCP 连接。")
                logger.error("  后果: 控制器将丢弃不带 Tag 的 SYN 包，连接必然超时。")
                logger.error("  解决方案: 请在 Windows 设备管理器中配置网卡驱动 VLAN (生成虚拟网卡)，并在代码中将 vlan_id 设为 None。")
                # 尽管知道会失败，还是尝试一下，以便用户看到 'timed out' 能对应上
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3.0)
                sock.connect((ip, port))
                sock.settimeout(None)
                self.tcp_socket = sock
                self.use_tcp = True

                self.tcp_recv_thread = threading.Thread(target=self._receive_loop_tcp, daemon=True)
                self.tcp_recv_thread.start()
                logger.info("TCP 连接成功")
                return
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

                # 尝试绑定本地端口到 1025-65534
                bound = False
                for _ in range(20):
                    local_tcp_port = random.randint(1025, 65534)
                    try:
                        sock.bind((self.local_ip, local_tcp_port))
                        bound = True
                        logger.debug(f"TCP 客户端绑定本地端口: {local_tcp_port}")
                        break
                    except OSError:
                        continue

                if not bound:
                    logger.warning("TCP 无法在 1025-65534 范围内绑定本地端口，将由系统自动分配")

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
            elif self.vlan_id is not None and self.iface and target_ip:
                # VLAN 模式发送
                try:
                    # 尝试解析 MAC (优先使用配置值或 ARP)
                    dst_mac = self._resolve_mac(target_ip)
                    if not dst_mac:
                        logger.warning(f"无法解析 {target_ip} 的 MAC 地址，尝试广播")
                        dst_mac = "ff:ff:ff:ff:ff:ff"

                    full_pkt = Ether(src=self.mac, dst=dst_mac) / \
                               Dot1Q(vlan=self.vlan_id) / \
                               IP(src=self.local_ip, dst=target_ip) / \
                               UDP(sport=self.local_port, dport=target_port) / \
                               pkt

                    # 关键动作：打孔防火墙
                    # Scapy 发包不走系统栈，为了让防火墙允许该端口接收回包，我们用 socket 发一个假包
                    try:
                        self.udp_socket.sendto(b'', (target_ip, target_port))
                    except:
                        pass # 可能会因为路由问题失败，不重要

                    sendp(full_pkt, iface=self.iface, verbose=False)
                    logger.info(f"发送 VLAN {self.vlan_id} UDP Req -> {target_ip}:{target_port} (MAC={dst_mac})")
                except Exception as e:
                    logger.error(f"Scapy VLAN 发送失败: {e}")
            elif target_ip:
                try:
                    self.udp_socket.sendto(bytes(pkt), (target_ip, target_port))
                    logger.info(f"发送 UDP Req -> {target_ip}:{target_port}")
                except Exception as e:
                    logger.error(f"UDP 发送失败: {e}")
            else:
                logger.error("发送失败: 未建立 TCP 连接且未提供 UDP 目标 IP")

    def find_service(self, service_id=0xFFFF, instance_id=0xFFFF, override_ip=None, ttl=3):
        """发送 FindService"""
        sd = SOMEIP_SD(flags=0x80, entry_array=[
            SDEntry_Service(type=0x00, srv_id=service_id, inst_id=instance_id, ttl=ttl)
        ])
        pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=self.client_id,
                     session_id=self._get_next_session_id(), msg_type=0x02) / sd

        dest_ip = override_ip if override_ip else self.multicast_ip

        if self.vlan_id is not None and self.iface:
            # VLAN 模式发送
            try:
                if dest_ip == self.multicast_ip:
                    # 简单映射组播 MAC (239.71.0.2 -> 01:00:5e:47:00:02)
                    dst_mac = "01:00:5e:47:00:02"
                else:
                    dst_mac = self._resolve_mac(dest_ip)
                    if not dst_mac:
                        dst_mac = "ff:ff:ff:ff:ff:ff"

                full_pkt = Ether(src=self.mac, dst=dst_mac) / \
                           Dot1Q(vlan=self.vlan_id) / \
                           IP(src=self.local_ip, dst=dest_ip) / \
                           UDP(sport=self.local_port, dport=self.multicast_port) / \
                           pkt
                sendp(full_pkt, iface=self.iface, verbose=False)
                logger.info(f"发送 VLAN {self.vlan_id} FindService to {dest_ip}:{self.multicast_port}")
                return
            except Exception as e:
                logger.error(f"Scapy VLAN 发送失败: {e}")
                # 失败后尝试回退到普通 Socket 发送

        try:
            self.udp_socket.sendto(bytes(pkt), (dest_ip, self.multicast_port))
            logger.info(f"发送 FindService (0x{service_id:04X}) to {dest_ip}:{self.multicast_port}")
        except Exception as e:
            logger.error(f"发送 FindService 失败: {e}")

    def request_with_discovery(self, service_id: int, method_id: int, payload: bytes = b'',
                               target_ip: str = None, target_port: int = 30500, timeout: float = 3.0) -> Optional[bytes]:
        """
        自动服务发现并发送请求 (集成 UDP/TCP 自动切换与重试)
        :param service_id: 服务 ID
        :param method_id: 方法 ID
        :param payload: 请求负载
        :param target_ip: (可选) 指定目标 IP，用于单播发现或盲测
        :param target_port: (可选) 指定目标端口
        :param timeout: 等待回复的超时时间
        :return: 收到回复的 Payload 或 None
        """
        found_event = threading.Event()
        response_event = threading.Event()
        result_container: Dict[str, Optional[bytes]] = {'payload': None}

        # 存储发现的所有端点
        discovered_eps = {'tcp': [], 'udp': []}

        # 1. 定义 SD 回调
        def on_sd_offer(entries, options):
            for entry in entries:
                if entry.type == 0x01 and entry.srv_id == service_id:  # OfferService
                    tcp_list, udp_list = self._extract_endpoints(entry, options)

                    found_new = False
                    if tcp_list:
                        for ep in tcp_list:
                            if ep not in discovered_eps['tcp']:
                                discovered_eps['tcp'].append(ep)
                                found_new = True
                    if udp_list:
                        for ep in udp_list:
                            if ep not in discovered_eps['udp']:
                                discovered_eps['udp'].append(ep)
                                found_new = True

                    if found_new:
                        logger.info(f"[AutoReq] 收到 Offer: UDP={udp_list} TCP={tcp_list}")
                        found_event.set()

        # 2. 定义业务回调
        def on_response(pkt):
            # 过滤：确保是针对我们请求的 Service/Method
            # 严格模式：只接受 Response (0x80) 或 Error (0x81)
            # 避免把广播的 Notification 当作回复
            if pkt.srv_id == service_id and pkt.sub_id == method_id:
                if pkt.msg_type in [0x80, 0x81]:
                    if hasattr(pkt.payload, 'load'):
                        result_container['payload'] = pkt.payload.load
                    else:
                        result_container['payload'] = b''

                    logger.info(f"[AutoReq] 收到回复 (Type=0x{pkt.msg_type:02X})")
                    try:
                        pkt.show()
                        logger.info(f"Payload (Hex): {result_container['payload'].hex()}")
                    except:
                        pass

                    response_event.set()

        # 注册回调
        self.register_sd_callback(on_sd_offer)
        self.register_callback(service_id, method_id, on_response)

        try:
            # === 阶段 1: 服务发现 ===
            logger.info(f"[AutoReq] 开始服务发现 Service=0x{service_id:04X}...")

            # 策略 A: 组播 Find
            self.find_service(service_id)

            # 等待 Offer (1.5秒)
            # 如果控制器已经在周期性广播 Offer，这里应该能马上收到
            if not found_event.wait(timeout=1.5):
                # 策略 B: 单播 Find
                if target_ip:
                    logger.info(f"[AutoReq] 组播未响应，尝试单播 Find -> {target_ip}")
                    self.find_service(service_id, override_ip=target_ip)
                    found_event.wait(timeout=1.5)

            # 如果还是没找到，检查是否可以利用默认参数盲测
            if not discovered_eps['udp'] and not discovered_eps['tcp']:
                if target_ip:
                    logger.warning("[AutoReq] 未发现服务，将尝试使用给定的目标参数进行盲发")
                    # 默认假设是 UDP
                    discovered_eps['udp'].append((target_ip, target_port))
                else:
                    logger.error("[AutoReq] 无法继续: 未发现服务且未提供目标 IP")
                    return None

            # === 阶段 2: 尝试请求 (优先 UDP，失败转 TCP) ===

            # 2.1 尝试 UDP
            for ep in discovered_eps['udp']:
                ip, port = ep
                logger.info(f"[AutoReq] [UDP] 尝试请求 -> {ip}:{port}")

                response_event.clear()
                self.send_request(service_id, method_id, payload, target_ip=ip, target_port=port)

                if response_event.wait(timeout=timeout):
                    logger.info("[AutoReq] [UDP] 请求成功")
                    return result_container['payload']
                else:
                    logger.warning(f"[AutoReq] [UDP] 请求超时 ({ip}:{port})")

            # 2.2 尝试 TCP (如果 UDP 失败或无 UDP)
            for ep in discovered_eps['tcp']:
                ip, port = ep
                logger.info(f"[AutoReq] [TCP] 尝试建立连接并请求 -> {ip}:{port}")

                response_event.clear()

                # 建立 TCP 连接
                self.connect_tcp(ip, port)
                if not self.tcp_socket:
                    logger.warning(f"[AutoReq] [TCP] 连接失败 ({ip}:{port})")
                    continue

                self.send_request(service_id, method_id, payload)

                if response_event.wait(timeout=timeout):
                    logger.info("[AutoReq] [TCP] 请求成功")
                    return result_container['payload']
                else:
                    logger.warning(f"[AutoReq] [TCP] 请求超时 ({ip}:{port})")

            logger.error("[AutoReq] 所有尝试均失败")
            return None

        finally:
            # 清理回调
            self.unregister_sd_callback(on_sd_offer)
            self.unregister_callback(service_id, method_id)


# ==========================================
# 测试流程
# ==========================================
class TestRunner:
    def __init__(self):
        self.found = threading.Event()
        self.received = threading.Event()
        self.target_udp = None
        self.target_tcp = None

    def run(self):
        print("\n=== 启动测试 (三步策略) ===")

        # --- 配置 ---
        # MAC地址将自动使用本机网卡MAC
        # 请确保网卡已配置 VLAN 4
        CLIENT_IP = "172.16.64.47"
        # CLIENT_MAC = "20:7B:D5:20:25:B6"
        CLIENT_MAC = "00:E0:4C:55:36:98"

        # 目标控制器配置
        ECU_UNICAST_IP = "172.16.66.79"  # 控制器 IP
        # 如果 Ping 不通，必须手动填入控制器的 MAC 地址！否则发出的包要么 ARP 失败，要么是广播 MAC 可能被丢弃
        # 请填入嗅探器抓到的包里的源 MAC 地址，例如:
        ECU_MAC = "02:47:00:00:02:4F" # "00:01:02:03:04:05"

        STD_MCAST_IP = "239.71.0.2"  # 标准组播 IP
        VLAN_ID = 4  # 设置 VLAN ID

        # 必须确保这两个 ID 和控制器数据库(ARXML)一致
        # SERVICE_ID = 0x106E
        SERVICE_ID = 0x1055
        METHOD_ID = 0x0001

        # 盲测时的默认端口 (通常是 30500, 30501, 30491 等)
        BLIND_PORT = 30490
        # ------------

        print(f"配置: 本机 {CLIENT_IP} -> 目标 {ECU_UNICAST_IP} (VLAN {VLAN_ID})")
        if not ECU_MAC:
            print("注意: 未配置 ECU_MAC。如果 ARP 不通，单播通信可能会失败。")

        # 测试时也使用固定 client_id 30813
        client = SomeIPClient(local_ip=CLIENT_IP, client_id=30813,
                              multicast_ip=STD_MCAST_IP, vlan_id=VLAN_ID,
                              client_mac=CLIENT_MAC, target_mac=ECU_MAC)
        if not client.start(): return

        # 1. 注册 SD 回调
        def on_sd(entries, options):
            for entry in entries:
                if entry.type == 0x01 and entry.srv_id == SERVICE_ID:  # OfferService
                    if self.found.is_set(): return

                    tcp_list, udp_list = client._extract_endpoints(entry, options)

                    if tcp_list:
                        ep = tcp_list[0]
                        self.target_tcp = {'ip': ep[0], 'port': ep[1]}
                        print(f"\n[SD] 发现 TCP Endpoint: {ep[0]}:{ep[1]}")

                    if udp_list:
                        ep = udp_list[0]
                        self.target_udp = {'ip': ep[0], 'port': ep[1]}
                        print(f"\n[SD] 发现 UDP Endpoint: {ep[0]}:{ep[1]}")


                    # 只要发现任意一个端点，就认为成功
                    if self.target_udp or self.target_tcp:
                        self.found.set()

        client.register_sd_callback(on_sd)

        # 2. 注册业务回调
        def on_msg(pkt):
            print("\n[SUCCESS] 收到业务回复!")
            print(">>> 完整报文详情:")
            try:
                pkt.show()
            except:
                pass
            print("-------------------")
            payload = pkt.payload.load if hasattr(pkt.payload, 'load') else b''
            print(f"Payload (Hex): {payload.hex()}")
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

            # 等待结果

            if self.found.wait(timeout=10):
                print(f"--> [SD成功] 服务已就绪，准备发送请求...")
            else:
                print("测试失败: 未收到服务端的 Offer 回复，停止后续操作。")
                print("请检查: 1.链路连接 2.VLAN ID配置 3.服务端状态")
                return

            # ====== 执行发送测试 ======

            # 1. 尝试 UDP
            # 用户要求: 先尝试 UDP
            # 注意: 如果只发现了 TCP 端点，这里 target_udp 为空，会自动跳过。
            # 如果发现两者，都会尝试。

            if self.target_udp:
                print(f"\n[Step 1] 尝试 UDP 发送 -> {self.target_udp['ip']}:{self.target_udp['port']}")
                client.send_request(
                    service_id=SERVICE_ID,
                    method_id=METHOD_ID,
                    payload=b'\x01\x02',
                    target_ip=self.target_udp['ip'],
                    target_port=self.target_udp['port']
                )

                # 等待回复
                if self.received.wait(timeout=3):
                    print("测试通过！(UDP 收到业务回复)")
                    return
                else:
                    print("UDP 请求超时，未收到回复。")

            # 2. 尝试 TCP (如果 UDP 失败或被跳过)
            if self.target_tcp:
                # 只有当还没有收到回复时才尝试
                if not self.received.is_set():
                    print(f"\n[Step 2] 尝试 TCP 建立连接并发送 -> {self.target_tcp['ip']}:{self.target_tcp['port']}")

                    # 连接 TCP
                    client.connect_tcp(self.target_tcp['ip'], self.target_tcp['port'])

                    # TCP 模式下 send_request 使用 socket
                    client.send_request(
                        service_id=SERVICE_ID,
                        method_id=METHOD_ID,
                        payload=b'\x01\x02'
                    )

                    if self.received.wait(timeout=5):
                         print("测试通过！(TCP 收到业务回复)")
                    else:
                         print("TCP 请求超时，未收到回复。")

            if not self.received.is_set():
                print("测试结束: 未收到业务回复。")

        except KeyboardInterrupt:
            print("停止")
        finally:
            client.stop()


if __name__ == "__main__":
    TestRunner().run()

