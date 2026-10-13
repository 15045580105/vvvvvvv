#!/usr/bin/env python3
"""Comprehensive ICC SOME/IP SD test - capture Offer, build matching Subscribe, test multiple strategies."""
import sys, struct, time, threading, subprocess, socket
sys.path.insert(0, r"d:\VCC")

OUT = r"d:\VCC\tools\sd_final_result.txt"
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
log(f"Local: {local_ip} MAC: {local_mac} iface: {iface}")

# Resolve target MAC
target_mac = None
subprocess.run(["ping", "-n", "1", "-w", "1000", "192.168.62.31"], capture_output=True, timeout=5)
r = subprocess.run(["arp", "-a", "-N", local_ip], capture_output=True, text=True, timeout=5)
for line in r.stdout.splitlines():
    if "192.168.62.31" in line:
        for p in line.split():
            if len(p) == 17 and p.count("-") == 5:
                target_mac = p.replace("-", ":").lower()
log(f"Target MAC: {target_mac}")

# Step 1: Capture ICC SD Offer
log(f"\n=== Step 1: Capture ICC SD Offer ===")
captured = []
def cap_offer(pkt):
    try:
        if Dot1Q not in pkt or pkt[Dot1Q].vlan != 62: return
        if IP not in pkt or UDP not in pkt: return
        if pkt[IP].src == local_ip: return
        p = bytes(pkt[UDP].payload)
        if len(p) < 16: return
        srv = struct.unpack(">H", p[0:2])[0]
        mid = struct.unpack(">H", p[2:4])[0]
        if srv == 0xFFFF and mid == 0x8100:
            captured.append(p)
    except: pass

sniff(iface=iface, prn=cap_offer, store=0, timeout=8)
log(f"Captured {len(captured)} SD packets")

if not captured:
    log("No SD packets captured! Exiting.")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(buf))
    sys.exit(1)

# Parse first Offer with Scapy
from scapy.contrib.automotive.someip import SOMEIP as ScapySOMEIP
icc_pkt = ScapySOMEIP(captured[0])
sd_layer = icc_pkt.payload
offers = []
for e in sd_layer.entry_array:
    info = {"type": e.type, "srv_id": e.srv_id, "inst_id": e.inst_id, 
            "major_ver": e.major_ver, "ttl": e.ttl}
    if hasattr(e, 'minor_ver'):
        info["minor_ver"] = e.minor_ver
    if hasattr(e, 'eventgroup_id'):
        info["eventgroup_id"] = e.eventgroup_id
    offers.append(info)
    log(f"  Offer: svc=0x{e.srv_id:04X} inst=0x{e.inst_id:04X} major={e.major_ver} ttl={e.ttl}")

options_info = []
for o in sd_layer.option_array:
    info = {"type": o.type, "addr": o.addr, "l4_proto": o.l4_proto, "port": o.port}
    options_info.append(info)
    proto_name = "UDP" if o.l4_proto == 0x11 else "TCP"
    log(f"  Option: {o.addr}:{o.port} ({proto_name})")

# Step 2: Build Subscribe using EXACT ICC Offer parameters
log(f"\n=== Step 2: Build Subscribe ===")

from app.common.communication.clients.someip import SOMEIP, SOMEIP_SD, SDOption_IP4_EndPoint
from scapy.contrib.automotive.someip import SDEntry_EventGroup

# Use exact values from ICC Offer
target_svc = 0xA994
target_inst = 0x0001  # From Offer (NOT 0xFFFF!)
target_major = 0x01   # From Offer (NOT 0xFF!)
target_eg = 0x0001
client_port = 30501

log(f"Target: svc=0x{target_svc:04X} inst=0x{target_inst:04X} major={target_major} eg=0x{target_eg:04X}")

# Build with Scapy
option = SDOption_IP4_EndPoint(type=0x04, addr=local_ip, l4_proto=0x11, port=client_port)
entry = SDEntry_EventGroup(type=0x06, srv_id=target_svc, inst_id=target_inst, 
                           major_ver=target_major, ttl=0xFF, cnt=0, eventgroup_id=target_eg)
entry.index_1 = 0
entry.n_opt_1 = 1

sd_pkt = SOMEIP_SD(flags=0xC0, entry_array=[entry], option_array=[option])
someip_pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001, session_id=0x0001, msg_type=0x02) / sd_pkt
scapy_sub = bytes(someip_pkt)

log(f"\nScapy Subscribe ({len(scapy_sub)} bytes):")
for row in range(0, len(scapy_sub), 16):
    hx = " ".join(f"{b:02X}" for b in scapy_sub[row:row+16])
    log(f"  {row:04X}: {hx}")

# Also build raw version (to have full control)
def build_raw_sub(svc_id, inst_id, major_ver, eg_id, client_port, ttl=0xFF, session_id=1):
    """Build raw SOME/IP SD SubscribeEventGroup."""
    entry = bytes([
        0x06,  # type = SubscribeEventGroup
        0x00,  # index_1
        0x10,  # n_opt_1=1, n_opt_2=0
        0x00,  # index_2
        (svc_id >> 8) & 0xFF, svc_id & 0xFF,
        (inst_id >> 8) & 0xFF, inst_id & 0xFF,
        major_ver,
        0x00, 0x00, ttl,
        0x00,  # counter
        0x00,  # reserved
        (eg_id >> 8) & 0xFF, eg_id & 0xFF,
    ])
    ip_bytes = bytes(int(x) for x in local_ip.split("."))
    option = bytes([0x00, 0x09, 0x04, 0x00]) + ip_bytes + bytes([0x00, 0x11,
        (client_port >> 8) & 0xFF, client_port & 0xFF])
    
    # Standard SD format (no entries_array_length based on analysis)
    sd_body = entry + option
    sd_header = bytes([0xC0, 0x00, 0x00, 0x00]) + struct.pack(">I", len(sd_body))
    sd_payload = sd_header + sd_body
    
    someip = struct.pack(">HH", 0xFFFF, 0x8100) + struct.pack(">I", len(sd_payload))
    someip += struct.pack(">H", 0x7001) + struct.pack(">H", session_id)
    someip += bytes([0x01, 0x01, 0x02, 0x00])
    return someip + sd_payload

raw_sub = build_raw_sub(target_svc, target_inst, target_major, target_eg, client_port)
log(f"\nRaw Subscribe ({len(raw_sub)} bytes):")
for row in range(0, len(raw_sub), 16):
    hx = " ".join(f"{b:02X}" for b in raw_sub[row:row+16])
    log(f"  {row:04X}: {hx}")

# Step 3: Test multiple strategies
log(f"\n=== Step 3: Subscribe Test ===")

all_responses = []
offer_count = [0]
subscribe_acks = []

def cap_response(pkt):
    try:
        if Dot1Q not in pkt or pkt[Dot1Q].vlan != 62: return
        if IP not in pkt: return
        if pkt[IP].src == local_ip: return
        
        # Check UDP
        if UDP in pkt:
            p = bytes(pkt[UDP].payload)
            if len(p) < 16: return
            srv = struct.unpack(">H", p[0:2])[0]
            mid = struct.unpack(">H", p[2:4])[0]
            if srv == 0xFFFF and mid == 0x8100:
                # SD packet - check if it's an Offer or SubscribeAck
                try:
                    sd_p = ScapySOMEIP(p).payload
                    for e in sd_p.entry_array:
                        if e.type == 0x01:  # OfferService
                            offer_count[0] += 1
                        elif e.type == 0x06:  # SubscribeEventGroup (Ack?)
                            subscribe_acks.append(p)
                            log(f"  SUBSCRIBE ACK from {pkt[IP].src}! svc=0x{e.srv_id:04X}")
                except:
                    pass
                return
            all_responses.append(p)
            log(f"  DATA RESP from {pkt[IP].src}: {p[:20].hex()}")
        
        # Check TCP
        if TCP in pkt:
            p = bytes(pkt[TCP].payload)
            if len(p) > 0:
                all_responses.append(p)
                log(f"  TCP DATA from {pkt[IP].src}:{pkt[TCP].sport}: {p[:20].hex()}")
    except: pass

sniff_t = threading.Thread(target=lambda: sniff(iface=iface, prn=cap_response, store=0, timeout=60), daemon=True)
sniff_t.start()
time.sleep(0.5)

# Passive listen
log(f"  Passive listen (5s)...")
time.sleep(5)
log(f"  Offers: {offer_count[0]}, Responses: {len(all_responses)}, SubAcks: {len(subscribe_acks)}")

# Strategy 1: Scapy Subscribe -> multicast SD port
dst_mac = target_mac or "ff:ff:ff:ff:ff:ff"
strategies = [
    ("Scapy Sub -> mcast 239.0.0.255:30490",
     Ether(src=local_mac, dst="01:00:5e:00:00:ff") / Dot1Q(vlan=62) /
     IP(src=local_ip, dst="239.0.0.255") / UDP(sport=30490, dport=30490) / scapy_sub),
    
    ("Scapy Sub -> unicast 192.168.62.31:30490",
     Ether(src=local_mac, dst=dst_mac) / Dot1Q(vlan=62) /
     IP(src=local_ip, dst="192.168.62.31") / UDP(sport=30490, dport=30490) / scapy_sub),
    
    ("Raw Sub -> mcast 239.0.0.255:30490",
     Ether(src=local_mac, dst="01:00:5e:00:00:ff") / Dot1Q(vlan=62) /
     IP(src=local_ip, dst="239.0.0.255") / UDP(sport=30490, dport=30490) / raw_sub),
    
    ("Raw Sub -> unicast 192.168.62.31:30490",
     Ether(src=local_mac, dst=dst_mac) / Dot1Q(vlan=62) /
     IP(src=local_ip, dst="192.168.62.31") / UDP(sport=30490, dport=30490) / raw_sub),
    
    ("Raw Sub -> unicast 192.168.62.31:30500",
     Ether(src=local_mac, dst=dst_mac) / Dot1Q(vlan=62) /
     IP(src=local_ip, dst="192.168.62.31") / UDP(sport=30501, dport=30500) / raw_sub),
    
    ("Raw Sub(inst=0xFFFF) -> unicast 192.168.62.31:30490",
     Ether(src=local_mac, dst=dst_mac) / Dot1Q(vlan=62) /
     IP(src=local_ip, dst="192.168.62.31") / UDP(sport=30490, dport=30490) / 
     build_raw_sub(0xA994, 0xFFFF, 0xFF, 0x0001, 30501)),
]

for idx, (name, pkt) in enumerate(strategies):
    before_o = offer_count[0]
    before_r = len(all_responses)
    before_a = len(subscribe_acks)
    log(f"\n  [{idx+1}] {name}")
    for _ in range(3):
        sendp(pkt, iface=iface, verbose=False)
        time.sleep(0.5)
    time.sleep(4)
    log(f"    Offers: +{offer_count[0]-before_o}, Data: +{len(all_responses)-before_r}, SubAcks: +{len(subscribe_acks)-before_a}")

# Strategy: Try TCP connection to ICC service
log(f"\n  [7] TCP connect to 192.168.62.31:30500")
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    # Need to bind to VLAN 62 IP
    s.bind((local_ip, 30501))
    s.connect(("192.168.62.31", 30500))
    log(f"    TCP Connected!")
    # Try to send some data
    s.settimeout(5)
    try:
        data = s.recv(1024)
        log(f"    Received {len(data)} bytes: {data[:20].hex()}")
    except socket.timeout:
        log(f"    No data received (timeout)")
    s.close()
except Exception as ex:
    log(f"    TCP Error: {ex}")

# Strategy: Send FindService to trigger re-offer
log(f"\n  [8] FindService (Scapy) -> mcast 239.0.0.255:30490")
from scapy.contrib.automotive.someip import SDEntry
find_entry = SDEntry(type=0x00, srv_id=0xFFFF, inst_id=0xFFFF, major_ver=0xFF, ttl=0xFF)
find_sd = SOMEIP_SD(flags=0xC0, entry_array=[find_entry])
find_someip = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001, session_id=0x0099, msg_type=0x02) / find_sd
find_bytes = bytes(find_someip)
find_pkt = (
    Ether(src=local_mac, dst="01:00:5e:00:00:ff") / Dot1Q(vlan=62) /
    IP(src=local_ip, dst="239.0.0.255") / UDP(sport=30490, dport=30490) / find_bytes
)
before_o = offer_count[0]
for _ in range(3):
    sendp(find_pkt, iface=iface, verbose=False)
    time.sleep(0.5)
time.sleep(5)
log(f"    Offers after Find: +{offer_count[0]-before_o}")

log(f"\n=== Summary ===")
log(f"Total Offers: {offer_count[0]}")
log(f"Total Data Responses: {len(all_responses)}")
log(f"Total SubscribeAcks: {len(subscribe_acks)}")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(buf))
print(f"\nWritten to {OUT}")
