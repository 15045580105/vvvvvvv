#!/usr/bin/env python3
"""Analyze ICC SD Offer packets and test Subscribe strategies."""
import sys, struct, time, threading, subprocess, socket
sys.path.insert(0, r"d:\VCC")

OUT = r"d:\VCC\tools\sd_analyze_result.txt"
buf = []
def log(m=""):
    buf.append(str(m))

from scapy.layers.l2 import Ether, Dot1Q
from scapy.layers.inet import IP, UDP
from scapy.sendrecv import sendp, sniff
from scapy.arch import get_if_list, get_if_addr, get_if_hwaddr

ZERO = b'\x00'

# Find interface
iface = local_ip = local_mac = None
for i in get_if_list():
    try:
        a = get_if_addr(i)
        if a.startswith("192.168.62."):
            iface = i; local_ip = a; local_mac = get_if_hwaddr(i); break
    except: pass

log(f"Interface: {iface}, IP: {local_ip}, MAC: {local_mac}")

# Phase 1: Capture ICC SD Offer packets
captured_offers = []
def capture_offer(pkt):
    try:
        if Dot1Q not in pkt or pkt[Dot1Q].vlan != 62: return
        if IP not in pkt or UDP not in pkt: return
        if pkt[IP].src == local_ip: return
        payload = bytes(pkt[UDP].payload)
        if len(payload) < 16: return
        srv_id = struct.unpack(">H", payload[0:2])[0]
        method = struct.unpack(">H", payload[4:6])[0]
        if srv_id == 0xFFFF and method == 0x8100:
            captured_offers.append({"raw": payload, "src": pkt[IP].src, "sport": pkt[UDP].sport, "dport": pkt[UDP].dport})
    except: pass

log("\n=== Phase 1: Capture ICC SD Offer (5s) ===")
t = threading.Thread(target=lambda: sniff(iface=iface, prn=capture_offer, store=0, timeout=5), daemon=True)
t.start(); time.sleep(6); t.join(timeout=2)

log(f"Captured {len(captured_offers)} SD Offer packets")
for i, off in enumerate(captured_offers[:3]):
    raw = off["raw"]
    log(f"\n--- Offer #{i+1}: {off['src']}:{off['sport']} -> :{off['dport']}, len={len(raw)} ---")
    log(f"  SOME/IP: SrvID=0x{struct.unpack('>H', raw[0:2])[0]:04X} "
        f"MthID=0x{struct.unpack('>H', raw[4:6])[0]:04X} "
        f"CliID=0x{struct.unpack('>H', raw[8:10])[0]:04X} "
        f"SesID=0x{struct.unpack('>H', raw[10:12])[0]:04X} "
        f"Type=0x{raw[14]:02X} Ret=0x{raw[15]:02X}")
    length_val = struct.unpack(">I", ZERO + raw[4:8])[0]
    log(f"  Length: {length_val}")
    sd = raw[16:]
    if len(sd) >= 12:
        log(f"  SD: Flags=0x{sd[0]:02X} Len={struct.unpack('>I', ZERO + sd[4:8])[0]}")
        pos = 12  # 8 (sd header) + 4 (entries length)
        eidx = 0
        while pos + 16 <= len(sd) and eidx < 5:
            etype = sd[pos]
            n_opt1 = (sd[pos+2] >> 4) & 0x0F
            n_opt2 = sd[pos+2] & 0x0F
            svc_id = struct.unpack(">H", sd[pos+4:pos+6])[0]
            inst_id = struct.unpack(">H", sd[pos+6:pos+8])[0]
            major = sd[pos+8]
            ttl = struct.unpack(">I", ZERO + sd[pos+9:pos+12])[0]
            if etype == 0x01:
                minor = struct.unpack(">I", sd[pos+12:pos+16])[0]
                log(f"  Entry[{eidx}]: Offer SvcID=0x{svc_id:04X} Inst=0x{inst_id:04X} Maj={major} Min={minor} TTL={ttl} n_opt1={n_opt1} n_opt2={n_opt2}")
                pos += 16
            elif etype == 0x06:
                eg_id = struct.unpack(">H", sd[pos+14:pos+16])[0]
                log(f"  Entry[{eidx}]: SubAck SvcID=0x{svc_id:04X} Inst=0x{inst_id:04X} TTL={ttl} EG=0x{eg_id:04X}")
                pos += 16
            else:
                log(f"  Entry[{eidx}]: type=0x{etype:02X} SvcID=0x{svc_id:04X}")
                pos += 16
            eidx += 1
        # Options
        if pos + 4 <= len(sd):
            opt_len = struct.unpack(">I", ZERO + sd[pos:pos+4])[0]
            log(f"  Options len: {opt_len}")
            op = pos + 4
            oidx = 0
            while op + 12 <= len(sd) and oidx < 5:
                ot = sd[op]
                if ot == 0x04:
                    addr = ".".join(str(b) for b in sd[op+4:op+8])
                    l4 = sd[op+8]
                    port = struct.unpack(">H", sd[op+10:op+12])[0]
                    pn = {0x06: "TCP", 0x11: "UDP"}.get(l4, f"0x{l4:02X}")
                    log(f"  Option[{oidx}]: IPv4EP {addr}:{port} {pn}")
                    op += 12
                elif ot == 0x06:
                    addr = ".".join(str(b) for b in sd[op+4:op+8])
                    l4 = sd[op+8]
                    port = struct.unpack(">H", sd[op+10:op+12])[0]
                    pn = {0x06: "TCP", 0x11: "UDP"}.get(l4, f"0x{l4:02X}")
                    log(f"  Option[{oidx}]: IPv4SubEP {addr}:{port} {pn}")
                    op += 12
                else:
                    log(f"  Option[{oidx}]: type=0x{ot:02X}")
                    op += 12
                oidx += 1
    # Hex dump
    log(f"  Hex ({len(raw)} bytes):")
    for row in range(0, min(len(raw), 200), 16):
        hx = " ".join(f"{b:02X}" for b in raw[row:row+16])
        log(f"    {row:04X}: {hx}")

# Phase 2: Our Subscribe hex dump
log("\n\n=== Phase 2: Our Subscribe hex ===")
from app.common.communication.clients.someip import SOMEIP, SOMEIP_SD, SDOption_IP4_EndPoint
from scapy.contrib.automotive.someip import SDEntry_EventGroup

option = SDOption_IP4_EndPoint(type=0x04, addr=local_ip, l4_proto=0x11, port=40000)
entry = SDEntry_EventGroup(type=0x06, srv_id=0xA994, inst_id=0xFFFF, major_ver=0xFF, ttl=3, cnt=0, eventgroup_id=0x0001)
entry.index_1 = 0
entry.n_opt_1 = 1
sd = SOMEIP_SD(flags=0x80, entry_array=[entry], option_array=[option])
someip_pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001, session_id=0x0001, msg_type=0x02) / sd
pkt_bytes = bytes(someip_pkt)
log(f"Our Subscribe ({len(pkt_bytes)} bytes):")
for row in range(0, len(pkt_bytes), 16):
    hx = " ".join(f"{b:02X}" for b in pkt_bytes[row:row+16])
    log(f"  {row:04X}: {hx}")

# Phase 3: Resolve target MAC
target_mac = None
subprocess.run(["ping", "-n", "1", "-w", "1000", "192.168.62.31"], capture_output=True, timeout=5)
r = subprocess.run(["arp", "-a", "-N", local_ip], capture_output=True, text=True, timeout=5)
for line in r.stdout.splitlines():
    if "192.168.62.31" in line:
        for p in line.split():
            if len(p) == 17 and p.count("-") == 5:
                target_mac = p.replace("-", ":").lower()
log(f"\nTarget MAC: {target_mac}")

# Phase 4: Subscribe strategies
log("\n=== Phase 3: Subscribe strategies ===")
responses = []
def capture_resp(pkt):
    try:
        if Dot1Q not in pkt or pkt[Dot1Q].vlan != 62: return
        if IP not in pkt or UDP not in pkt: return
        if pkt[IP].src == local_ip: return
        payload = bytes(pkt[UDP].payload)
        if len(payload) < 16: return
        srv_id = struct.unpack(">H", payload[0:2])[0]
        method = struct.unpack(">H", payload[4:6])[0]
        if srv_id == 0xFFFF and method == 0x8100: return
        responses.append(payload)
        log(f"  RESP: srv=0x{srv_id:04X} mth=0x{method:04X} type=0x{payload[14]:02X}")
    except: pass

sniff_thread = threading.Thread(target=lambda: sniff(iface=iface, prn=capture_resp, store=0, timeout=40), daemon=True)
sniff_thread.start()
time.sleep(0.5)

strategies = [
    ("A-mcast", "01:00:5e:00:00:ff", "239.0.0.255", 30490, 30490),
    ("B-ucast-sd", target_mac or "ff:ff:ff:ff:ff:ff", "192.168.62.31", 30490, 30490),
    ("C-ucast-cli", target_mac or "ff:ff:ff:ff:ff:ff", "192.168.62.31", 30501, 30490),
    ("D-ucast-biz", target_mac or "ff:ff:ff:ff:ff:ff", "192.168.62.31", 30501, 30500),
]
for name, dmac, dip, sport, dport in strategies:
    before = len(responses)
    pkt = (
        Ether(src=local_mac, dst=dmac) /
        Dot1Q(vlan=62) /
        IP(src=local_ip, dst=dip) /
        UDP(sport=sport, dport=dport) /
        someip_pkt
    )
    log(f"  [{name}] -> {dip}:{dport} sport={sport} mac={dmac}")
    for _ in range(3):
        sendp(pkt, iface=iface, verbose=False)
        time.sleep(0.3)
    time.sleep(4)
    after = len(responses)
    log(f"    Responses: {after - before}")

# Phase 5: RPC
log("\n=== Phase 4: RPC Request ===")
before = len(responses)
rpc_pkt = SOMEIP(srv_id=0xAC04, sub_id=0x0001, client_id=0x7001, session_id=0x0002, msg_type=0x00, retcode=0x00) / b"\x00"
rpc_vlan = (
    Ether(src=local_mac, dst=target_mac or "ff:ff:ff:ff:ff:ff") /
    Dot1Q(vlan=62) /
    IP(src=local_ip, dst="192.168.62.31") /
    UDP(sport=30501, dport=30500) /
    rpc_pkt
)
log(f"  TX RPC 0xAC04:0x0001 -> 192.168.62.31:30500")
sendp(rpc_vlan, iface=iface, verbose=False)
time.sleep(5)
log(f"  Responses: {len(responses) - before}")

# Phase 6: TCP
log("\n=== Phase 5: TCP ===")
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    s.connect(("192.168.62.31", 30500))
    log(f"  TCP connected!")
    s.send(bytes(someip_pkt))
    time.sleep(3)
    try:
        resp = s.recv(4096)
        log(f"  TCP resp: {len(resp)} bytes hex={resp[:64].hex()}")
    except socket.timeout:
        log(f"  TCP timeout")
    s.close()
except Exception as e:
    log(f"  TCP failed: {e}")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(buf))
print(f"Written to {OUT}")
