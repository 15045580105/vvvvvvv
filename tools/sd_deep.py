#!/usr/bin/env python3
"""Deep analysis of ICC SD Offer structure."""
import struct

raw_hex = (
    "FF FF 81 00 00 00 00 5C 00 00 07 11 01 01 02 00"
    "C0 00 00 00 00 00 00 30 01 00 00 20 A9 94 00 01"
    "01 00 00 03 00 00 00 01 01 00 00 10 A9 95 00 01"
    "01 00 00 03 00 00 00 01 01 00 00 20 AC 0C 00 01"
    "01 00 00 03 00 00 00 01 00 00 00 18 00 09 04 00"
    "C0 A8 3E 1F 00 11 77 24 00 09 04 00 C0 A8 3E 1F"
    "00 06 77 24"
)
raw = bytes.fromhex(raw_hex.replace(" ", ""))
sd = raw[16:]  # SD payload after SOMEIP header

print("=== ICC SD Offer Analysis ===")
print(f"SD payload ({len(sd)} bytes):")
for row in range(0, len(sd), 16):
    hx = " ".join(f"{b:02X}" for b in sd[row:row+16])
    print(f"  {row:3d}: {hx}")

print(f"\nByte 0: flags = 0x{sd[0]:02X}")
print(f"Bytes 1-3: reserved = {sd[1]:02X} {sd[2]:02X} {sd[3]:02X}")

# Try different interpretations of the length field
for name, offset in [("bytes 4-7", 4), ("bytes 8-11", 8)]:
    val = struct.unpack('>I', sd[offset:offset+4])[0]
    print(f"\nIf length at {name}: value = {val} (0x{val:08X})")

# Let me try to parse entries starting at different offsets
print("\n=== Parse entries starting at SD offset 8 ===")
pos = 8
eidx = 0
while pos + 16 <= len(sd) and eidx < 5:
    etype = sd[pos]
    if etype not in (0x01, 0x06, 0x00):
        print(f"  [{eidx}] offset {pos}: type=0x{etype:02X} (not a valid entry, stop)")
        break
    idx1 = sd[pos+1]
    no1 = (sd[pos+2] >> 4) & 0x0F
    no2 = sd[pos+2] & 0x0F
    idx2 = sd[pos+3]
    svc = struct.unpack('>H', sd[pos+4:pos+6])[0]
    inst = struct.unpack('>H', sd[pos+6:pos+8])[0]
    maj = sd[pos+8]
    ttl = (sd[pos+9] << 16) | (sd[pos+10] << 8) | sd[pos+11]
    if etype == 0x01:
        minor = struct.unpack('>I', sd[pos+12:pos+16])[0]
        print(f"  [{eidx}] Offer: svc=0x{svc:04X} inst=0x{inst:04X} maj={maj} min={minor} ttl={ttl} nopt1={no1} nopt2={no2}")
    pos += 16
    eidx += 1

# Now let me check: what does Scapy parse for ICC's SD packet?
print("\n\n=== Scapy parse of ICC SD ===")
import sys
sys.path.insert(0, r"d:\VCC")
from app.common.communication.clients.someip import SOMEIP, SOMEIP_SD

# Build the raw SOMEIP packet as ICC sends it
someip_raw = raw  # full packet including SOMEIP header
icc_pkt = SOMEIP(someip_raw)
print(f"srv_id=0x{icc_pkt.srv_id:04X} sub_id=0x{icc_pkt.sub_id:04X}")
print(f"client_id=0x{icc_pkt.client_id:04X} session_id=0x{icc_pkt.session_id:04X}")
print(f"msg_type=0x{icc_pkt.msg_type:02X}")

if hasattr(icc_pkt, 'payload') and isinstance(icc_pkt.payload, SOMEIP_SD):
    sd_pkt = icc_pkt.payload
    print(f"\nSD flags={sd_pkt.flags}")
    print(f"SD entries: {len(sd_pkt.entry_array)}")
    for i, e in enumerate(sd_pkt.entry_array):
        print(f"  Entry[{i}]: type=0x{e.type:02X} svc=0x{e.srv_id:04X} inst=0x{e.inst_id:04X}")
    print(f"SD options: {len(sd_pkt.option_array)}")
    for i, o in enumerate(sd_pkt.option_array):
        print(f"  Option[{i}]: type=0x{o.type:02X}")
else:
    print(f"Payload type: {type(icc_pkt.payload)}")
    if hasattr(icc_pkt.payload, 'load'):
        sd_raw = icc_pkt.payload.load
        print(f"Raw SD ({len(sd_raw)} bytes): {' '.join(f'{b:02X}' for b in sd_raw[:32])}")
        sd_pkt = SOMEIP_SD(sd_raw)
        print(f"SD flags=0x{sd_pkt.flags:02X}")
        print(f"SD entries: {len(sd_pkt.entry_array)}")
        for i, e in enumerate(sd_pkt.entry_array):
            print(f"  Entry[{i}]: type=0x{e.type:02X} svc=0x{e.srv_id:04X}")

# Now compare with our Subscribe
print("\n\n=== Scapy parse of our Subscribe ===")
our_hex = (
    "FF FF 81 00 00 00 00 30 70 01 00 01 01 01 02 00"
    "80 00 00 00 00 00 00 10 06 00 00 10 A9 94 FF FF"
    "FF 00 00 03 00 00 00 01 00 00 00 0C 00 09 04 00"
    "C0 A8 3E 05 00 11 9C 40"
)
our_raw = bytes.fromhex(our_hex.replace(" ", ""))
our_pkt = SOMEIP(our_raw)
print(f"srv_id=0x{our_pkt.srv_id:04X} sub_id=0x{our_pkt.sub_id:04X}")
print(f"client_id=0x{our_pkt.client_id:04X} session_id=0x{our_pkt.session_id:04X}")

if hasattr(our_pkt, 'payload') and isinstance(our_pkt.payload, SOMEIP_SD):
    osd = our_pkt.payload
    print(f"SD flags={osd.flags}")
    print(f"SD entries: {len(osd.entry_array)}")
    for i, e in enumerate(osd.entry_array):
        print(f"  Entry[{i}]: type=0x{e.type:02X} svc=0x{e.srv_id:04X} eg=0x{getattr(e, 'eventgroup_id', '?')}")
    print(f"SD options: {len(osd.option_array)}")
    for i, o in enumerate(osd.option_array):
        print(f"  Option[{i}]: type=0x{o.type:02X}")

# Now compare raw bytes side by side
print("\n\n=== Raw SD comparison ===")
print(f"ICC SD:  {' '.join(f'{b:02X}' for b in sd)}")

our_sd = our_raw[16:]
print(f"Our SD:  {' '.join(f'{b:02X}' for b in our_sd)}")

# Key differences
print(f"\nICC flags: 0x{sd[0]:02X}  Our flags: 0x{our_sd[0]:02X}")
print(f"ICC entry type: 0x{sd[8]:02X}  Our entry type: 0x{our_sd[8]:02X}")
