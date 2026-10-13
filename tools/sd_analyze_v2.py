#!/usr/bin/env python3
"""Capture ICC SD Offer, parse with Scapy, compare with our Subscribe byte-by-byte."""
import sys, struct, time, threading
sys.path.insert(0, r"d:\VCC")

from scapy.layers.l2 import Ether, Dot1Q
from scapy.layers.inet import IP, UDP
from scapy.sendrecv import sniff
from scapy.arch import get_if_list, get_if_addr, get_if_hwaddr

iface = local_ip = local_mac = None
for i in get_if_list():
    try:
        a = get_if_addr(i)
        if a.startswith("192.168.62."):
            iface = i; local_ip = a; local_mac = get_if_hwaddr(i); break
    except: pass
print(f"Local: {local_ip} MAC: {local_mac} iface: {iface}")

# Capture ICC SD Offer
captured = []
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
            captured.append((pkt, p))
    except: pass

print("Listening for ICC SD Offer (10s)...")
sniff(iface=iface, prn=cap, store=0, timeout=10)
print(f"Captured {len(captured)} SD packets")

if not captured:
    print("No SD packets captured!")
    sys.exit(1)

# Use first captured packet
pkt, raw = captured[0]
print(f"\n=== ICC SD Offer Raw ({len(raw)} bytes) ===")
for row in range(0, len(raw), 16):
    hx = " ".join(f"{b:02X}" for b in raw[row:row+16])
    print(f"  {row:04X}: {hx}")

# Parse SOMEIP header
print(f"\n=== SOMEIP Header ===")
print(f"  Service ID:    0x{struct.unpack('>H', raw[0:2])[0]:04X}")
print(f"  Method ID:     0x{struct.unpack('>H', raw[2:4])[0]:04X}")
print(f"  Length:        {struct.unpack('>I', raw[4:8])[0]}")
print(f"  Client ID:     0x{struct.unpack('>H', raw[8:10])[0]:04X}")
print(f"  Session ID:    0x{struct.unpack('>H', raw[10:12])[0]:04X}")
print(f"  Proto:         {raw[12]}")
print(f"  Interface:     {raw[13]}")
print(f"  Msg Type:      0x{raw[14]:02X}")
print(f"  Return Code:   0x{raw[15]:02X}")

# Parse SD
sd = raw[16:]
print(f"\n=== SD Payload ({len(sd)} bytes) ===")
print(f"  Flags:         0x{sd[0]:02X}")
print(f"  Reserved:      {sd[1]:02X} {sd[2]:02X} {sd[3]:02X}")
sd_len = struct.unpack(">I", sd[4:8])[0]
print(f"  SD Length:     {sd_len}")
print(f"  SD[8:12]:      {' '.join(f'{b:02X}' for b in sd[8:12])}")
print(f"  SD[8:12] as u32: {struct.unpack('>I', sd[8:12])[0]}")

# Try to parse with Scapy
print(f"\n=== Scapy Parse ===")
try:
    from scapy.contrib.automotive.someip import SOMEIP as ScapySOMEIP
    scapy_pkt = ScapySOMEIP(raw)
    scapy_pkt.show()
    
    # Get SD layer
    if hasattr(scapy_pkt, 'payload'):
        sd_layer = scapy_pkt.payload
        print(f"\n  SD layer: {sd_layer}")
        if hasattr(sd_layer, 'entry_array'):
            print(f"  Entries: {len(sd_layer.entry_array)}")
            for i, e in enumerate(sd_layer.entry_array):
                print(f"    Entry[{i}]: type=0x{e.type:02X} srv_id=0x{e.srv_id:04X} inst_id=0x{e.inst_id:04X}")
                if hasattr(e, 'eventgroup_id'):
                    print(f"      eventgroup_id=0x{e.eventgroup_id:04X}")
        if hasattr(sd_layer, 'option_array'):
            print(f"  Options: {len(sd_layer.option_array)}")
            for i, o in enumerate(sd_layer.option_array):
                print(f"    Option[{i}]: type=0x{o.type:02X}")
                if hasattr(o, 'addr'):
                    print(f"      addr={o.addr} port={o.port} l4_proto=0x{o.l4_proto:02X}")
except Exception as ex:
    print(f"  Scapy parse error: {ex}")

# Manual parse - try both with and without entries_array_length
print(f"\n=== Manual Parse (NO entries_array_length) ===")
pos = 8  # after flags+reserved+sd_length
entry_count = 0
while pos < 8 + sd_len and pos + 16 <= len(sd):
    etype = sd[pos]
    if etype not in (0x00, 0x01, 0x06, 0x07):
        print(f"  Unknown entry type 0x{etype:02X} at offset {pos}, stopping")
        break
    type_names = {0x00: "FindService", 0x01: "OfferService(v1)", 0x06: "SubscribeEventGroup", 0x07: "OfferService"}
    svc_id = struct.unpack(">H", sd[pos+4:pos+6])[0]
    inst_id = struct.unpack(">H", sd[pos+6:pos+8])[0]
    major = sd[pos+8]
    ttl = struct.unpack(">I", b'\x00' + sd[pos+9:pos+12])[0]
    print(f"  Entry[{entry_count}] @ {pos}: type=0x{etype:02X}({type_names.get(etype,'?')}) svc=0x{svc_id:04X} inst=0x{inst_id:04X} major={major} ttl={ttl}")
    if etype == 0x06:
        eg_id = struct.unpack(">H", sd[pos+14:pos+16])[0]
        print(f"    eventgroup_id=0x{eg_id:04X}")
    pos += 16
    entry_count += 1

# Parse options
print(f"  Options start @ {pos}")
opt_count = 0
while pos + 4 <= len(sd):
    opt_len = struct.unpack(">H", sd[pos:pos+2])[0]
    opt_type = sd[pos+2]
    if opt_type not in (0x04, 0x06, 0x09, 0x12):
        print(f"  Unknown option type 0x{opt_type:02X} at offset {pos}, stopping")
        break
    opt_data = sd[pos+4:pos+2+opt_len]
    if opt_type == 0x04 and len(opt_data) >= 7:  # IPv4 endpoint
        ip_addr = ".".join(str(b) for b in opt_data[1:5])
        l4_proto = opt_data[5]
        port = struct.unpack(">H", opt_data[6:8])[0]
        print(f"  Option[{opt_count}] @ {pos}: type=0x{opt_type:02X}(IPv4Endpoint) len={opt_len} ip={ip_addr} proto={'UDP' if l4_proto==0x11 else 'TCP'} port={port}")
    else:
        print(f"  Option[{opt_count}] @ {pos}: type=0x{opt_type:02X} len={opt_len}")
    pos += 2 + opt_len
    opt_count += 1

print(f"\n=== Manual Parse (WITH entries_array_length) ===")
eal = struct.unpack(">I", sd[8:12])[0]
print(f"  entries_array_length = {eal}")
pos = 12
entry_count = 0
end_pos = 8 + sd_len
while pos < min(12 + eal, end_pos) and pos + 16 <= len(sd):
    etype = sd[pos]
    if etype not in (0x00, 0x01, 0x06, 0x07):
        print(f"  Unknown entry type 0x{etype:02X} at offset {pos}, stopping")
        break
    type_names = {0x00: "FindService", 0x01: "OfferService(v1)", 0x06: "SubscribeEventGroup", 0x07: "OfferService"}
    svc_id = struct.unpack(">H", sd[pos+4:pos+6])[0]
    inst_id = struct.unpack(">H", sd[pos+6:pos+8])[0]
    major = sd[pos+8]
    ttl = struct.unpack(">I", b'\x00' + sd[pos+9:pos+12])[0]
    print(f"  Entry[{entry_count}] @ {pos}: type=0x{etype:02X}({type_names.get(etype,'?')}) svc=0x{svc_id:04X} inst=0x{inst_id:04X} major={major} ttl={ttl}")
    if etype == 0x06:
        eg_id = struct.unpack(">H", sd[pos+14:pos+16])[0]
        print(f"    eventgroup_id=0x{eg_id:04X}")
    pos += 16
    entry_count += 1

# After entries, check for options_array_length
if pos + 4 <= len(sd):
    oal = struct.unpack(">I", sd[pos:pos+4])[0]
    print(f"  options_array_length @ {pos} = {oal}")
    pos += 4
    opt_count = 0
    while pos + 4 <= len(sd):
        opt_len = struct.unpack(">H", sd[pos:pos+2])[0]
        opt_type = sd[pos+2]
        if opt_type not in (0x04, 0x06, 0x09, 0x12):
            print(f"  Unknown option type 0x{opt_type:02X} at offset {pos}")
            break
        opt_data = sd[pos+4:pos+2+opt_len]
        if opt_type == 0x04 and len(opt_data) >= 7:
            ip_addr = ".".join(str(b) for b in opt_data[1:5])
            l4_proto = opt_data[5]
            port = struct.unpack(">H", opt_data[6:8])[0]
            print(f"  Option[{opt_count}] @ {pos}: type=0x{opt_type:02X}(IPv4Endpoint) len={opt_len} ip={ip_addr} proto={'UDP' if l4_proto==0x11 else 'TCP'} port={port}")
        else:
            print(f"  Option[{opt_count}] @ {pos}: type=0x{opt_type:02X} len={opt_len}")
        pos += 2 + opt_len
        opt_count += 1

# Now build our Subscribe and compare
print(f"\n=== Build Our Subscribe ===")
from scapy.contrib.automotive.someip import SDEntry_EventGroup
sys.path.insert(0, r"d:\VCC")
from app.common.communication.clients.someip import SOMEIP, SOMEIP_SD, SDOption_IP4_EndPoint

option = SDOption_IP4_EndPoint(type=0x04, addr=local_ip, l4_proto=0x11, port=30501)
entry = SDEntry_EventGroup(type=0x06, srv_id=0xA994, inst_id=0xFFFF, major_ver=0xFF, ttl=3, cnt=0, eventgroup_id=0x0001)
entry.index_1 = 0
entry.n_opt_1 = 1
sd_pkt = SOMEIP_SD(flags=0xC0, entry_array=[entry], option_array=[option])
someip_pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001, session_id=0x0001, msg_type=0x02) / sd_pkt
our_bytes = bytes(someip_pkt)

print(f"Our Subscribe ({len(our_bytes)} bytes):")
for row in range(0, len(our_bytes), 16):
    hx = " ".join(f"{b:02X}" for b in our_bytes[row:row+16])
    print(f"  {row:04X}: {hx}")

# Also build raw version matching ICC format
print(f"\n=== Build Raw Subscribe (ICC format) ===")
# SD Entry
sub_entry = bytes([
    0x06, 0x00, 0x10, 0x00,
    0xA9, 0x94, 0xFF, 0xFF,
    0x01, 0x00, 0x00, 0x03,
    0x00, 0x00, 0x00, 0x01,
])
# SD Option
ip_bytes = bytes(int(x) for x in local_ip.split("."))
sub_option = bytes([0x00, 0x09, 0x04, 0x00]) + ip_bytes + bytes([0x00, 0x11, 0x77, 0x25])

# Format 1: NO entries_array_length (standard SOME/IP SD)
sd_body_1 = sub_entry + sub_option
sd_header_1 = bytes([0xC0, 0x00, 0x00, 0x00]) + struct.pack(">I", len(sd_body_1))
sd_payload_1 = sd_header_1 + sd_body_1
someip_1 = struct.pack(">HH", 0xFFFF, 0x8100) + struct.pack(">I", len(sd_payload_1))
someip_1 += struct.pack(">H", 0x7001) + struct.pack(">H", 0x0001) + bytes([0x01, 0x01, 0x02, 0x00])
raw_no_eal = someip_1 + sd_payload_1

# Format 2: WITH entries_array_length (what we tried before)
sd_body_2 = struct.pack(">I", len(sub_entry)) + sub_entry + struct.pack(">I", len(sub_option)) + sub_option
sd_header_2 = bytes([0xC0, 0x00, 0x00, 0x00]) + struct.pack(">I", len(sd_body_2))
sd_payload_2 = sd_header_2 + sd_body_2
someip_2 = struct.pack(">HH", 0xFFFF, 0x8100) + struct.pack(">I", len(sd_payload_2))
someip_2 += struct.pack(">H", 0x7001) + struct.pack(">H", 0x0001) + bytes([0x01, 0x01, 0x02, 0x00])
raw_with_eal = someip_2 + sd_payload_2

print(f"\nFormat 1 (NO entries_array_length, {len(raw_no_eal)} bytes):")
for row in range(0, len(raw_no_eal), 16):
    hx = " ".join(f"{b:02X}" for b in raw_no_eal[row:row+16])
    print(f"  {row:04X}: {hx}")

print(f"\nFormat 2 (WITH entries_array_length, {len(raw_with_eal)} bytes):")
for row in range(0, len(raw_with_eal), 16):
    hx = " ".join(f"{b:02X}" for b in raw_with_eal[row:row+16])
    print(f"  {row:04X}: {hx}")

# Compare SD portions
print(f"\n=== SD Comparison ===")
icc_sd = raw[16:]
f1_sd = raw_no_eal[16:]
f2_sd = raw_with_eal[16:]
scapy_sd = our_bytes[16:]

print(f"ICC SD first 16:  {' '.join(f'{b:02X}' for b in icc_sd[:16])}")
print(f"F1  SD first 16:  {' '.join(f'{b:02X}' for b in f1_sd[:16])}")
print(f"F2  SD first 16:  {' '.join(f'{b:02X}' for b in f2_sd[:16])}")
print(f"Scapy SD first 16:{' '.join(f'{b:02X}' for b in scapy_sd[:16])}")

# Check: does ICC use entries_array_length?
print(f"\n=== Key Question: Does ICC use entries_array_length? ===")
# If YES: sd[8:12] = entries_array_length, first entry type at sd[12]
# If NO: first entry type at sd[8]
print(f"  If NO eal: first entry type = 0x{icc_sd[8]:02X} (should be 0x01 or 0x07 for Offer)")
print(f"  If YES eal: entries_array_length = {struct.unpack('>I', icc_sd[8:12])[0]}, first entry type = 0x{icc_sd[12]:02X}")
