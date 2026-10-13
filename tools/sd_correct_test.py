#!/usr/bin/env python3
"""Test Subscribe with CORRECT ICC-matching SD format."""
import sys, struct, time, threading, subprocess
sys.path.insert(0, r"d:\VCC")

OUT = r"d:\VCC\tools\sd_correct_result.txt"
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

target_mac = None
subprocess.run(["ping", "-n", "1", "-w", "1000", "192.168.62.31"], capture_output=True, timeout=5)
r = subprocess.run(["arp", "-a", "-N", local_ip], capture_output=True, text=True, timeout=5)
for line in r.stdout.splitlines():
    if "192.168.62.31" in line:
        for p in line.split():
            if len(p) == 17 and p.count("-") == 5:
                target_mac = p.replace("-", ":").lower()
log(f"Target MAC: {target_mac}")

def build_someip_sd_raw(svc_id, eventgroup_id, client_port, session_id=1):
    """Build SOME/IP SD SubscribeEventGroup matching ICC's exact format.
    
    ICC format:
      SOMEIP header (16 bytes):
        srv_id=0xFFFF, method_id=0x8100, length, client_id, session_id, 
        proto=1, iface=1, msg_type=0x02, retcode=0
      SD payload:
        flags=0xC0, reserved(3), sd_length(4),
        entries_array_length(4), entries...,
        options_array_length(4), options...
    """
    # Build SD Entry (SubscribeEventGroup, 16 bytes)
    entry = bytes([
        0x06,  # type = SubscribeEventGroup
        0x00,  # index_1
        0x10,  # n_opt_1=1, n_opt_2=0
        0x00,  # index_2
        (svc_id >> 8) & 0xFF, svc_id & 0xFF,
        0xFF, 0xFF,  # instance_id
        0x01,  # major version
        0x00, 0x00, 0x03,  # TTL=3
        0x00,  # counter
        0x00,  # reserved
        (eventgroup_id >> 8) & 0xFF, eventgroup_id & 0xFF,
    ])
    
    # Build SD Option (IPv4 Endpoint, 12 bytes)
    ip_bytes = bytes(int(x) for x in local_ip.split("."))
    option = bytes([
        0x00, 0x09,  # length=9
        0x04,        # type=IPv4Endpoint
        0x00,        # reserved
    ]) + ip_bytes + bytes([
        0x00,        # reserved
        0x11,        # L4 proto=UDP
        (client_port >> 8) & 0xFF, client_port & 0xFF,
    ])
    
    # SD payload with ICC format (includes entries_array_length)
    entries_arr_len = struct.pack(">I", len(entry))
    options_arr_len = struct.pack(">I", len(option))
    sd_body = entries_arr_len + entry + options_arr_len + option
    sd_header = bytes([0xC0, 0x00, 0x00, 0x00]) + struct.pack(">I", len(sd_body))
    sd_payload = sd_header + sd_body
    
    # SOMEIP header
    someip_len = len(sd_payload)
    someip = struct.pack(">HH", 0xFFFF, 0x8100)  # srv_id, method_id
    someip += struct.pack(">I", someip_len)         # length
    someip += struct.pack(">H", 0x7001)             # client_id
    someip += struct.pack(">H", session_id)          # session_id
    someip += bytes([0x01, 0x01, 0x02, 0x00])       # proto, iface, type, retcode
    
    return someip + sd_payload

# Build Subscribe for 0xA994
raw_sub = build_someip_sd_raw(0xA994, 0x0001, 30501)
log(f"\nRaw Subscribe (ICC format, {len(raw_sub)} bytes):")
for row in range(0, len(raw_sub), 16):
    hx = " ".join(f"{b:02X}" for b in raw_sub[row:row+16])
    log(f"  {row:04X}: {hx}")

# Compare with ICC Offer format
icc_hex = (
    "FF FF 81 00 00 00 00 5C 00 00 07 11 01 01 02 00"
    "C0 00 00 00 00 00 00 30 01 00 00 20 A9 94 00 01"
    "01 00 00 03 00 00 00 01"
)
icc_raw = bytes.fromhex(icc_hex.replace(" ", ""))
log(f"\nICC Offer header:  {' '.join(f'{b:02X}' for b in icc_raw[:28])}")
log(f"Our Sub header:    {' '.join(f'{b:02X}' for b in raw_sub[:28])}")

# Verify SD structure matches
log(f"\nICC SD[0:12]: {' '.join(f'{b:02X}' for b in icc_raw[16:28])}")
log(f"Our SD[0:12]:  {' '.join(f'{b:02X}' for b in raw_sub[16:28])}")

# Test
log(f"\n=== Subscribe test ===")
responses = []
offer_count = [0]
def cap(pkt):
    try:
        if Dot1Q not in pkt or pkt[Dot1Q].vlan != 62: return
        if IP not in pkt or UDP not in pkt: return
        if pkt[IP].src == local_ip: return
        p = bytes(pkt[UDP].payload)
        if len(p) < 16: return
        srv = struct.unpack(">H", p[0:2])[0]
        mid = struct.unpack(">H", p[2:4])[0]
        if srv == 0xFFFF and mid == 0x8100:
            offer_count[0] += 1
            return
        responses.append(p)
        log(f"  RESP: {p[:32].hex()}")
    except: pass

sniff_t = threading.Thread(target=lambda: sniff(iface=iface, prn=cap, store=0, timeout=40), daemon=True)
sniff_t.start()
time.sleep(0.5)

# First: passive listen for ICC Offers
log(f"  Passive listen (3s)...")
time.sleep(3)
log(f"  Offers: {offer_count[0]}")

# Strategy 1: Raw Subscribe -> multicast
before_r = len(responses)
before_o = offer_count[0]
pkt1 = (
    Ether(src=local_mac, dst="01:00:5e:00:00:ff") /
    Dot1Q(vlan=62) /
    IP(src=local_ip, dst="239.0.0.255") /
    UDP(sport=30490, dport=30490) /
    raw_sub
)
log(f"  [1] Raw Sub -> mcast 239.0.0.255:30490")
for _ in range(5):
    sendp(pkt1, iface=iface, verbose=False)
    time.sleep(0.3)
time.sleep(5)
log(f"    Offers: {offer_count[0]-before_o}, Responses: {len(responses)-before_r}")

# Strategy 2: Raw Subscribe -> unicast to SD port
before_r = len(responses)
before_o = offer_count[0]
pkt2 = (
    Ether(src=local_mac, dst=target_mac or "ff:ff:ff:ff:ff:ff") /
    Dot1Q(vlan=62) /
    IP(src=local_ip, dst="192.168.62.31") /
    UDP(sport=30490, dport=30490) /
    raw_sub
)
log(f"  [2] Raw Sub -> unicast 192.168.62.31:30490")
for _ in range(5):
    sendp(pkt2, iface=iface, verbose=False)
    time.sleep(0.3)
time.sleep(5)
log(f"    Offers: {offer_count[0]-before_o}, Responses: {len(responses)-before_r}")

# Strategy 3: Raw Subscribe -> unicast to business port
before_r = len(responses)
before_o = offer_count[0]
pkt3 = (
    Ether(src=local_mac, dst=target_mac or "ff:ff:ff:ff:ff:ff") /
    Dot1Q(vlan=62) /
    IP(src=local_ip, dst="192.168.62.31") /
    UDP(sport=30501, dport=30500) /
    raw_sub
)
log(f"  [3] Raw Sub -> unicast 192.168.62.31:30500")
for _ in range(5):
    sendp(pkt3, iface=iface, verbose=False)
    time.sleep(0.3)
time.sleep(5)
log(f"    Offers: {offer_count[0]-before_o}, Responses: {len(responses)-before_r}")

# Strategy 4: Raw FindService -> unicast
before_o = offer_count[0]
find_entry = bytes([
    0x00, 0x00, 0x00, 0x00,  # type=0 (FindService), idx/nopt=0
    0xFF, 0xFF, 0xFF, 0xFF,  # svc_id=0xFFFF, inst_id=0xFFFF
    0xFF, 0x00, 0x00, 0x03,  # major=0xFF, TTL=3
])
find_sd_body = struct.pack(">I", len(find_entry)) + find_entry
find_sd = bytes([0xC0, 0x00, 0x00, 0x00]) + struct.pack(">I", len(find_sd_body)) + find_sd_body
find_someip = struct.pack(">HH", 0xFFFF, 0x8100) + struct.pack(">I", len(find_sd))
find_someip += struct.pack(">H", 0x7001) + struct.pack(">H", 0x0099)
find_someip += bytes([0x01, 0x01, 0x02, 0x00])
find_raw = find_someip + find_sd

pkt4 = (
    Ether(src=local_mac, dst=target_mac or "ff:ff:ff:ff:ff:ff") /
    Dot1Q(vlan=62) /
    IP(src=local_ip, dst="192.168.62.31") /
    UDP(sport=30490, dport=30490) /
    find_raw
)
log(f"  [4] Raw FindService -> unicast 192.168.62.31:30490")
for _ in range(3):
    sendp(pkt4, iface=iface, verbose=False)
    time.sleep(0.3)
time.sleep(5)
log(f"    Offers after Find: {offer_count[0]-before_o}")

log(f"\nTotal: Offers={offer_count[0]}, Responses={len(responses)}")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(buf))
print(f"Written to {OUT}")
