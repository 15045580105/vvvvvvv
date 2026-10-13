#!/usr/bin/env python3
"""
从 ICC SOMEIP Excel 矩阵读取服务配置，并针对两个目标设备执行连通性测试。

目标设备:
  - 192.168.62.31 (ICC_8155_Android)
  - 192.168.62.55 (ADCC - 实际IP可能与Excel不同)

用法:
  python tools/someip_connectivity_test.py
"""

import sys
import os
import json
import time
import socket
import threading
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# 确保项目路径可用
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl

from scapy.contrib.automotive.someip import (
    SOMEIP,
    SD as SOMEIP_SD,
    SDEntry_Service,
    SDEntry_EventGroup,
    SDOption_IP4_EndPoint,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("SomeIPConnTest")

# ============================================================================
# Excel 解析
# ============================================================================

EXCEL_PATH = r"d:\奇瑞\ICC SOMEIP Services Interface Description V4.400（For EEA5.1）20251030.xlsx"

SD_MULTICAST_IP = "239.71.0.2"
SD_PORT = 30490


def parse_deployment_sheet(excel_path: str) -> List[Dict[str, Any]]:
    """从 Deployment sheet (sheet index 5 = '3 SOMEIP...') 解析服务配置。"""
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    try:
        # 找到包含 Service ID / Instance ID 的 sheet
        target_sheet = None
        for name in wb.sheetnames:
            sheet = wb[name]
            for idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                vals = [str(v).strip().lower() if v else "" for v in row]
                joined = " ".join(vals)
                if "service id" in joined and "instance id" in joined and "server ip" in joined:
                    target_sheet = name
                    break
            if target_sheet:
                break

        if not target_sheet:
            logger.error("未找到包含 Deployment 信息的 sheet")
            return []

        logger.info(f"找到 Deployment sheet: {target_sheet!r}")
        sheet = wb[target_sheet]
        rows = list(sheet.iter_rows(values_only=True))

        # 找到 header 行
        header_idx = 0
        for idx, row in enumerate(rows):
            vals = [str(v).strip().lower() if v else "" for v in row]
            joined = " ".join(vals)
            if "service id" in joined and "instance id" in joined:
                header_idx = idx
                break

        headers = [str(v).strip().lower() if v else "" for v in rows[header_idx]]

        def col(keywords):
            for i, h in enumerate(headers):
                if any(k in h for k in keywords):
                    return i
            return -1

        si = col(["service id"])
        ii = col(["instance id"])
        ni = col(["service name", "interface name"])
        mvi = col(["major version"])
        mivi = col(["minor\n version", "minor version"])
        tti = col(["ttl"])
        vi = col(["vlan \n", "vlan"])
        pi = col(["transport", "udp/tcp", "protocol"])
        svi = col(["server"])
        sip = col(["server ip"])
        sp = col(["server\nport", "server port"])
        ci = col(["client"])
        cip = col(["client ip"])
        cp = col(["client\nport", "client port"])

        services = []
        for row in rows[header_idx + 1:]:
            def g(idx):
                if idx < 0 or idx >= len(row):
                    return ""
                v = row[idx]
                return "" if v is None else str(v).strip()

            service_name = g(ni)
            service_id_str = g(si)
            instance_id_str = g(ii)
            server_ip = g(sip)
            server_port_str = g(sp)
            client_ip = g(cip)
            transport = g(pi)
            vlan_str = g(vi)
            major_str = g(mvi)
            minor_str = g(mivi)
            ttl_str = g(tti)
            server_name = g(svi)
            client_name = g(ci)

            if not service_id_str or not server_ip:
                continue

            try:
                service_id = int(service_id_str, 16)
            except ValueError:
                continue
            try:
                instance_id = int(instance_id_str, 10) if instance_id_str else 1
            except ValueError:
                instance_id = 1
            try:
                server_port = int(server_port_str, 10) if server_port_str else 30500
            except ValueError:
                server_port = 30500
            try:
                vlan_id = int(vlan_str, 10) if vlan_str else None
            except ValueError:
                vlan_id = None

            services.append({
                "service_name": service_name,
                "service_id": service_id,
                "instance_id": instance_id,
                "server_ip": server_ip,
                "server_port": server_port,
                "server_name": server_name,
                "client_ip": client_ip,
                "client_name": client_name,
                "transport": transport,
                "vlan_id": vlan_id,
                "major_version": int(major_str, 10) if major_str else 1,
                "minor_version": int(minor_str, 10) if minor_str else 0,
                "ttl": int(ttl_str, 10) if ttl_str else 3,
            })

        return services
    finally:
        wb.close()


def parse_method_sheet(excel_path: str) -> List[Dict[str, Any]]:
    """从方法 sheet (sheet index 3 = '1 ...') 解析 Method/Event 信息。"""
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    try:
        target_sheet = None
        for name in wb.sheetnames:
            sheet = wb[name]
            for idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                vals = [str(v).strip().lower() if v else "" for v in row]
                joined = " ".join(vals)
                if "service id" in joined and "method/event id" in joined:
                    target_sheet = name
                    break
            if target_sheet:
                break

        if not target_sheet:
            logger.warning("未找到方法/事件 sheet")
            return []

        logger.info(f"找到 Method sheet: {target_sheet!r}")
        sheet = wb[target_sheet]
        rows = list(sheet.iter_rows(values_only=True))

        header_idx = 0
        for idx, row in enumerate(rows):
            vals = [str(v).strip().lower() if v else "" for v in row]
            joined = " ".join(vals)
            if "service id" in joined and "method/event id" in joined:
                header_idx = idx
                break

        headers = [str(v).strip().lower() if v else "" for v in rows[header_idx]]

        def col(keywords):
            for i, h in enumerate(headers):
                if any(k in h for k in keywords):
                    return i
            return -1

        ni = col(["service name"])
        si = col(["service id"])
        rpc_type_i = col(["rpc type"])
        mei = col(["method/event name"])
        mid = col(["method/event id"])
        egi = col(["eventgroup"])
        transport_i = col(["udp/tcp"])

        methods = []
        last_service_name = ""
        last_service_id = ""

        for row in rows[header_idx + 1:]:
            def g(idx):
                if idx < 0 or idx >= len(row):
                    return ""
                v = row[idx]
                return "" if v is None else str(v).strip()

            service_name = g(ni) or last_service_name
            service_id_str = g(si) or last_service_id
            rpc_type = g(rpc_type_i)
            method_name = g(mei)
            method_id_str = g(mid)
            eventgroup_str = g(egi)
            transport = g(transport_i)

            if service_name:
                last_service_name = service_name
            if service_id_str:
                last_service_id = service_id_str

            if not service_id_str or not method_id_str:
                continue

            try:
                service_id = int(service_id_str, 16)
            except ValueError:
                continue
            try:
                method_id = int(method_id_str, 16)
            except ValueError:
                continue

            # 解析 eventgroup
            eventgroup_id = 0x0001
            if "@" in eventgroup_str:
                try:
                    eg_part = eventgroup_str.split("@")[-1]
                    eventgroup_id = int(eg_part, 16) if eg_part.lower().startswith("0x") else int(eg_part, 16)
                except ValueError:
                    pass

            is_event = "event" in rpc_type.lower() if rpc_type else (method_id & 0x8000) != 0

            methods.append({
                "service_name": service_name,
                "service_id": service_id,
                "method_name": method_name,
                "method_id": method_id,
                "eventgroup_id": eventgroup_id,
                "rpc_type": rpc_type,
                "transport": transport,
                "is_event": is_event,
            })

        return methods
    finally:
        wb.close()


# ============================================================================
# SOME/IP 连通性测试
# ============================================================================

class SomeIPConnectivityTester:
    """轻量级 SOME/IP 连通性测试器。"""

    def __init__(self, local_ip: str, vlan_id: Optional[int] = None):
        self.local_ip = local_ip
        self.vlan_id = vlan_id
        self.sd_socket: Optional[socket.socket] = None
        self.running = False
        self.recv_thread: Optional[threading.Thread] = None
        self.discovered_services: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._offer_events: Dict[int, threading.Event] = {}

    def start(self) -> bool:
        try:
            self.sd_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sd_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sd_socket.settimeout(0.5)
            self.sd_socket.bind((self.local_ip, SD_PORT))

            # 加入组播组
            try:
                membership = socket.inet_aton(SD_MULTICAST_IP) + socket.inet_aton(self.local_ip)
                self.sd_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
            except OSError as e:
                logger.warning(f"加入组播组失败: {e}")

            # 设置组播出口
            try:
                self.sd_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                                          socket.inet_aton(self.local_ip))
            except OSError:
                pass

            self.running = True
            self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self.recv_thread.start()
            logger.info(f"SD 监听已启动: {self.local_ip}:{SD_PORT} (组播 {SD_MULTICAST_IP})")
            return True
        except Exception as e:
            logger.error(f"启动失败: {e}")
            return False

    def stop(self):
        self.running = False
        if self.sd_socket:
            try:
                self.sd_socket.close()
            except:
                pass
        if self.recv_thread:
            self.recv_thread.join(timeout=1)
        logger.info("测试器已停止")

    def _recv_loop(self):
        while self.running and self.sd_socket:
            try:
                data, addr = self.sd_socket.recvfrom(65535)
                self._process_sd(data, addr)
            except socket.timeout:
                continue
            except OSError:
                if self.running:
                    break
            except Exception:
                pass

    def _process_sd(self, data: bytes, addr: Tuple[str, int]):
        try:
            pkt = SOMEIP(data)
            if pkt.srv_id != 0xFFFF or pkt.sub_id != 0x8100:
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

            sender_ip = addr[0]
            for entry in sd_pkt.entry_array:
                if entry.type == 0x01:  # OfferService
                    svc_id = int(entry.srv_id)
                    inst_id = int(getattr(entry, 'inst_id', 0xFFFF))
                    key = f"{sender_ip}:0x{svc_id:04X}"

                    # 解析 endpoints
                    tcp_eps, udp_eps = self._extract_endpoints(entry, sd_pkt.option_array)

                    with self._lock:
                        self.discovered_services[key] = {
                            "source_ip": sender_ip,
                            "service_id": svc_id,
                            "instance_id": inst_id,
                            "tcp_endpoints": tcp_eps,
                            "udp_endpoints": udp_eps,
                        }

                    # 触发对应的 event
                    if svc_id in self._offer_events:
                        self._offer_events[svc_id].set()

                    logger.info(
                        f"  发现服务: {sender_ip} -> Service=0x{svc_id:04X} "
                        f"Instance=0x{inst_id:04X} UDP={udp_eps} TCP={tcp_eps}"
                    )

        except Exception:
            pass

    @staticmethod
    def _extract_endpoints(entry, options) -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]]]:
        tcp_eps = []
        udp_eps = []
        try:
            idx1 = getattr(entry, 'index_1', getattr(entry, 'index_1st_opts', None))
            num1 = getattr(entry, 'n_opt_1', getattr(entry, 'number_1st_opts', None))
            idx2 = getattr(entry, 'index_2', getattr(entry, 'index_2nd_opts', None))
            num2 = getattr(entry, 'n_opt_2', getattr(entry, 'number_2nd_opts', None))

            if idx1 is None or num1 is None:
                return [], []

            found_opts = []
            for k in range(idx1, idx1 + num1):
                if k < len(options):
                    found_opts.append(options[k])
            if idx2 is not None and num2 is not None:
                for k in range(idx2, idx2 + num2):
                    if k < len(options):
                        found_opts.append(options[k])

            for opt in found_opts:
                if isinstance(opt, SDOption_IP4_EndPoint):
                    ep = (opt.addr, opt.port)
                    if opt.l4_proto == 0x06:
                        tcp_eps.append(ep)
                    elif opt.l4_proto == 0x11:
                        udp_eps.append(ep)
        except Exception:
            pass
        return tcp_eps, udp_eps

    def send_find_service(self, service_id: int, target_ip: Optional[str] = None):
        """发送 FindService (组播或单播)。"""
        sd = SOMEIP_SD(flags=0x80, entry_array=[
            SDEntry_Service(type=0x00, srv_id=service_id, inst_id=0xFFFF, ttl=3)
        ])
        pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001,
                     session_id=1, msg_type=0x02) / sd

        dest_ip = target_ip if target_ip else SD_MULTICAST_IP
        try:
            self.sd_socket.sendto(bytes(pkt), (dest_ip, SD_PORT))
            logger.debug(f"  FindService(0x{service_id:04X}) -> {dest_ip}:{SD_PORT}")
        except Exception as e:
            logger.error(f"  发送 FindService 失败: {e}")

    def send_find_wildcard(self, target_ip: Optional[str] = None):
        """发送通配 FindService(0xFFFF)。"""
        self.send_find_service(0xFFFF, target_ip)

    def discover_all(self, target_ips: List[str], timeout: float = 5.0) -> Dict[str, Dict[str, Any]]:
        """对每个目标 IP 执行通配服务发现。"""
        logger.info(f"\n{'=' * 60}")
        logger.info(f"开始服务发现 (通配) 目标: {target_ips}")
        logger.info(f"{'=' * 60}")

        # 先发送通配 Find
        for tip in target_ips:
            self.send_find_wildcard(tip)
        self.send_find_wildcard()  # 组播也发一次

        time.sleep(timeout)
        return dict(self.discovered_services)

    def discover_specific(self, services: List[Dict[str, Any]], target_ip: str,
                          timeout: float = 3.0) -> Dict[str, Dict[str, Any]]:
        """针对特定服务列表发送 FindService。"""
        # 注册 offer events
        for svc in services:
            sid = svc["service_id"]
            if sid not in self._offer_events:
                self._offer_events[sid] = threading.Event()

        # 发送单播 + 组播 Find
        for svc in services:
            self.send_find_service(svc["service_id"], target_ip)
        self.send_find_service(0xFFFF)  # 通配也发

        time.sleep(timeout)

        results = {}
        with self._lock:
            for key, val in self.discovered_services.items():
                if val["source_ip"] == target_ip:
                    results[key] = val
        return results

    def test_rpc(self, service_id: int, method_id: int, target_ip: str,
                 target_port: int, payload: bytes = b'\x00',
                 timeout: float = 3.0) -> Optional[bytes]:
        """发送 RPC Request 并等待 Response。"""
        # 创建临时业务 socket
        biz_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        biz_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        biz_socket.settimeout(timeout)

        # 绑定到随机端口
        local_biz_port = 0
        for _ in range(20):
            p = 30800 + (hash(str(time.time())) % 1000)
            try:
                biz_socket.bind((self.local_ip, p))
                local_biz_port = p
                break
            except OSError:
                continue
        if local_biz_port == 0:
            biz_socket.bind((self.local_ip, 0))
            local_biz_port = biz_socket.getsockname()[1]

        # 构建 SOME/IP Request
        req = SOMEIP(
            srv_id=service_id,
            sub_id=method_id,
            client_id=0x7001,
            session_id=1,
            msg_type=0x00,  # REQUEST
            retcode=0x00,
        ) / payload

        response = None
        try:
            biz_socket.sendto(bytes(req), (target_ip, target_port))
            logger.info(f"  RPC Req: Service=0x{service_id:04X} Method=0x{method_id:04X} "
                        f"-> {target_ip}:{target_port} (from :{local_biz_port})")

            try:
                data, addr = biz_socket.recvfrom(65535)
                resp_pkt = SOMEIP(data)
                if resp_pkt.srv_id == service_id and resp_pkt.sub_id == method_id:
                    response = bytes(resp_pkt.payload)
                    logger.info(f"  RPC Resp: Type=0x{resp_pkt.msg_type:02X} "
                                f"RetCode=0x{resp_pkt.retcode:02X} Payload={response.hex()}")
                else:
                    logger.warning(f"  收到不匹配的响应: Srv=0x{resp_pkt.srv_id:04X} "
                                   f"Method=0x{resp_pkt.sub_id:04X}")
            except socket.timeout:
                logger.warning(f"  RPC 响应超时 ({timeout}s)")
        except Exception as e:
            logger.error(f"  RPC 发送失败: {e}")
        finally:
            biz_socket.close()

        return response


# ============================================================================
# 主测试流程
# ============================================================================

def main():
    print("=" * 70)
    print("  ICC SOMEIP 连通性测试工具")
    print("  目标设备: 192.168.62.31 (ICC), 192.168.62.55 (ADCC)")
    print("=" * 70)

    # 1. 读取 Excel
    print(f"\n[1] 读取 Excel 矩阵: {EXCEL_PATH}")
    try:
        deployment = parse_deployment_sheet(EXCEL_PATH)
        methods = parse_method_sheet(EXCEL_PATH)
    except Exception as e:
        logger.error(f"读取 Excel 失败: {e}")
        return

    print(f"    解析到 {len(deployment)} 条 Deployment 记录")
    print(f"    解析到 {len(methods)} 条 Method/Event 记录")

    # 2. 按目标设备分组
    local_ip = "192.168.62.55"
    target_devices = {
        "192.168.62.31": {"name": "ICC_8155_Android", "services": [], "methods": []},
        "192.168.62.55": {"name": "ADCC (本地)", "services": [], "methods": []},
    }

    for svc in deployment:
        sip = svc["server_ip"]
        if sip in target_devices:
            target_devices[sip]["services"].append(svc)
        # 也检查 .11 映射到 .55 (ADCC)
        elif sip == "192.168.62.11":
            target_devices["192.168.62.55"]["services"].append(svc)

    for m in methods:
        # 根据 service_id 匹配到对应的 server
        for tip, info in target_devices.items():
            for svc in info["services"]:
                if svc["service_id"] == m["service_id"]:
                    info["methods"].append(m)
                    break

    for tip, info in target_devices.items():
        svc_ids = set(s["service_id"] for s in info["services"])
        print(f"\n  设备 {tip} ({info['name']}):")
        print(f"    服务数: {len(svc_ids)} ({', '.join(f'0x{s:04X}' for s in sorted(svc_ids))})")
        print(f"    方法/事件数: {len(info['methods'])}")

    # 3. 启动测试器
    print(f"\n[2] 启动 SOME/IP 测试器 (本地IP={local_ip})")
    tester = SomeIPConnectivityTester(local_ip)
    if not tester.start():
        logger.error("测试器启动失败")
        return

    try:
        # 4. 通配服务发现
        target_ips = [tip for tip in target_devices if tip != local_ip]
        if local_ip in target_devices and target_devices[local_ip]["services"]:
            # 也测试本地 IP 上可能的服务 (ADCC 可能不在本机)
            pass

        all_discovered = tester.discover_all(target_ips, timeout=5.0)

        print(f"\n{'=' * 60}")
        print(f"  服务发现结果 (通配)")
        print(f"{'=' * 60}")
        if all_discovered:
            for key, info in sorted(all_discovered.items()):
                eps = []
                if info["udp_endpoints"]:
                    eps.append(f"UDP={info['udp_endpoints']}")
                if info["tcp_endpoints"]:
                    eps.append(f"TCP={info['tcp_endpoints']}")
                print(f"  [{info['source_ip']}] Service=0x{info['service_id']:04X} "
                      f"Instance=0x{info['instance_id']:04X} {' | '.join(eps)}")
            print(f"  共发现 {len(all_discovered)} 个服务")
        else:
            print("  未发现任何服务!")

        # 5. 针对每个目标设备做具体服务发现
        for tip in target_ips:
            info = target_devices[tip]
            if not info["services"]:
                continue

            print(f"\n{'=' * 60}")
            print(f"  针对性服务发现: {tip} ({info['name']})")
            print(f"{'=' * 60}")

            specific = tester.discover_specific(info["services"], tip, timeout=3.0)

            found_ids = set()
            for key, val in specific.items():
                found_ids.add(val["service_id"])

            for svc in info["services"]:
                sid = svc["service_id"]
                found = sid in found_ids
                state = "OK" if found else "FAIL"
                print(f"  [{state}] 0x{sid:04X} {svc['service_name']} "
                      f"({svc['transport']})")

        # 6. 尝试 RPC 测试
        print(f"\n{'=' * 60}")
        print(f"  RPC 连通性测试")
        print(f"{'=' * 60}")

        # 为每个已发现的服务选取一个 RPC Method 进行测试
        tested_services = set()
        for tip in target_ips:
            info = target_devices[tip]
            for svc in info["services"]:
                sid = svc["service_id"]
                if sid in tested_services:
                    continue

                # 找到该服务的第一个非 Event Method
                rpc_methods = [m for m in info["methods"]
                               if m["service_id"] == sid and not m["is_event"]]
                event_methods = [m for m in info["methods"]
                                 if m["service_id"] == sid and m["is_event"]]

                # 获取目标端口
                target_port = svc["server_port"]

                # 检查是否通过发现获得了实际端口
                for key, val in all_discovered.items():
                    if val["source_ip"] == tip and val["service_id"] == sid:
                        if val["udp_endpoints"]:
                            target_port = val["udp_endpoints"][0][1]
                        elif val["tcp_endpoints"]:
                            target_port = val["tcp_endpoints"][0][1]
                        break

                if rpc_methods:
                    m = rpc_methods[0]
                    print(f"\n  测试 RPC: Service=0x{sid:04X} ({svc['service_name']}) "
                          f"Method=0x{m['method_id']:04X} ({m['method_name']}) "
                          f"-> {tip}:{target_port}")
                    result = tester.test_rpc(
                        service_id=sid,
                        method_id=m["method_id"],
                        target_ip=tip,
                        target_port=target_port,
                        payload=b'\x00',
                        timeout=3.0,
                    )
                    if result is not None:
                        print(f"    => 成功! Response: {result.hex() if result else '(empty)'}")
                    else:
                        print(f"    => 未收到响应")
                    tested_services.add(sid)
                elif event_methods:
                    m = event_methods[0]
                    print(f"\n  测试 Event: Service=0x{sid:04X} ({svc['service_name']}) "
                          f"Method=0x{m['method_id']:04X} ({m['method_name']}) "
                          f"-> {tip}:{target_port}")
                    # Event 用 Notification 类型发送
                    result = tester.test_rpc(
                        service_id=sid,
                        method_id=m["method_id"],
                        target_ip=tip,
                        target_port=target_port,
                        payload=b'\x00',
                        timeout=3.0,
                    )
                    if result is not None:
                        print(f"    => 收到响应: {result.hex() if result else '(empty)'}")
                    else:
                        print(f"    => 未收到响应 (Event 可能需要订阅)")
                    tested_services.add(sid)

        # 7. 额外: 对所有已知服务 ID 做一次盲探 (发送简单请求)
        print(f"\n{'=' * 60}")
        print(f"  盲探测试 (对所有 Excel 中的服务发送 Request)")
        print(f"{'=' * 60}")

        all_service_ids = set()
        for svc in deployment:
            all_service_ids.add((svc["service_id"], svc["server_ip"], svc["server_port"],
                                 svc["service_name"]))

        for sid, sip, sport, sname in sorted(all_service_ids):
            if sip not in target_ips:
                continue
            print(f"\n  盲探: 0x{sid:04X} ({sname}) -> {sip}:{sport}")
            result = tester.test_rpc(
                service_id=sid,
                method_id=0x0001,  # 通用 method id
                target_ip=sip,
                target_port=sport,
                payload=b'\x00',
                timeout=2.0,
            )
            if result is not None:
                print(f"    => 有响应! {result.hex() if result else '(empty)'}")
            else:
                print(f"    => 无响应")

    except KeyboardInterrupt:
        print("\n用户中断")
    finally:
        tester.stop()

    print(f"\n{'=' * 70}")
    print("  测试完成")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
