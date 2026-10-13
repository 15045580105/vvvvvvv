#!/usr/bin/env python3
"""Test Subscribe with raw bytes (bypass Scapy SD builder) and multiple strategies."""
import sys, struct, time, threading, subprocess
sys.path.insert(0, r"d:\VCC")

OUT = r"d:\VCC\tools\sd_raw_result.txt"
buf = []
def log(m=""):
    buf.append(str(m))

from scapy.layers.l2 import Ether, Dot1Q
from scapy.layers.inet import IP, UDP
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

# Build raw SubscribeEventGroup packet matching ICC's SD format exactly
def build_raw_subscribe(svc_id, eventgroup_id, client_port):
    """Build raw SOME/IP SD SubscribeEventGroup matching ICC Offer format."""
    # SD Entry: SubscribeEventGroup (type=0x06)
    # Format: type(1) idx1(1) n_opt1|n_opt2(1) idx2(1) svc_id(2) inst_id(2) major(1) ttl(3) cnt(1) reserved(1) eg_id(2)
    entry = bytes([
        0x06,                    # type = SubscribeEventGroup
        0x00,                    # index_1
        0x10,                    # n_opt_1=1, n_opt_2=0
        0x00,                    # index_2
        (svc_id >> 8) & 0xFF, svc_id & 0xFF,  # service ID
        0xFF, 0xFF,              # instance ID
        0x01,                    # major version
        0x00, 0x00, 0x03,        # TTL = 3
        0x00,                    # counter
        0x00,                    # reserved
        (eventgroup_id >> 8) & 0xFF, eventgroup_id & 0xFF,  # eventgroup ID
    ])
    
    # SD Option: IPv4 Endpoint
    ip_parts = [int(x) for x in local_ip.split(".")]
    option = bytes([
        0x00, 0x09,              # length = 9 (type + reserved + data)
        0x04,                    # type = IPv4 Endpoint
        0x00,                    # reserved
    ]) + bytes(ip_parts) + bytes([
        0x00,                    # reserved
        0x11,                    # L4 proto = UDP
        (client_port >> 8) & 0xFF, client_port & 0xFF,  # port
    ])
    
    # SD payload: flags(1) reserved(3) entries_len(4) entries options_len(4) options
    entries_with_len = struct.pack(">I", len(entry)) + entry
    options_with_len = struct.pack(">I", len(option)) + option
    
    # sd_length = entries_with_len + options_with_len
    sd_data = entries_with_len + options_with_len
    sd_length = struct.pack(">I", len(sd_data))
    
    sd_payload = bytes([0xC0, 0x00, 0x00, 0x00]) + sd_length + sd_data
    
    # SOMEIP header
    someip_payload = sd_payload
    length = len(someip_payload)
    someip_header = struct.pack(">HH", 0xFFFF, 0x8100)  # srv_id, method_id
    someip_header += struct.pack(">I", length)            # length
    someip_header += struct.pack(">H", 0x7001)            # client_id
    someip_header += struct.pack(">H", 0x0001)            # session_id
    someip_header += bytes([0x01, 0x01, 0x02, 0x00])      # proto, iface, type, retcode
    
    return someip_header + someip_payload

# Test with raw bytes
raw_sub = build_raw_subscribe(0xA994, 0x0001, 30501)
log(f"\nRaw Subscribe ({len(raw_sub)} bytes):")
for row in range(0, len(raw_sub), 16):
    hx = " ".join(f"{b:02X}" for b in raw_sub[row:row+16])
    log(f"  {row:04X}: {hx}")

# Also build with Scapy for comparison
from app.common.communication.clients.someip import SOMEIP, SOMEIP_SD, SDOption_IP4_EndPoint
from scapy.contrib.automotive.someip import SDEntry_EventGroup

option = SDOption_IP4_EndPoint(type=0x04, addr=local_ip, l4_proto=0x11, port=30501)
entry = SDEntry_EventGroup(type=0x06, srv_id=0xA994, inst_id=0xFFFF, major_ver=0xFF, ttl=3, cnt=0, eventgroup_id=0x0001)
entry.index_1 = 0
entry.n_opt_1 = 1
sd = SOMEIP_SD(flags=0xC0, entry_array=[entry], option_array=[option])
scapy_pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001, session_id=0x0001, msg_type=0x02) / sd
scapy_bytes = bytes(scapy_pkt)
log(f"\nScapy Subscribe ({len(scapy_bytes)} bytes):")
for row in range(0, len(scapy_bytes), 16):
    hx = " ".join(f"{b:02X}" for b in scapy_bytes[row:row+16])
    log(f"  {row:04X}: {hx}")

# Compare
log(f"\n=== Diff ===")
max_len = max(len(raw_sub), len(scapy_bytes))
for i in range(max_len):
    rb = raw_sub[i] if i < len(raw_sub) else 0
    sb = scapy_bytes[i] if i < len(scapy_bytes) else 0
    mark = " <<<" if rb != sb else ""
    log(f"  Byte {i:2d}: Raw=0x{rb:02X} Scapy=0x{sb:02X}{mark}")

# Now test: send both raw and Scapy Subscribe and listen for responses
log(f"\n=== Subscribe test ===")
responses = []
def cap(pkt):
    try:
        if Dot1Q not in pkt or pkt[Dot1Q].vlan != 62: return
        if IP not in pkt or UDP not in pkt: return
        if pkt[IP].src == local_ip: return
        p = bytes(pkt[UDP].payload)
        if len(p) < 16: return
        srv = struct.unpack(">H", p[0:2])[0]
        mid = struct.unpack(">H", p[2:4])[0]
        if srv == 0xFFFF and mid == 0x8100: return  # ignore SD
        responses.append(p)
        log(f"  RESP: {p[:20].hex()}")
    except: pass

sniff_t = threading.Thread(target=lambda: sniff(iface=iface, prn=cap, store=0, timeout=30), daemon=True)
sniff_t.start()
time.sleep(0.5)

# Strategy 1: Raw bytes -> multicast
pkt1 = (
    Ether(src=local_mac, dst="01:00:5e:00:00:ff") /
    Dot1Q(vlan=62) /
    IP(src=local_ip, dst="239.0.0.255") /
    UDP(sport=30490, dport=30490) /
    raw_sub
)
log(f"  [1] Raw -> mcast 239.0.0.255:30490")
for _ in range(5):
    sendp(pkt1, iface=iface, verbose=False)
    time.sleep(0.3)
time.sleep(3)
log(f"    Responses: {len(responses)}")

# Strategy 2: Raw bytes -> unicast to ICC
pkt2 = (
    Ether(src=local_mac, dst=target_mac or "ff:ff:ff:ff:ff:ff") /
    Dot1Q(vlan=62) /
    IP(src=local_ip, dst="192.168.62.31") /
    UDP(sport=30490, dport=30490) /
    raw_sub
)
log(f"  [2] Raw -> unicast 192.168.62.31:30490")
for _ in range(5):
    sendp(pkt2, iface=iface, verbose=False)
    time.sleep(0.3)
time.sleep(3)
log(f"    Responses: {len(responses)}")

# Strategy 3: Scapy bytes -> unicast
pkt3 = (
    Ether(src=local_mac, dst=target_mac or "ff:ff:ff:ff:ff:ff") /
    Dot1Q(vlan=62) /
    IP(src=local_ip, dst="192.168.62.31") /
    UDP(sport=30490, dport=30490) /
    scapy_bytes
)
log(f"  [3] Scapy -> unicast 192.168.62.31:30490")
for _ in range(5):
    sendp(pkt3, iface=iface, verbose=False)
    time.sleep(0.3)
time.sleep(3)
log(f"    Responses: {len(responses)}")

# Strategy 4: Raw bytes -> unicast to business port
pkt4 = (
    Ether(src=local_mac, dst=target_mac or "ff:ff:ff:ff:ff:ff") /
    Dot1Q(vlan=62) /
    IP(src=local_ip, dst="192.168.62.31") /
    UDP(sport=30501, dport=30500) /
    raw_sub
)
log(f"  [4] Raw -> unicast 192.168.62.31:30500")
for _ in range(5):
    sendp(pkt4, iface=iface, verbose=False)
    time.sleep(0.3)
time.sleep(3)
log(f"    Responses: {len(responses)}")

# Strategy 5: Try FindService with raw bytes to see if ICC responds differently
find_entry = bytes([
    0x00, 0x00, 0x00, 0x00,  # type=FindService, idx1=0, nopt=0, idx2=0
    0xFF, 0xFF,              # svc_id=0xFFFF (all)
    0xFF, 0xFF,              # inst_id=0xFFFF
    0xFF, 0x00, 0x00, 0x03,  # major=0xFF, TTL=3
])
find_sd = bytes([0xC0, 0x00, 0x00, 0x00]) + struct.pack(">I", len(find_entry)) + find_entry
find_someip = struct.pack(">HH", 0xFFFF, 0x8100) + struct.pack(">I", len(find_sd))
find_someip += struct.pack(">H", 0x7001) + struct.pack(">H", 0x0002) + bytes([0x01, 0x01, 0x02, 0x00])
find_pkt_raw = find_someip + find_sd

pkt5 = (
    Ether(src=local_mac, dst=target_mac or "ff:ff:ff:ff:ff:ff") /
    Dot1Q(vlan=62) /
    IP(src=local_ip, dst="192.168.62.31") /
    UDP(sport=30490, dport=30490) /
    find_pkt_raw
)
log(f"  [5] Raw FindService -> unicast 192.168.62.31:30490")
before = len(responses)
for _ in range(3):
    sendp(pkt5, iface=iface, verbose=False)
    time.sleep(0.3)
time.sleep(3)
# Count SD Offers received
log(f"    New responses: {len(responses)}")

time.sleep(5)
log(f"\nTotal responses: {len(responses)}")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(buf))
print(f"Written to {OUT}")
