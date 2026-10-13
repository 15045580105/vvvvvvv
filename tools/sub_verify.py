#!/usr/bin/env python3
"""Verify: send SubscribeEventGroup and capture ALL VLAN 62 traffic to see if anything comes back."""
import sys, time, threading
sys.path.insert(0, r"d:\VCC")
OUT = r"d:\VCC\tools\sub_verify_result.txt"

from scapy.all import conf
conf.sniff_promisc = False
from scapy.layers.l2 import Ether, Dot1Q
from scapy.layers.inet import IP, UDP, TCP
from scapy.sendrecv import sendp, sniff
from scapy.arch import get_if_list, get_if_addr, get_if_hwaddr
from scapy.contrib.automotive.someip import (
    SOMEIP, SD as SOMEIP_SD, SDEntry_Service, SDEntry_EventGroup, SDOption_IP4_EndPoint,
)

LOCAL_IP = "192.168.62.5"
TARGET_IP = "192.168.62.31"
VLAN_ID = 62
SD_MCAST = "239.0.0.255"
SD_PORT = 30490
CLIENT_ID = 0x7001

iface = None
local_mac = None
target_mac = "02:51:52:00:00:1f"
for i in get_if_list():
    try:
        a = get_if_addr(i)
        if a.startswith("192.168.62."):
            iface = i
            local_mac = get_if_hwaddr(i)
            LOCAL_IP = a
            break
    except:
        pass

out = []
def log(m):
    out.append(str(m))

log(f"iface={iface} mac={local_mac} ip={LOCAL_IP}")
log(f"target_mac={target_mac}")

# Capture ALL packets for 15s
all_pkts = []
def capture():
    pkts = sniff(iface=iface, store=True, timeout=15, filter="vlan")
    all_pkts.extend(pkts)

t = threading.Thread(target=capture, daemon=True)
t.start()
time.sleep(1)

# Send SubscribeEventGroup
import random
for i in range(3):
    client_port = 40000 + i
    option = SDOption_IP4_EndPoint(type=0x04, addr=LOCAL_IP, l4_proto=0x11, port=client_port)
    entry = SDEntry_EventGroup(
        type=0x06, srv_id=0xA994, inst_id=0xFFFF,
        major_ver=0xFF, ttl=3, cnt=i, eventgroup_id=0x0001,
    )
    entry.index_1 = 0
    entry.n_opt_1 = 1
    sd = SOMEIP_SD(flags=0x80, entry_array=[entry], option_array=[option])
    someip_pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=CLIENT_ID,
                        session_id=i+1, msg_type=0x02) / sd
    pkt = (Ether(src=local_mac, dst=target_mac) /
           Dot1Q(vlan=VLAN_ID) /
           IP(src=LOCAL_IP, dst=TARGET_IP) /
           UDP(sport=client_port, dport=SD_PORT) /
           someip_pkt)
    sendp(pkt, iface=iface, verbose=False)
    log(f"TX Subscribe #{i+1}: sport={client_port} dport={SD_PORT} dst_mac={target_mac} len={len(bytes(pkt))}")
    time.sleep(0.5)

# Also try sending to broadcast MAC
for i in range(2):
    client_port = 40100 + i
    option = SDOption_IP4_EndPoint(type=0x04, addr=LOCAL_IP, l4_proto=0x11, port=client_port)
    entry = SDEntry_EventGroup(
        type=0x06, srv_id=0xA994, inst_id=0xFFFF,
        major_ver=0xFF, ttl=3, cnt=10+i, eventgroup_id=0x0001,
    )
    entry.index_1 = 0
    entry.n_opt_1 = 1
    sd = SOMEIP_SD(flags=0x80, entry_array=[entry], option_array=[option])
    someip_pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=CLIENT_ID,
                        session_id=10+i, msg_type=0x02) / sd
    pkt = (Ether(src=local_mac, dst="ff:ff:ff:ff:ff:ff") /
           Dot1Q(vlan=VLAN_ID) /
           IP(src=LOCAL_IP, dst=TARGET_IP) /
           UDP(sport=client_port, dport=SD_PORT) /
           someip_pkt)
    sendp(pkt, iface=iface, verbose=False)
    log(f"TX Subscribe(bcast) #{i+1}: sport={client_port} dport={SD_PORT} dst_mac=ff:ff:ff:ff:ff:ff len={len(bytes(pkt))}")
    time.sleep(0.5)

t.join(timeout=15)

log(f"\nCaptured {len(all_pkts)} VLAN packets")
from_us = 0
from_icc = 0
for p in all_pkts:
    if Dot1Q not in p:
        continue
    vid = p[Dot1Q].vlan
    src_ip = p[IP].src if IP in p else "?"
    dst_ip = p[IP].dst if IP in p else "?"
    sport = p[UDP].sport if UDP in p else (p[TCP].sport if TCP in p else "?")
    dport = p[UDP].dport if UDP in p else (p[TCP].dport if TCP in p else "?")
    direction = "TX" if src_ip == LOCAL_IP else "RX"
    if src_ip == LOCAL_IP:
        from_us += 1
    elif src_ip == TARGET_IP:
        from_icc += 1
    log(f"  {direction} VLAN={vid} {src_ip}:{sport} -> {dst_ip}:{dport}")

log(f"\nFrom us: {from_us}, From ICC: {from_icc}")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
