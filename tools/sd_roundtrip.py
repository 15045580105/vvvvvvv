#!/usr/bin/env python3
"""Round-trip test: capture ICC Offer, modify to Subscribe, verify format, and test."""
import sys, struct, time, threading, subprocess
sys.path.insert(0, r"d:\VCC")

OUT = r"d:\VCC\tools\sd_roundtrip_result.txt"
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

# Capture ICC Offer
from scapy.contrib.automotive.someip import SOMEIP as ScapySOMEIP
captured = []
def cap(pkt):
    try:
        if Dot1Q not in pkt or pkt[Dot1Q].vlan != 62: return
        if IP not in pkt or UDP not in pkt: return
        if pkt[IP].src == local_ip: return
        p = bytes(pkt[UDP].payload)
        if len(p) >= 16:
            srv = struct.unpack(">H", p[0:2])[0]
            mid = struct.unpack(">H", p[2:4])[0]
            if srv == 0xFFFF and mid == 0x8100:
                captured.append((pkt, p))
    except: pass

log("Capturing ICC SD (8s)...")
sniff(iface=iface, prn=cap, store=0, timeout=8)
log(f"Captured {len(captured)} SD packets")
if not captured:
    log("No SD captured!")
    sys.exit(1)

# Parse ICC Offer
icc_raw = captured[0][1]
icc_someip = ScapySOMEIP(icc_raw)
icc_sd = icc_someip.payload

log(f"\n=== ICC Offer Analysis ===")
log(f"  Raw length: {len(icc_raw)}")
log(f"  SD flags: {icc_sd.flags}")
log(f"  SD len_entry_array: {icc_sd.len_entry_array}")
log(f"  Entries: {len(icc_sd.entry_array)}")
for e in icc_sd.entry_array:
    log(f"    type=0x{e.type:02X} svc=0x{e.srv_id:04X} inst=0x{e.inst_id:04X} major={e.major_ver} ttl={e.ttl}")
log(f"  Options: {len(icc_sd.option_array)}")
for o in icc_sd.option_array:
    log(f"    type=0x{o.type:02X} addr={o.addr} port={o.port} l4=0x{o.l4_proto:02X}")

# Check: does ICC Offer have len_option_array?
log(f"  hasattr len_option_array: {hasattr(icc_sd, 'len_option_array')}")
if hasattr(icc_sd, 'len_option_array'):
    log(f"  SD len_option_array: {icc_sd.len_option_array}")

# Now: take ICC Offer and convert to SubscribeEventGroup
log(f"\n=== Convert ICC Offer -> Subscribe ===")
from app.common.communication.clients.someip import SOMEIP, SOMEIP_SD, SDOption_IP4_EndPoint
from scapy.contrib.automotive.someip import SDEntry_EventGroup

# Build Subscribe entry matching ICC's Offer parameters
svc_id = icc_sd.entry_array[0].srv_id  # 0xA994
inst_id = icc_sd.entry_array[0].inst_id  # 0x0001
major_ver = icc_sd.entry_array[0].major_ver  # 0x01

# SubscribeEventGroup entry
sub_entry = SDEntry_EventGroup(
    type=0x06,       # SubscribeEventGroup
    srv_id=svc_id,
    inst_id=inst_id,
    major_ver=major_ver,
    ttl=0xFF,        # Subscribe TTL
    cnt=0,
    eventgroup_id=0x0001,
)
sub_entry.index_1 = 0
sub_entry.n_opt_1 = 1

# Client endpoint option
client_option = SDOption_IP4_EndPoint(type=0x04, addr=local_ip, l4_proto=0x11, port=30501)

# Build SD
sub_sd = SOMEIP_SD(flags=0xC0, entry_array=[sub_entry], option_array=[client_option])
sub_someip = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001, session_id=0x0001, msg_type=0x02) / sub_sd
sub_bytes = bytes(sub_someip)

log(f"Subscribe ({len(sub_bytes)} bytes):")
for row in range(0, len(sub_bytes), 16):
    hx = " ".join(f"{b:02X}" for b in sub_bytes[row:row+16])
    log(f"  {row:04X}: {hx}")

# Parse our Subscribe back with Scapy to verify
our_someip = ScapySOMEIP(sub_bytes)
our_sd = our_someip.payload
log(f"\nOur Subscribe parsed back:")
log(f"  SD flags: {our_sd.flags}")
log(f"  SD len_entry_array: {our_sd.len_entry_array}")
log(f"  Entries: {len(our_sd.entry_array)}")
for e in our_sd.entry_array:
    log(f"    type=0x{e.type:02X} srv=0x{e.srv_id:04X} inst=0x{e.inst_id:04X} major={e.major_ver} ttl={e.ttl}")
    if hasattr(e, 'eventgroup_id'):
        log(f"    eventgroup_id=0x{e.eventgroup_id:04X}")
log(f"  Options: {len(our_sd.option_array)}")
for o in our_sd.option_array:
    log(f"    type=0x{o.type:02X} addr={o.addr} port={o.port} l4=0x{o.l4_proto:02X}")

# Byte-by-byte comparison of SD portions
log(f"\n=== SD Byte Comparison ===")
icc_sd_bytes = icc_raw[16:]  # SD payload from ICC
our_sd_bytes = sub_bytes[16:]  # SD payload from us

log(f"ICC SD ({len(icc_sd_bytes)} bytes):")
for row in range(0, min(len(icc_sd_bytes), 32), 16):
    hx = " ".join(f"{b:02X}" for b in icc_sd_bytes[row:row+16])
    log(f"  {row:04X}: {hx}")

log(f"Our SD ({len(our_sd_bytes)} bytes):")
for row in range(0, min(len(our_sd_bytes), 32), 16):
    hx = " ".join(f"{b:02X}" for b in our_sd_bytes[row:row+16])
    log(f"  {row:04X}: {hx}")

# Compare field by field
log(f"\nField comparison:")
log(f"  ICC  flags: 0x{icc_sd_bytes[0]:02X}  Our: 0x{our_sd_bytes[0]:02X}")
log(f"  ICC  sd_len: {struct.unpack('>I', icc_sd_bytes[4:8])[0]}  Our: {struct.unpack('>I', our_sd_bytes[4:8])[0]}")
log(f"  ICC  [8:12]: {' '.join(f'{b:02X}' for b in icc_sd_bytes[8:12])}  Our: {' '.join(f'{b:02X}' for b in our_sd_bytes[8:12])}")
log(f"  ICC  entry[0] type: 0x{icc_sd_bytes[8]:02X}  Our: 0x{our_sd_bytes[8]:02X}")

# Now: verify our outgoing packets actually go out with VLAN tag
log(f"\n=== Verify outgoing VLAN tag ===")
outgoing = []
def cap_outgoing(pkt):
    try:
        if Dot1Q in pkt and pkt[Dot1Q].vlan == 62:
            if IP in pkt and pkt[IP].src == local_ip:
                outgoing.append(bytes(pkt))
    except: pass

# Start capture for outgoing
sniff_t = threading.Thread(target=lambda: sniff(iface=iface, prn=cap_outgoing, store=0, timeout=15), daemon=True)
sniff_t.start()
time.sleep(0.5)

# Send test packet
test_pkt = (
    Ether(src=local_mac, dst=target_mac or "ff:ff:ff:ff:ff:ff") /
    Dot1Q(vlan=62) /
    IP(src=local_ip, dst="192.168.62.31") /
    UDP(sport=30490, dport=30490) /
    sub_bytes
)
sendp(test_pkt, iface=iface, verbose=False)
time.sleep(2)

log(f"Outgoing packets captured: {len(outgoing)}")
for i, pkt in enumerate(outgoing[:3]):
    log(f"  Outgoing[{i}] ({len(pkt)} bytes):")
    for row in range(0, min(len(pkt), 64), 16):
        hx = " ".join(f"{b:02X}" for b in pkt[row:row+16])
        log(f"    {row:04X}: {hx}")

# Main test: Subscribe with all services ICC offers
log(f"\n=== Main Subscribe Test ===")
responses = []
offer_cnt = [0]
ack_cnt = [0]

def cap_all(pkt):
    try:
        if Dot1Q not in pkt or pkt[Dot1Q].vlan != 62: return
        if IP not in pkt or pkt[IP].src == local_ip: return
        if UDP in pkt:
            p = bytes(pkt[UDP].payload)
            if len(p) < 16: return
            srv = struct.unpack(">H", p[0:2])[0]
            mid = struct.unpack(">H", p[2:4])[0]
            if srv == 0xFFFF and mid == 0x8100:
                try:
                    sd_p = ScapySOMEIP(p).payload
                    for e in sd_p.entry_array:
                        if e.type == 0x01:
                            offer_cnt[0] += 1
                        elif e.type in (0x06, 0x07):
                            ack_cnt[0] += 1
                            log(f"  ACK! type=0x{e.type:02X} svc=0x{e.srv_id:04X}")
                except:
                    pass
            else:
                responses.append(p)
                log(f"  Non-SD: srv=0x{srv:04X} mid=0x{mid:04X} {p[:16].hex()}")
        if TCP in pkt:
            p = bytes(pkt[TCP].payload)
            if len(p) > 0:
                responses.append(p)
                log(f"  TCP data: {p[:16].hex()}")
    except: pass

sniff_t2 = threading.Thread(target=lambda: sniff(iface=iface, prn=cap_all, store=0, timeout=45), daemon=True)
sniff_t2.start()
time.sleep(0.5)

# Subscribe to ALL 3 offered services
for entry_info in icc_sd.entry_array:
    svc = entry_info.srv_id
    inst = entry_info.inst_id
    maj = entry_info.major_ver
    
    e = SDEntry_EventGroup(type=0x06, srv_id=svc, inst_id=inst, major_ver=maj, ttl=0xFF, cnt=0, eventgroup_id=0x0001)
    e.index_1 = 0
    e.n_opt_1 = 1
    o = SDOption_IP4_EndPoint(type=0x04, addr=local_ip, l4_proto=0x11, port=30501)
    sd = SOMEIP_SD(flags=0xC0, entry_array=[e], option_array=[o])
    sm = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001, session_id=0x0001, msg_type=0x02) / sd
    b = bytes(sm)
    
    pkt = (
        Ether(src=local_mac, dst=target_mac or "ff:ff:ff:ff:ff:ff") /
        Dot1Q(vlan=62) /
        IP(src=local_ip, dst="192.168.62.31") /
        UDP(sport=30490, dport=30490) / b
    )
    log(f"  Subscribe svc=0x{svc:04X} inst=0x{inst:04X} major={maj} -> unicast 192.168.62.31:30490")
    for _ in range(3):
        sendp(pkt, iface=iface, verbose=False)
        time.sleep(0.3)

time.sleep(5)

# Also try multicast
for entry_info in icc_sd.entry_array:
    svc = entry_info.srv_id
    inst = entry_info.inst_id
    maj = entry_info.major_ver
    
    e = SDEntry_EventGroup(type=0x06, srv_id=svc, inst_id=inst, major_ver=maj, ttl=0xFF, cnt=0, eventgroup_id=0x0001)
    e.index_1 = 0
    e.n_opt_1 = 1
    o = SDOption_IP4_EndPoint(type=0x04, addr=local_ip, l4_proto=0x11, port=30501)
    sd = SOMEIP_SD(flags=0xC0, entry_array=[e], option_array=[o])
    sm = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001, session_id=0x0002, msg_type=0x02) / sd
    b = bytes(sm)
    
    pkt = (
        Ether(src=local_mac, dst="01:00:5e:00:00:ff") /
        Dot1Q(vlan=62) /
        IP(src=local_ip, dst="239.0.0.255") /
        UDP(sport=30490, dport=30490) / b
    )
    log(f"  Subscribe svc=0x{svc:04X} -> mcast 239.0.0.255:30490")
    for _ in range(3):
        sendp(pkt, iface=iface, verbose=False)
        time.sleep(0.3)

time.sleep(8)

log(f"\n=== Final Results ===")
log(f"Offers received: {offer_cnt[0]}")
log(f"SubscribeAcks: {ack_cnt[0]}")
log(f"Other responses: {len(responses)}")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(buf))
print(f"\nWritten to {OUT}")
