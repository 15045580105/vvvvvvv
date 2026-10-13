#!/usr/bin/env python3
"""Capture ICC SD Offer raw hex and compare with our Subscribe packet."""
import sys, struct, time, threading
sys.path.insert(0, r"d:\VCC")

OUT = r"d:\VCC\tools\sd_compare_result.txt"
buf = []
def log(m=""):
    buf.append(str(m))

from scapy.layers.l2 import Ether, Dot1Q
from scapy.layers.inet import IP, UDP
from scapy.sendrecv import sendp, sniff
from scapy.arch import get_if_list, get_if_addr, get_if_hwaddr

ZERO = b'\x00'

iface = local_ip = local_mac = None
for i in get_if_list():
    try:
        a = get_if_addr(i)
        if a.startswith("192.168.62."):
            iface = i; local_ip = a; local_mac = get_if_hwaddr(i); break
    except: pass

log(f"Local: {local_ip} MAC: {local_mac} iface: {iface}")

# === Phase 1: Capture ICC SD Offer ===
captured = []
def cap(pkt):
    try:
        if Dot1Q not in pkt or pkt[Dot1Q].vlan != 62: return
        if IP not in pkt or UDP not in pkt: return
        if pkt[IP].src == local_ip: return
        p = bytes(pkt[UDP].payload)
        if len(p) >= 16:
            captured.append({"raw": p, "src": pkt[IP].src, "sp": pkt[UDP].sport, "dp": pkt[UDP].dport})
    except: pass

log("\n=== Capture ICC packets (8s) ===")
sniff(iface=iface, prn=cap, store=0, timeout=8)
log(f"Captured {len(captured)} packets from ICC")

for i, c in enumerate(captured[:5]):
    r = c["raw"]
    log(f"\n--- ICC Packet #{i+1}: {c['src']}:{c['sp']}->{c['dp']} len={len(r)} ---")
    if len(r) < 16:
        log(f"  Too short to parse")
        continue
    # Parse SOMEIP header (standard format)
    srv = struct.unpack(">H", r[0:2])[0]
    mid = struct.unpack(">H", r[2:4])[0]
    length = struct.unpack(">I", r[4:8])[0]
    cid = struct.unpack(">H", r[8:10])[0]
    sid = struct.unpack(">H", r[10:12])[0]
    proto_ver = r[12]
    iface_ver = r[13]
    msg_type = r[14]
    ret_code = r[15]
    log(f"  [Standard SOMEIP]")
    log(f"    srv_id=0x{srv:04X} method_id=0x{mid:04X}")
    log(f"    length={length} client_id=0x{cid:04X} session_id=0x{sid:04X}")
    log(f"    proto={proto_ver} iface={iface_ver} type=0x{msg_type:02X} ret=0x{ret_code:02X}")
    
    if srv == 0xFFFF and mid == 0x8100:
        log(f"  >>> THIS IS A SD PACKET <<<")
        sd = r[16:]
        if len(sd) >= 8:
            flags = sd[0]
            sd_len = struct.unpack(">I", sd[4:8])[0]
            log(f"  SD: flags=0x{flags:02X} (reboot={bool(flags&0x80)}) sd_length={sd_len}")
            # Entries
            if len(sd) >= 12:
                ent_len = struct.unpack(">I", sd[8:12])[0]
                log(f"  Entries array len: {ent_len}")
                pos = 12
                eidx = 0
                while pos + 16 <= len(sd) and eidx < 8:
                    et = sd[pos]
                    i1 = sd[pos+1]
                    no1 = (sd[pos+2] >> 4) & 0x0F
                    no2 = sd[pos+2] & 0x0F
                    sv = struct.unpack(">H", sd[pos+4:pos+6])[0]
                    inst = struct.unpack(">H", sd[pos+6:pos+8])[0]
                    mj = sd[pos+8]
                    ttl = struct.unpack(">I", ZERO + sd[pos+9:pos+12])[0]
                    if et == 0x01:
                        mn = struct.unpack(">I", sd[pos+12:pos+16])[0]
                        log(f"  E[{eidx}] Offer: type=0x{et:02X} svc=0x{sv:04X} inst=0x{inst:04X} maj={mj} min={mn} ttl={ttl} nopt1={no1} nopt2={no2}")
                        pos += 16
                    elif et == 0x06:
                        eg = struct.unpack(">H", sd[pos+14:pos+16])[0]
                        log(f"  E[{eidx}] SubAck: type=0x{et:02X} svc=0x{sv:04X} inst=0x{inst:04X} ttl={ttl} eg=0x{eg:04X}")
                        pos += 16
                    else:
                        log(f"  E[{eidx}] type=0x{et:02X} svc=0x{sv:04X}")
                        pos += 16
                    eidx += 1
                # Options
                if pos + 4 <= len(sd):
                    ol = struct.unpack(">I", sd[pos:pos+4])[0]
                    log(f"  Options array len: {ol}")
                    op = pos + 4
                    oidx = 0
                    while op + 12 <= len(sd) and oidx < 8:
                        ot = sd[op]
                        if ot in (0x04, 0x06):
                            addr = ".".join(str(b) for b in sd[op+4:op+8])
                            l4 = sd[op+8]
                            pt = struct.unpack(">H", sd[op+10:op+12])[0]
                            pn = {0x06:"TCP",0x11:"UDP"}.get(l4,f"0x{l4:02X}")
                            tn = "SubEP" if ot == 0x06 else "EP"
                            log(f"  O[{oidx}] {tn}: {addr}:{pt} {pn}")
                            op += 12
                        else:
                            log(f"  O[{oidx}] type=0x{ot:02X}")
                            op += 12
                        oidx += 1
    # Hex dump
    log(f"  Raw hex ({len(r)} bytes):")
    for row in range(0, min(len(r), 256), 16):
        hx = " ".join(f"{b:02X}" for b in r[row:row+16])
        log(f"    {row:04X}: {hx}")

# === Phase 2: Build our Subscribe and compare ===
log("\n\n=== Our Subscribe packet ===")
from app.common.communication.clients.someip import SOMEIP, SOMEIP_SD, SDOption_IP4_EndPoint
from scapy.contrib.automotive.someip import SDEntry_EventGroup

# Check SOMEIP field structure
test_pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001, session_id=0x0001, msg_type=0x02)
test_bytes = bytes(test_pkt)
log(f"SOMEIP header only ({len(test_bytes)} bytes):")
for row in range(0, len(test_bytes), 16):
    hx = " ".join(f"{b:02X}" for b in test_bytes[row:row+16])
    log(f"  {row:04X}: {hx}")

# Check what Scapy thinks the fields are
log(f"\nSOMEIP field values:")
log(f"  srv_id = 0x{test_pkt.srv_id:04X}")
log(f"  sub_id = 0x{test_pkt.sub_id:04X}")
log(f"  method_id = 0x{getattr(test_pkt, 'method_id', 'N/A'):04X}" if hasattr(test_pkt, 'method_id') else "  method_id = N/A")
log(f"  client_id = 0x{test_pkt.client_id:04X}")
log(f"  session_id = 0x{test_pkt.session_id:04X}")
log(f"  msg_type = 0x{test_pkt.msg_type:02X}")

# Show SOMEIP fields definition
log(f"\nSOMEIP fields definition:")
for f in test_pkt.fields_desc:
    log(f"  {f.name}: {f.__class__.__name__} size={getattr(f, 'size', '?')}")

# Build full Subscribe
option = SDOption_IP4_EndPoint(type=0x04, addr=local_ip, l4_proto=0x11, port=40000)
entry = SDEntry_EventGroup(type=0x06, srv_id=0xA994, inst_id=0xFFFF, major_ver=0xFF, ttl=3, cnt=0, eventgroup_id=0x0001)
entry.index_1 = 0
entry.n_opt_1 = 1
sd = SOMEIP_SD(flags=0x80, entry_array=[entry], option_array=[option])
full_pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001, session_id=0x0001, msg_type=0x02) / sd
full_bytes = bytes(full_pkt)
log(f"\nFull Subscribe ({len(full_bytes)} bytes):")
for row in range(0, len(full_bytes), 16):
    hx = " ".join(f"{b:02X}" for b in full_bytes[row:row+16])
    log(f"  {row:04X}: {hx}")

# === Phase 3: Compare ===
log("\n\n=== COMPARISON ===")
if captured:
    icc_raw = captured[0]["raw"]
    icc_someip = icc_raw[:16]
    our_someip = full_bytes[:16]
    log(f"ICC SOMEIP header:  {' '.join(f'{b:02X}' for b in icc_someip)}")
    log(f"Our SOMEIP header:  {' '.join(f'{b:02X}' for b in our_someip)}")
    log(f"\nByte-by-byte diff:")
    for i in range(16):
        ic = icc_someip[i] if i < len(icc_someip) else 0
        ou = our_someip[i] if i < len(our_someip) else 0
        mark = " <<<" if ic != ou else ""
        log(f"  Byte {i:2d}: ICC=0x{ic:02X} Our=0x{ou:02X}{mark}")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(buf))
print(f"Written to {OUT}")
