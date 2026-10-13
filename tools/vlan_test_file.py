#!/usr/bin/env python3
"""VLAN-aware SOME/IP connectivity test."""
import sys, time, threading, traceback
sys.path.insert(0, r"d:\VCC")

OUT = r"d:\VCC\tools\vlan_test_result.txt"
out = []
def log(m):
    out.append(str(m))

try:
    from scapy.all import conf as scapy_conf
    scapy_conf.sniff_promisc = False
    from scapy.layers.l2 import Ether, Dot1Q
    from scapy.layers.inet import IP, UDP
    from scapy.sendrecv import sendp, sniff
    from scapy.arch import get_if_list, get_if_addr, get_if_hwaddr
    from scapy.contrib.automotive.someip import (
        SOMEIP, SD as SOMEIP_SD, SDEntry_Service, SDOption_IP4_EndPoint,
    )
    log("scapy OK")
except Exception as e:
    log(f"scapy ERROR: {e}")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    sys.exit(1)

LOCAL_IP = "192.168.62.5"
TARGET_IP = "192.168.62.31"
VLAN_ID = 62
SD_MCAST = "239.0.0.255"
SD_PORT = 30490
BIZ_PORT = 30500
CLIENT_ID = 0x7001

TARGET_IFACE = None
LOCAL_MAC = None
for iface in get_if_list():
    try:
        addr = get_if_addr(iface)
        if addr.startswith("192.168.62."):
            TARGET_IFACE = iface
            LOCAL_IP = addr
            LOCAL_MAC = get_if_hwaddr(iface)
            break
    except Exception:
        pass

if not TARGET_IFACE:
    log("ERROR: no 192.168.62.x interface")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    sys.exit(1)

log(f"iface={TARGET_IFACE} mac={LOCAL_MAC} ip={LOCAL_IP}")

running = True
discovered = {}
offer_count = 0
lock = threading.Lock()

def process_packet(pkt):
    global offer_count
    if not running:
        return
    try:
        if Dot1Q not in pkt:
            return
        if pkt[Dot1Q].vlan != VLAN_ID:
            return
        if IP not in pkt or UDP not in pkt:
            return
        src_ip = pkt[IP].src
        if src_ip == LOCAL_IP:
            return
        udp_payload = bytes(pkt[UDP].payload)
        if len(udp_payload) < 16:
            return
        someip_pkt = SOMEIP(udp_payload)
        if someip_pkt.srv_id == 0xFFFF and someip_pkt.sub_id == 0x8100:
            try:
                if isinstance(someip_pkt.payload, SOMEIP_SD):
                    sd_pkt = someip_pkt.payload
                elif hasattr(someip_pkt.payload, 'load'):
                    sd_pkt = SOMEIP_SD(someip_pkt.payload.load)
                else:
                    return
                for entry in sd_pkt.entry_array:
                    if entry.type == 0x01:
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
                                "ip": src_ip, "udp_eps": udp_eps,
                                "tcp_eps": tcp_eps, "inst_id": inst_id,
                            }
                            offer_count += 1
                        log(f"  [Offer] Srv=0x{svc_id:04X} UDP={udp_eps} TCP={tcp_eps}")
                    elif entry.type == 0x07:
                        svc_id = int(entry.srv_id)
                        eg_id = getattr(entry, 'eventgroup_id', 0)
                        ttl = getattr(entry, 'ttl', 0)
                        log(f"  [SubAck] Srv=0x{svc_id:04X} Grp=0x{eg_id:04X} TTL={ttl}")
            except Exception as e:
                log(f"  SD parse err: {e}")
        else:
            log(f"  [Resp] Srv=0x{someip_pkt.srv_id:04X} Mth=0x{someip_pkt.sub_id:04X} Type=0x{someip_pkt.msg_type:02X}")
    except Exception:
        pass

def build_vlan_pkt(someip_pkt, dst_mac, dst_ip, sport, dport):
    return (Ether(src=LOCAL_MAC, dst=dst_mac) /
            Dot1Q(vlan=VLAN_ID) /
            IP(src=LOCAL_IP, dst=dst_ip) /
            UDP(sport=sport, dport=dport) /
            someip_pkt)

def send_find_service(service_id=0xFFFF, unicast=False):
    sd = SOMEIP_SD(flags=0x80, entry_array=[
        SDEntry_Service(type=0x00, srv_id=service_id, inst_id=0xFFFF, ttl=3)
    ])
    someip_pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=CLIENT_ID,
                        session_id=1, msg_type=0x02) / sd
    if unicast:
        dst_ip = TARGET_IP
        dst_mac = "ff:ff:ff:ff:ff:ff"
    else:
        dst_ip = SD_MCAST
        dst_mac = "01:00:5e:00:00:ff"
    pkt = build_vlan_pkt(someip_pkt, dst_mac, dst_ip, SD_PORT, SD_PORT)
    sendp(pkt, iface=TARGET_IFACE, verbose=False)

def send_rpc(svc_id, method_id, target_port=BIZ_PORT):
    someip_pkt = SOMEIP(srv_id=svc_id, sub_id=method_id,
                        client_id=CLIENT_ID, session_id=3,
                        msg_type=0x00, retcode=0x00) / b'\x00'
    pkt = build_vlan_pkt(someip_pkt, "ff:ff:ff:ff:ff:ff", TARGET_IP, SD_PORT, target_port)
    sendp(pkt, iface=TARGET_IFACE, verbose=False)

# ===== Main =====
log("=" * 50)
log("VLAN SOME/IP Test")
log(f"LOCAL={LOCAL_IP} TARGET={TARGET_IP} VLAN={VLAN_ID}")

log("\n[1] Passive listen 8s ...")
t = threading.Thread(target=lambda: sniff(iface=TARGET_IFACE, prn=process_packet, store=0, timeout=60), daemon=True)
t.start()
time.sleep(8)

with lock:
    p_count = offer_count
    p_svcs = dict(discovered)
log(f"  passive: {p_count} offers, {len(p_svcs)} services")

log("\n[2] FindService ...")
for _ in range(5):
    send_find_service(0xFFFF, False)
    send_find_service(0xFFFF, True)
    time.sleep(0.5)
time.sleep(5)

with lock:
    a_svcs = dict(discovered)
    t_offers = offer_count
log(f"  total: {t_offers} offers, {len(a_svcs)} services")
for sid, info in sorted(a_svcs.items()):
    log(f"    0x{sid:04X} -> {info['ip']} UDP={info['udp_eps']} TCP={info['tcp_eps']}")

log("\n[3] RPC test ...")
for svc_id, mid, name in [(0xA994, 1, "ParkingUI"), (0xA995, 1, "ADAS"), (0xAC0C, 1, "mapInfo")]:
    if svc_id not in a_svcs:
        log(f"  [SKIP] 0x{svc_id:04X} {name}")
        continue
    info = a_svcs[svc_id]
    tp = info["udp_eps"][0][1] if info["udp_eps"] else BIZ_PORT
    log(f"  [RPC] 0x{svc_id:04X} {name} -> {TARGET_IP}:{tp}")
    send_rpc(svc_id, mid, tp)
    time.sleep(3)

running = False
time.sleep(1)

log("\n" + "=" * 50)
log("SUMMARY")
log(f"  Passive: {len(p_svcs)} | Active: {len(a_svcs)} | Offers: {t_offers}")
for sid, info in sorted(a_svcs.items()):
    log(f"    0x{sid:04X}: UDP={info['udp_eps']} TCP={info['tcp_eps']}")
log("=" * 50)

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
