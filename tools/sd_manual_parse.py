#!/usr/bin/env python3
"""Manual parse of ICC SD Offer - correct offset."""
import struct

# ICC SD Offer raw hex (from capture)
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
print(f"Total length: {len(raw)} bytes")

# SOMEIP header (16 bytes)
print("\n=== SOMEIP Header ===")
print(f"  srv_id:     0x{struct.unpack('>H', raw[0:2])[0]:04X}")
print(f"  method_id:  0x{struct.unpack('>H', raw[2:4])[0]:04X}")
print(f"  length:     {struct.unpack('>I', raw[4:8])[0]}")
print(f"  client_id:  0x{struct.unpack('>H', raw[8:10])[0]:04X}")
print(f"  session_id: 0x{struct.unpack('>H', raw[10:12])[0]:04X}")
print(f"  proto_ver:  {raw[12]}")
print(f"  iface_ver:  {raw[13]}")
print(f"  msg_type:   0x{raw[14]:02X}")
print(f"  retcode:    0x{raw[15]:02X}")

# SD payload starts at byte 16
sd = raw[16:]
print(f"\n=== SD Payload ({len(sd)} bytes) ===")
print(f"  SD hex: {' '.join(f'{b:02X}' for b in sd)}")

# SD header
print(f"\n  flags:    0x{sd[0]:02X} (reboot={bool(sd[0]&0x80)} unicast={bool(sd[0]&0x40)})")
print(f"  reserved: {sd[1]:02X} {sd[2]:02X} {sd[3]:02X}")
sd_len = struct.unpack('>I', sd[4:8])[0]
print(f"  sd_len:   {sd_len}")

# Entries array
entries_len = struct.unpack('>I', sd[8:12])[0]
print(f"\n  Entries array length: {entries_len}")

pos = 12
eidx = 0
while pos + 16 <= len(sd) and eidx < 8:
    etype = sd[pos]
    idx1 = sd[pos+1]
    no1 = (sd[pos+2] >> 4) & 0x0F
    no2 = sd[pos+2] & 0x0F
    idx2 = sd[pos+3]
    svc_id = struct.unpack('>H', sd[pos+4:pos+6])[0]
    inst_id = struct.unpack('>H', sd[pos+6:pos+8])[0]
    major = sd[pos+8]
    # TTL is 3 bytes at pos+9..pos+11
    ttl = (sd[pos+9] << 16) | (sd[pos+10] << 8) | sd[pos+11]
    
    if etype == 0x01:  # OfferService
        minor = struct.unpack('>I', sd[pos+12:pos+16])[0]
        print(f"\n  Entry[{eidx}] @ offset {pos}:")
        print(f"    type=0x{etype:02X} (OfferService)")
        print(f"    idx1={idx1} n_opt1={no1} n_opt2={no2} idx2={idx2}")
        print(f"    svc_id=0x{svc_id:04X} inst_id=0x{inst_id:04X}")
        print(f"    major={major} minor={minor} ttl={ttl}")
        pos += 16
    elif etype == 0x06:  # SubscribeEventGroup
        cnt = sd[pos+12]
        eg_id = struct.unpack('>H', sd[pos+14:pos+16])[0]
        print(f"\n  Entry[{eidx}] @ offset {pos}:")
        print(f"    type=0x{etype:02X} (SubscribeEventGroup)")
        print(f"    idx1={idx1} n_opt1={no1} n_opt2={no2} idx2={idx2}")
        print(f"    svc_id=0x{svc_id:04X} inst_id=0x{inst_id:04X}")
        print(f"    major={major} ttl={ttl} cnt={cnt} eg_id=0x{eg_id:04X}")
        pos += 16
    else:
        print(f"\n  Entry[{eidx}] @ offset {pos}: type=0x{etype:02X} (unknown)")
        print(f"    raw: {' '.join(f'{b:02X}' for b in sd[pos:pos+16])}")
        pos += 16
    eidx += 1

# Options array
if pos + 4 <= len(sd):
    opt_len = struct.unpack('>I', sd[pos:pos+4])[0]
    print(f"\n  Options array length: {opt_len}")
    op = pos + 4
    oidx = 0
    while op + 12 <= len(sd) and oidx < 8:
        ot = sd[op]
        olen = struct.unpack('>H', sd[op+2:op+4])[0]
        if ot in (0x04, 0x06):
            addr = ".".join(str(b) for b in sd[op+4:op+8])
            l4 = sd[op+8]
            pt = struct.unpack('>H', sd[op+10:op+12])[0]
            pn = {0x06:"TCP",0x11:"UDP"}.get(l4,f"0x{l4:02X}")
            tn = "SubEP" if ot == 0x06 else "EP"
            print(f"  Option[{oidx}] @ offset {op}: {tn} {addr}:{pt} {pn}")
            op += 12
        else:
            print(f"  Option[{oidx}] @ offset {op}: type=0x{ot:02X} len={olen}")
            op += 12
        oidx += 1

# Now compare with our Subscribe
print("\n\n=== Our Subscribe ===")
our_hex = (
    "FF FF 81 00 00 00 00 30 70 01 00 01 01 01 02 00"
    "80 00 00 00 00 00 00 10 06 00 00 10 A9 94 FF FF"
    "FF 00 00 03 00 00 00 01 00 00 00 0C 00 09 04 00"
    "C0 A8 3E 05 00 11 9C 40"
)
our = bytes.fromhex(our_hex.replace(" ", ""))
print(f"Total length: {len(our)} bytes")

print("\n=== SOMEIP Header ===")
print(f"  srv_id:     0x{struct.unpack('>H', our[0:2])[0]:04X}")
print(f"  method_id:  0x{struct.unpack('>H', our[2:4])[0]:04X}")
print(f"  length:     {struct.unpack('>I', our[4:8])[0]}")
print(f"  client_id:  0x{struct.unpack('>H', our[8:10])[0]:04X}")
print(f"  session_id: 0x{struct.unpack('>H', our[10:12])[0]:04X}")
print(f"  proto_ver:  {our[12]}")
print(f"  iface_ver:  {our[13]}")
print(f"  msg_type:   0x{our[14]:02X}")
print(f"  retcode:    0x{our[15]:02X}")

osd = our[16:]
print(f"\n=== SD Payload ({len(osd)} bytes) ===")
print(f"  SD hex: {' '.join(f'{b:02X}' for b in osd)}")
print(f"  flags:    0x{osd[0]:02X}")
print(f"  reserved: {osd[1]:02X} {osd[2]:02X} {osd[3]:02X}")
osd_len = struct.unpack('>I', osd[4:8])[0]
print(f"  sd_len:   {osd_len}")
oentries_len = struct.unpack('>I', osd[8:12])[0]
print(f"  Entries array length: {oentries_len}")

# Our entry
pos = 12
etype = osd[pos]
idx1 = osd[pos+1]
no1 = (osd[pos+2] >> 4) & 0x0F
no2 = osd[pos+2] & 0x0F
idx2 = osd[pos+3]
svc_id = struct.unpack('>H', osd[pos+4:pos+6])[0]
inst_id = struct.unpack('>H', osd[pos+6:pos+8])[0]
major = osd[pos+8]
ttl = (osd[pos+9] << 16) | (osd[pos+10] << 8) | osd[pos+11]
cnt = osd[pos+12]
eg_id = struct.unpack('>H', osd[pos+14:pos+16])[0]
print(f"\n  Entry[0] @ offset {pos}:")
print(f"    type=0x{etype:02X} (SubscribeEventGroup)")
print(f"    idx1={idx1} n_opt1={no1} n_opt2={no2} idx2={idx2}")
print(f"    svc_id=0x{svc_id:04X} inst_id=0x{inst_id:04X}")
print(f"    major={major} ttl={ttl} cnt={cnt} eg_id=0x{eg_id:04X}")

# Compare headers
print("\n\n=== HEADER COMPARISON ===")
print(f"ICC:  {' '.join(f'{b:02X}' for b in raw[:16])}")
print(f"Our:  {' '.join(f'{b:02X}' for b in our[:16])}")
print()
labels = ["srv_id_h","srv_id_l","mth_id_h","mth_id_l","len3","len2","len1","len0","cli_h","cli_l","ses_h","ses_l","proto","iface","type","ret"]
for i in range(16):
    mark = " <<<" if raw[i] != our[i] else ""
    print(f"  Byte {i:2d} ({labels[i]:>8s}): ICC=0x{raw[i]:02X} Our=0x{our[i]:02X}{mark}")
