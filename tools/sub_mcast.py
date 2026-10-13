#!/usr/bin/env python3
"""Try sending Subscribe to SD multicast address instead of unicast."""
import sys, time, threading
sys.path.insert(0, r"d:\VCC")
OUT = r"d:\VCC\tools\sub_mcast_result.txt"

from scapy.all import conf
conf.sniff_promisc = False
from scapy.layers.l2 import Ether, Dot1Q
from scapy.layers.inet import IP, UDP
from scapy.sendrecv import sendp, sniff
from scapy.arch import get_if_list, get_if_addr, get_if_hwaddr
from scapy.contrib.automotive.someip import (
    SOMEIP, SD as SOMEIP_SD, SDEntry_EventGroup, SDOption_IP4_EndPoint,
)

LOCAL_IP = "192.168.62.5"
TARGET_IP = "192.168.62.31"
VLAN_ID = 62
SD_MCAST = "239.0.0.255"
SD_PORT = 30490
CLIENT_ID = 0x7001
TARGET_MAC = "02:51:52:00:00:1f"

iface = local_mac = None
for i in get_if_list():
    try:
        a = get_if_addr(i)
        if a.startswith("192.168.62."):
            iface = i
            local_mac = get_if_hwaddr(i)
            LOCAL_IP = a
            break
    except:
        pass

out = []
def log(m):
    out.append(str(m))

# Capture
all_pkts = []
def capture():
    pkts = sniff(iface=iface, store=True, timeout=20)
    all_pkts.extend(pkts)

t = threading.Thread(target=capture, daemon=True)
t.start()
time.sleep(1)

def make_subscribe(svc_id, eg_id, client_port, dst_ip, dst_mac, session_id):
    option = SDOption_IP4_EndPoint(type=0x04, addr=LOCAL_IP, l4_proto=0x11, port=client_port)
    entry = SDEntry_EventGroup(
        type=0x06, srv_id=svc_id, inst_id=0xFFFF,
        major_ver=0xFF, ttl=3, cnt=0, eventgroup_id=eg_id,
    )
    entry.index_1 = 0
    entry.n_opt_1 = 1
    sd = SOMEIP_SD(flags=0x80, entry_array=[entry], option_array=[option])
    someip_pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=CLIENT_ID,
                        session_id=session_id, msg_type=0x02) / sd
    return (Ether(src=local_mac, dst=dst_mac) /
            Dot1Q(vlan=VLAN_ID) /
            IP(src=LOCAL_IP, dst=dst_ip) /
            UDP(sport=client_port, dport=SD_PORT) /
            someip_pkt)

# Strategy 1: Subscribe to SD multicast IP + multicast MAC
log("=== Strategy 1: Subscribe to multicast 239.0.0.255 ===")
pkt = make_subscribe(0xA994, 0x0001, 40000, SD_MCAST, "01:00:5e:00:00:ff", 1)
sendp(pkt, iface=iface, verbose=False)
log(f"TX: dst={SD_MCAST} mac=01:00:5e:00:00:ff len={len(bytes(pkt))}")
time.sleep(3)

# Strategy 2: Subscribe to SD multicast IP + broadcast MAC
log("=== Strategy 2: Subscribe to multicast IP + broadcast MAC ===")
pkt = make_subscribe(0xA994, 0x0001, 40001, SD_MCAST, "ff:ff:ff:ff:ff:ff", 2)
sendp(pkt, iface=iface, verbose=False)
log(f"TX: dst={SD_MCAST} mac=ff:ff:ff:ff:ff:ff len={len(bytes(pkt))}")
time.sleep(3)

# Strategy 3: Subscribe to unicast IP + multicast MAC
log("=== Strategy 3: Subscribe to unicast IP + multicast MAC ===")
pkt = make_subscribe(0xA994, 0x0001, 40002, TARGET_IP, "01:00:5e:00:00:ff", 3)
sendp(pkt, iface=iface, verbose=False)
log(f"TX: dst={TARGET_IP} mac=01:00:5e:00:00:ff len={len(bytes(pkt))}")
time.sleep(3)

# Strategy 4: Subscribe to unicast IP + target MAC
log("=== Strategy 4: Subscribe to unicast IP + target MAC ===")
pkt = make_subscribe(0xA994, 0x0001, 40003, TARGET_IP, TARGET_MAC, 4)
sendp(pkt, iface=iface, verbose=False)
log(f"TX: dst={TARGET_IP} mac={TARGET_MAC} len={len(bytes(pkt))}")
time.sleep(3)

# Strategy 5: Subscribe to broadcast IP + broadcast MAC
log("=== Strategy 5: Subscribe to broadcast 255.255.255.255 ===")
pkt = make_subscribe(0xA994, 0x0001, 40004, "255.255.255.255", "ff:ff:ff:ff:ff:ff", 5)
sendp(pkt, iface=iface, verbose=False)
log(f"TX: dst=255.255.255.255 mac=ff:ff:ff:ff:ff:ff len={len(bytes(pkt))}")
time.sleep(5)

t.join(timeout=5)

# Analyze
from_icc_non_offer = 0
for p in all_pkts:
    if Dot1Q not in p or IP not in p or UDP not in p:
        continue
    src_ip = p[IP].src
    if src_ip != TARGET_IP:
        continue
    # Check if it's NOT an SD Offer (i.e., a response to our subscribe)
    try:
        udp_payload = bytes(p[UDP].payload)
        if len(udp_payload) >= 16:
            someip = SOMEIP(udp_payload)
            is_sd = someip.srv_id == 0xFFFF and someip.sub_id == 0x8100
            if not is_sd:
                from_icc_non_offer += 1
                log(f"  NON-OFFER from ICC: {src_ip}:{p[UDP].sport} -> {p[IP].dst}:{p[UDP].dport} "
                    f"srv=0x{someip.srv_id:04X} mth=0x{someip.sub_id:04X} type=0x{someip.msg_type:02X}")
            else:
                # Check if it's a SubscribeAck (has entry type 0x07)
                try:
                    if isinstance(someip.payload, SOMEIP_SD):
                        sd = someip.payload
                    elif hasattr(someip.payload, 'load'):
                        sd = SOMEIP_SD(someip.payload.load)
                    else:
                        sd = None
                    if sd:
                        for e in sd.entry_array:
                            if e.type == 0x07:
                                from_icc_non_offer += 1
                                log(f"  SUBACK from ICC: svc=0x{int(e.srv_id):04X} grp=0x{getattr(e, 'eventgroup_id', 0):04X}")
                except:
                    pass
    except:
        pass

log(f"\nTotal captured: {len(all_pkts)}")
log(f"Non-Offer responses from ICC: {from_icc_non_offer}")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
