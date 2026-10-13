#!/usr/bin/env python3
"""Minimal L2 sniff test."""
import sys
sys.path.insert(0, r"d:\VCC")

from scapy.all import conf
conf.sniff_promisc = False
from scapy.layers.l2 import Dot1Q
from scapy.layers.inet import IP, UDP
from scapy.sendrecv import sniff
from scapy.arch import get_if_list, get_if_addr

iface = None
for i in get_if_list():
    try:
        a = get_if_addr(i)
        if a.startswith("192.168.62."):
            iface = i
            print(f"Found iface={i} ip={a}")
            break
    except:
        pass

if not iface:
    print("No 192.168.62.x iface")
    sys.exit(1)

print("Sniffing 5s ...")
pkts = sniff(iface=iface, store=True, timeout=5, filter="udp")
print(f"Captured {len(pkts)} UDP packets")

vlan_count = 0
for p in pkts[:30]:
    has_vlan = Dot1Q in p
    vid = p[Dot1Q].vlan if has_vlan else None
    src = p[IP].src if IP in p else "?"
    dst = p[IP].dst if IP in p else "?"
    if has_vlan:
        vlan_count += 1
    print(f"  VLAN={vid} {src} -> {dst}")

print(f"\nVLAN tagged: {vlan_count}/{min(len(pkts),30)}")
