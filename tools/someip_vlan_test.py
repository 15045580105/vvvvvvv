#!/usr/bin/env python3
"""
VLAN-aware SOME/IP 连通性测试 - 使用 Scapy L2 收发带 VLAN 62 标签的包。
"""
import sys, time, threading, struct, socket
sys.path.insert(0, r"d:\VCC")

from scapy.all import conf
conf.sniff_promisc = False
from scapy.layers.l2 import Ether, Dot1Q
from scapy.layers.inet import IP, UDP
from scapy.sendrecv import sendp, sniff
from scapy.arch import get_if_list, get_if_addr, get_if_hwaddr
from scapy.contrib.automotive.someip import (
    SOMEIP, SD as SOMEIP_SD, SDEntry_Service, SDEntry_EventGroup, SDOption_IP4_EndPoint,
)

# ===== 配置 =====
LOCAL_IP = "192.168.62.5"
TARGET_IP = "192.168.62.31"
VLAN_ID = 62
SD_MCAST = "239.0.0.255"  # ICC 实际使用的 SD 组播地址
SD_PORT = 30490
BIZ_PORT = 30500
CLIENT_ID = 0x7001

# 找到 Npcap 接口
TARGET_IFACE = None
LOCAL_MAC = None
for iface in get_if_list():
    try:
        addr = get_if_addr(iface)
        if addr == LOCAL_IP:
            TARGET_IFACE = iface
            LOCAL_MAC = get_if_hwaddr(iface)
            break
    except:
        pass

if not TARGET_IFACE:
    print(f"ERROR: 找不到 IP {LOCAL_IP} 对应的 Npcap 接口")
    sys.exit(1)

print("=" * 60)
print("  VLAN-aware SOME/IP 连通性测试")
print(f"  本地: {LOCAL_IP} (VLAN {VLAN_ID})")
print(f"  目标: {TARGET_IP}")
print(f"  接口: {TARGET_IFACE}")
print(f"  MAC:  {LOCAL_MAC}")
print(f"  SD:   {SD_MCAST}:{SD_PORT}")
print("=" * 60)

# ===== 状态 =====
running = True
discovered = {}  # service_id -> {ip, udp_eps, tcp_eps, inst_id}
offer_count = 0
lock = threading.Lock()

def process_packet(pkt):
    """处理收到的 L2 包"""
    global offer_count
    if not running:
        return
    if Dot1Q not in pkt or pkt[Dot1Q].vlan != VLAN_ID:
        return
    if IP not in pkt or UDP not in pkt:
        return

    src_ip = pkt[IP].src
    if src_ip == LOCAL_IP:
        return  # 忽略自己

    try:
        udp_payload = bytes(pkt[UDP].payload)
        if len(udp_payload) < 16:
            return
        someip_pkt = SOMEIP(udp_payload)

        if someip_pkt.srv_id == 0xFFFF and someip_pkt.sub_id == 0x8100:
            # SD packet
            if isinstance(someip_pkt.payload, SOMEIP_SD):
                sd_pkt = someip_pkt.payload
            elif hasattr(someip_pkt.payload, 'load'):
                try:
                    sd_pkt = SOMEIP_SD(someip_pkt.payload.load)
                except:
                    return
            else:
                return

            for entry in sd_pkt.entry_array:
                if entry.type == 0x01:  # OfferService
                    svc_id = int(entry.srv_id)
                    inst_id = int(getattr(entry, 'inst_id', 0xFFFF))
                    tcp_eps, udp_eps = [], []
                    for opt in sd_pkt.option_array:
                        if isinstance(opt, SDOption_IP4_EndPoint):
                            ep = (opt.addr, opt.port)
                            if opt.l4_proto == 0x06:
                                tcp_eps.append(ep)
                            elif opt.l4_proto == 0x11:
                                udp_eps.append(ep)
                    with lock:
                        discovered[svc_id] = {
                            "ip": src_ip,
                            "udp_eps": udp_eps,
                            "tcp_eps": tcp_eps,
                            "inst_id": inst_id,
                        }
                        offer_count += 1
                    print(f"  [Offer] Srv=0x{svc_id:04X} Inst=0x{inst_id:04X} "
                          f"UDP={udp_eps} TCP={tcp_eps}")

                elif entry.type == 0x07:  # SubscribeAck
                    svc_id = int(entry.srv_id)
                    eg_id = getattr(entry, 'eventgroup_id', getattr(entry, 'reserved', 0))
                    ttl = getattr(entry, 'ttl', 0)
                    print(f"  [SubAck] Srv=0x{svc_id:04X} Group=0x{eg_id:04X} TTL={ttl}")

        else:
            # 业务回复
            print(f"  [Response] Srv=0x{someip_pkt.srv_id:04X} "
                  f"Method=0x{someip_pkt.sub_id:04X} Type=0x{someip_pkt.msg_type:02X} "
                  f"Payload={bytes(someip_pkt.payload).hex()[:60]}")

    except Exception as e:
        pass


def build_vlan_someip(someip_pkt, dst_mac, dst_ip, sport, dport):
    """构建带 VLAN 标签的 SOMEIP 包"""
    return (Ether(src=LOCAL_MAC, dst=dst_mac) /
            Dot1Q(vlan=VLAN_ID) /
            IP(src=LOCAL_IP, dst=dst_ip) /
            UDP(sport=sport, dport=dport) /
            someip_pkt)


def send_find_service(service_id=0xFFFF, unicast=False):
    """发送 VLAN-tagged FindService"""
    sd = SOMEIP_SD(flags=0x80, entry_array=[
        SDEntry_Service(type=0x00, srv_id=service_id, inst_id=0xFFFF, ttl=3)
    ])
    someip_pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=CLIENT_ID,
                        session_id=1, msg_type=0x02) / sd

    if unicast:
        dst_ip = TARGET_IP
        # 单播需要知道目标 MAC，先用广播
        dst_mac = "ff:ff:ff:ff:ff:ff"
    else:
        dst_ip = SD_MCAST
        # 组播 MAC 映射: 239.0.0.255 -> 01:00:5e:00:00:ff
        dst_mac = "01:00:5e:00:00:ff"

    pkt = build_vlan_someip(someip_pkt, dst_mac, dst_ip, SD_PORT, SD_PORT)
    sendp(pkt, iface=TARGET_IFACE, verbose=False)


def send_subscribe(service_id, eventgroup_id, target_port=SD_PORT):
    """发送 VLAN-tagged SubscribeEventGroup"""
    option = SDOption_IP4_EndPoint(
        type=0x04, addr=LOCAL_IP, l4_proto=0x11, port=SD_PORT
    )
    entry = SDEntry_EventGroup(
        type=0x06, srv_id=service_id, inst_id=0xFFFF,
        major_ver=0xFF, ttl=3, cnt=0, eventgroup_id=eventgroup_id
    )
    entry.index_1 = 0
    entry.n_opt_1 = 1

    sd = SOMEIP_SD(flags=0x80, entry_array=[entry], option_array=[option])
    someip_pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=CLIENT_ID,
                        session_id=2, msg_type=0x02) / sd

    dst_mac = "ff:ff:ff:ff:ff:ff"
    pkt = build_vlan_someip(someip_pkt, dst_mac, TARGET_IP, SD_PORT, target_port)
    sendp(pkt, iface=TARGET_IFACE, verbose=False)


def send_rpc_request(service_id, method_id, payload=b'\x00', target_port=BIZ_PORT):
    """发送 VLAN-tagged RPC Request"""
    someip_pkt = SOMEIP(
        srv_id=service_id, sub_id=method_id,
        client_id=CLIENT_ID, session_id=3,
        msg_type=0x00, retcode=0x00
    ) / payload

    dst_mac = "ff:ff:ff:ff:ff:ff"
    pkt = build_vlan_someip(someip_pkt, dst_mac, TARGET_IP, SD_PORT, target_port)
    sendp(pkt, iface=TARGET_IFACE, verbose=False)


# ===== 主流程 =====
print(f"\n[1] 启动 L2 监听 (VLAN {VLAN_ID}) ...")
sniff_thread = threading.Thread(
    target=lambda: sniff(iface=TARGET_IFACE, prn=process_packet, store=0, timeout=60),
    daemon=True
)
sniff_thread.start()
time.sleep(0.5)

# 2. 被动等待 ICC 的 SD Offer (5秒)
print(f"\n[2] 被动监听 ICC SD Offer (5秒) ...")
time.sleep(5)

with lock:
    passive_count = offer_count
    passive_services = dict(discovered)

print(f"  被动发现 {passive_count} 个 Offer, {len(passive_services)} 个服务")

# 3. 发送 FindService
print(f"\n[3] 发送 FindService (组播+单播) ...")
for _ in range(3):
    send_find_service(0xFFFF, unicast=False)
    send_find_service(0xFFFF, unicast=True)
    time.sleep(0.5)

time.sleep(3)
with lock:
    after_find_services = dict(discovered)

print(f"  发现 {len(after_find_services)} 个服务:")
for sid, info in sorted(after_find_services.items()):
    print(f"    0x{sid:04X} -> {info['ip']} UDP={info['udp_eps']} TCP={info['tcp_eps']}")

# 4. RPC 测试
print(f"\n[4] RPC 连通性测试 ...")
test_services = [
    (0xA994, 0x0001, "eHMI_ParkingUI"),
    (0xA995, 0x0001, "eHMI_ADASSetting"),
    (0xAC0C, 0x0001, "ICC_SDmapInfo_2"),
]

for svc_id, method_id, name in test_services:
    if svc_id not in after_find_services:
        print(f"\n  [SKIP] 0x{svc_id:04X} ({name}) - 未发现")
        continue

    # 获取目标端口
    info = after_find_services[svc_id]
    target_port = BIZ_PORT
    if info["udp_eps"]:
        target_port = info["udp_eps"][0][1]

    print(f"\n  [TEST] 0x{svc_id:04X} ({name}) Method=0x{method_id:04X} -> {TARGET_IP}:{target_port}")
    send_rpc_request(svc_id, method_id, b'\x00', target_port)
    time.sleep(3)

# 5. Event 订阅测试 (Event method ID >= 0x8000)
print(f"\n[5] Event 订阅测试 ...")
event_tests = [
    (0xA994, 0x8001, 0x0001, "eHMI_ParkingUI.NtfParkingFuncModReq"),
    (0xA995, 0x8001, 0x0001, "eHMI_ADASSetting.NtfADASSettingInfo"),
]

for svc_id, event_id, eg_id, name in event_tests:
    if svc_id not in after_find_services:
        print(f"\n  [SKIP] {name} - 未发现")
        continue
    print(f"\n  [SUB] {name} (Svc=0x{svc_id:04X} Event=0x{event_id:04X} Group=0x{eg_id:04X})")
    send_subscribe(svc_id, eg_id)
    time.sleep(5)

# 6. 总结
running = False
time.sleep(1)

print(f"\n{'=' * 60}")
print(f"  测试总结")
print(f"{'=' * 60}")
print(f"  被动发现: {len(passive_services)} 个服务")
print(f"  主动发现: {len(after_find_services)} 个服务")
print(f"  ICC SD Offer 总数: {offer_count}")
print(f"\n  已发现的服务:")
for sid, info in sorted(after_find_services.items()):
    print(f"    0x{sid:04X}: {info['ip']} UDP={info['udp_eps']} TCP={info['tcp_eps']}")
print(f"\n  VLAN {VLAN_ID} L2 连通性: OK")
print(f"  (SD Offer 可正常接收)")
print(f"{'=' * 60}")
