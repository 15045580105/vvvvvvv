#!/usr/bin/env python3
"""Test passive event listening, TCP connection, and direct SOME/IP requests to ICC."""
import sys, struct, time, threading, subprocess, socket
sys.path.insert(0, r"d:\VCC")

OUT = r"d:\VCC\tools\sd_passive_result.txt"
buf = []
def log(m=""):
    buf.append(str(m))
    print(m)

from scapy.layers.l2 import Ether, Dot1Q
from scapy.layers.inet import IP, UDP, TCP
from scapy.sendrecv import sendp, sniff
from scapy.arch import get_if_list, get_if_addr, get_if_hwaddr

iface = local_ip = local_mac = None
for i in get_if_list():
    try:
        a = get_if_addr(i)
        if a.startswith("192.168.62."):
            iface = i; local_ip = a; local_mac = get_if_hwaddr(i); break
    except: pass
log(f"Local: {local_ip} MAC: {local_mac}")

target_mac = None
subprocess.run(["ping", "-n", "1", "-w", "1000", "192.168.62.31"], capture_output=True, timeout=5)
r = subprocess.run(["arp", "-a", "-N", local_ip], capture_output=True, text=True, timeout=5)
for line in r.stdout.splitlines():
    if "192.168.62.31" in line:
        for p in line.split():
            if len(p) == 17 and p.count("-") == 5:
                target_mac = p.replace("-", ":").lower()
log(f"Target MAC: {target_mac}")

dst_mac = target_mac or "ff:ff:ff:ff:ff:ff"

# Collect all packets from ICC
all_from_icc = []
sd_offers = []
non_sd = []

def cap_all(pkt):
    try:
        if Dot1Q not in pkt or pkt[Dot1Q].vlan != 62: return
        if IP not in pkt or pkt[IP].src != "192.168.62.31": return
        
        if UDP in pkt:
            p = bytes(pkt[UDP].payload)
            if len(p) >= 16:
                srv = struct.unpack(">H", p[0:2])[0]
                mid = struct.unpack(">H", p[2:4])[0]
                sport = pkt[UDP].sport
                dport = pkt[UDP].dport
                if srv == 0xFFFF and mid == 0x8100:
                    sd_offers.append((pkt, p, sport, dport))
                else:
                    non_sd.append((pkt, p, sport, dport))
                    log(f"  NON-SD UDP: {pkt[IP].src}:{sport}->{dport} srv=0x{srv:04X} mid=0x{mid:04X} {p[:20].hex()}")
            elif len(p) > 0:
                non_sd.append((pkt, p, pkt[UDP].sport, pkt[UDP].dport))
                log(f"  SHORT UDP: {pkt[IP].src}:{pkt[UDP].sport}->{pkt[UDP].dport} {p.hex()}")
        
        if TCP in pkt:
            p = bytes(pkt[TCP].payload)
            if len(p) > 0:
                non_sd.append((pkt, p, pkt[TCP].sport, pkt[TCP].dport))
                log(f"  TCP DATA: {pkt[IP].src}:{pkt[TCP].sport}->{pkt[TCP].dport} {p[:20].hex()}")
            # Also capture SYN/ACK
            flags = pkt[TCP].flags
            if flags & 0x12 == 0x12:  # SYN-ACK
                log(f"  TCP SYN-ACK: {pkt[IP].src}:{pkt[TCP].sport}->{pkt[TCP].dport}")
            elif flags & 0x14 == 0x14:  # RST-ACK
                log(f"  TCP RST-ACK: {pkt[IP].src}:{pkt[TCP].sport}->{pkt[TCP].dport}")
    except: pass

# Start sniffing
sniff_t = threading.Thread(target=lambda: sniff(iface=iface, prn=cap_all, store=0, timeout=120), daemon=True)
sniff_t.start()
time.sleep(0.5)

# Phase 1: Passive listen (15s) - see what ICC sends without any interaction
log(f"\n=== Phase 1: Passive Listen (15s) ===")
time.sleep(15)
log(f"  SD packets: {len(sd_offers)}")
log(f"  Non-SD packets: {len(non_sd)}")

# Phase 2: Send FindService and watch for changes
log(f"\n=== Phase 2: FindService ===")
from scapy.contrib.automotive.someip import SDEntry_Service
from app.common.communication.clients.someip import SOMEIP, SOMEIP_SD

find_entry = SDEntry_Service(type=0x00, srv_id=0xFFFF, inst_id=0xFFFF, major_ver=0xFF, ttl=0xFF)
find_sd = SOMEIP_SD(flags=0xC0, entry_array=[find_entry])
find_someip = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001, session_id=0x0099, msg_type=0x02) / find_sd
find_bytes = bytes(find_someip)

find_pkt = (
    Ether(src=local_mac, dst="01:00:5e:00:00:ff") /
    Dot1Q(vlan=62) /
    IP(src=local_ip, dst="239.0.0.255") /
    UDP(sport=30490, dport=30490) / find_bytes
)
before_sd = len(sd_offers)
before_nonsd = len(non_sd)
for _ in range(3):
    sendp(find_pkt, iface=iface, verbose=False)
    time.sleep(0.3)
time.sleep(5)
log(f"  SD after Find: +{len(sd_offers)-before_sd}")
log(f"  Non-SD after Find: +{len(non_sd)-before_nonsd}")

# Phase 3: Try Subscribe on BUSINESS port (30500) instead of SD port (30490)
log(f"\n=== Phase 3: Subscribe on business port ===")
from scapy.contrib.automotive.someip import SDEntry_EventGroup
from app.common.communication.clients.someip import SDOption_IP4_EndPoint

for svc in [0xA994, 0xA995, 0xAC0C]:
    e = SDEntry_EventGroup(type=0x06, srv_id=svc, inst_id=0x0001, major_ver=0x01, ttl=0xFF, cnt=0, eventgroup_id=0x0001)
    e.index_1 = 0
    e.n_opt_1 = 1
    o = SDOption_IP4_EndPoint(type=0x04, addr=local_ip, l4_proto=0x11, port=30501)
    sd = SOMEIP_SD(flags=0xC0, entry_array=[e], option_array=[o])
    sm = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001, session_id=0x0010+svc, msg_type=0x02) / sd
    b = bytes(sm)
    
    # Send to business port
    pkt = (
        Ether(src=local_mac, dst=dst_mac) / Dot1Q(vlan=62) /
        IP(src=local_ip, dst="192.168.62.31") /
        UDP(sport=30501, dport=30500) / b
    )
    log(f"  Subscribe 0x{svc:04X} -> 192.168.62.31:30500 (business port)")
    sendp(pkt, iface=iface, verbose=False)
    time.sleep(0.5)

time.sleep(5)
log(f"  SD after Sub-on-business: +{len(sd_offers)-before_sd}")
log(f"  Non-SD after Sub-on-business: +{len(non_sd)-before_nonsd}")

# Phase 4: TCP SYN to ICC service port
log(f"\n=== Phase 4: TCP SYN to ICC ===")
before_nonsd = len(non_sd)

# Try TCP SYN with VLAN tag via Scapy L2
tcp_syn = (
    Ether(src=local_mac, dst=dst_mac) / Dot1Q(vlan=62) /
    IP(src=local_ip, dst="192.168.62.31") /
    TCP(sport=30501, dport=30500, flags="S", seq=1000)
)
log(f"  TCP SYN -> 192.168.62.31:30500")
sendp(tcp_syn, iface=iface, verbose=False)
time.sleep(3)
log(f"  Responses after TCP SYN: +{len(non_sd)-before_nonsd}")

# Try TCP SYN to SD port
tcp_syn2 = (
    Ether(src=local_mac, dst=dst_mac) / Dot1Q(vlan=62) /
    IP(src=local_ip, dst="192.168.62.31") /
    TCP(sport=30501, dport=30490, flags="S", seq=2000)
)
log(f"  TCP SYN -> 192.168.62.31:30490")
sendp(tcp_syn2, iface=iface, verbose=False)
time.sleep(3)
log(f"  Responses after TCP SYN to SD port: +{len(non_sd)-before_nonsd}")

# Phase 5: Direct SOME/IP method call (request)
log(f"\n=== Phase 5: Direct SOME/IP Request ===")
# ICC_Aom (0xAC04) has method GetRenderDBInfo (0x0001, TCP)
# Try sending a request via UDP to the SD port
someip_req = struct.pack(">HH", 0xAC04, 0x0001)  # srv_id, method_id
someip_req += struct.pack(">I", 8)  # length (just header = 8)
someip_req += struct.pack(">H", 0x7001)  # client_id
someip_req += struct.pack(">H", 0x0001)  # session_id
someip_req += bytes([0x01, 0x01, 0x00, 0x00])  # proto, iface, type=REQUEST, retcode

req_pkt = (
    Ether(src=local_mac, dst=dst_mac) / Dot1Q(vlan=62) /
    IP(src=local_ip, dst="192.168.62.31") /
    UDP(sport=30501, dport=30500) / someip_req
)
before_nonsd = len(non_sd)
log(f"  SOME/IP Request svc=0xAC04 method=0x0001 -> 192.168.62.31:30500")
sendp(req_pkt, iface=iface, verbose=False)
time.sleep(5)
log(f"  Responses: +{len(non_sd)-before_nonsd}")

# Also try to SD port
req_pkt2 = (
    Ether(src=local_mac, dst=dst_mac) / Dot1Q(vlan=62) /
    IP(src=local_ip, dst="192.168.62.31") /
    UDP(sport=30501, dport=30490) / someip_req
)
log(f"  SOME/IP Request svc=0xAC04 method=0x0001 -> 192.168.62.31:30490")
sendp(req_pkt2, iface=iface, verbose=False)
time.sleep(5)
log(f"  Responses: +{len(non_sd)-before_nonsd}")

# Phase 6: Try sending Subscribe with TCP endpoint option (instead of UDP)
log(f"\n=== Phase 6: Subscribe with TCP endpoint option ===")
e = SDEntry_EventGroup(type=0x06, srv_id=0xA994, inst_id=0x0001, major_ver=0x01, ttl=0xFF, cnt=0, eventgroup_id=0x0001)
e.index_1 = 0
e.n_opt_1 = 1
o_tcp = SDOption_IP4_EndPoint(type=0x04, addr=local_ip, l4_proto=0x06, port=30501)  # TCP!
sd_tcp = SOMEIP_SD(flags=0xC0, entry_array=[e], option_array=[o_tcp])
sm_tcp = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001, session_id=0x0020, msg_type=0x02) / sd_tcp
b_tcp = bytes(sm_tcp)

pkt_tcp = (
    Ether(src=local_mac, dst=dst_mac) / Dot1Q(vlan=62) /
    IP(src=local_ip, dst="192.168.62.31") /
    TCP(sport=30501, dport=30500, flags="A") / b_tcp  # Send SD over TCP!
)
before_nonsd = len(non_sd)
log(f"  Subscribe over TCP -> 192.168.62.31:30500")
sendp(pkt_tcp, iface=iface, verbose=False)
time.sleep(5)
log(f"  Responses: +{len(non_sd)-before_nonsd}")

# Phase 7: Try Subscribe with StopSubscribe (type=0x06 but TTL=0)
log(f"\n=== Phase 7: StopSubscribe ===")
e_stop = SDEntry_EventGroup(type=0x06, srv_id=0xA994, inst_id=0x0001, major_ver=0x01, ttl=0, cnt=0, eventgroup_id=0x0001)
e_stop.index_1 = 0
e_stop.n_opt_1 = 1
o_stop = SDOption_IP4_EndPoint(type=0x04, addr=local_ip, l4_proto=0x11, port=30501)
sd_stop = SOMEIP_SD(flags=0xC0, entry_array=[e_stop], option_array=[o_stop])
sm_stop = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001, session_id=0x0030, msg_type=0x02) / sd_stop
b_stop = bytes(sm_stop)

pkt_stop = (
    Ether(src=local_mac, dst=dst_mac) / Dot1Q(vlan=62) /
    IP(src=local_ip, dst="192.168.62.31") /
    UDP(sport=30490, dport=30490) / b_stop
)
before_nonsd = len(non_sd)
before_sd = len(sd_offers)
log(f"  StopSubscribe -> 192.168.62.31:30490")
sendp(pkt_stop, iface=iface, verbose=False)
time.sleep(5)
log(f"  SD responses: +{len(sd_offers)-before_sd}")
log(f"  Non-SD responses: +{len(non_sd)-before_nonsd}")

# Summary
log(f"\n=== Summary ===")
log(f"Total SD packets from ICC: {len(sd_offers)}")
log(f"Total non-SD packets from ICC: {len(non_sd)}")

# Show all non-SD packets
if non_sd:
    log(f"\nAll non-SD packets:")
    for i, (pkt, p, sp, dp) in enumerate(non_sd):
        proto = "TCP" if TCP in pkt else "UDP"
        log(f"  [{i}] {proto} {pkt[IP].src}:{sp}->{dp} ({len(p)} bytes): {p[:32].hex()}")
else:
    log(f"\nNo non-SD packets received from ICC at all!")
    log(f"ICC only sends SD Offer messages and nothing else.")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(buf))
print(f"\nWritten to {OUT}")
