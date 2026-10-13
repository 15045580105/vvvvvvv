#!/usr/bin/env python3
"""快速诊断: 在 L2 层扫描所有 192.168.62.x 接口，寻找 ICC VLAN 62 SD 报文。"""

import threading
import time
from scapy.all import (
    get_if_list, get_if_addr, get_if_hwaddr,
    sniff, Ether, Dot1Q, IP, UDP, TCP, SOMEIP, conf,
)

VLAN_ID = 62
results = {}
lock = threading.Lock()

def sniff_iface(iface, addr, duration=8.0):
    """在指定接口上抓包 duration 秒，统计 VLAN-tagged 包。"""
    count = {"vlan": 0, "sd": 0, "total": 0, "services": set()}

    def handler(pkt):
        count["total"] += 1
        if Dot1Q in pkt and pkt[Dot1Q].vlan == VLAN_ID:
            count["vlan"] += 1
            if IP in pkt:
                src_ip = pkt[IP].src
                if src_ip != addr:
                    # 尝试解析 SOMEIP
                    payload = None
                    if UDP in pkt:
                        payload = bytes(pkt[UDP].payload)
                    elif TCP in pkt:
                        payload = bytes(pkt[TCP].payload)
                    if payload and len(payload) >= 16:
                        try:
                            sip = SOMEIP(payload)
                            if sip.srv_id == 0xFFFF and sip.sub_id == 0x8100:
                                count["sd"] += 1
                                # 解析 SD entry
                                sd_load = bytes(sip.payload) if hasattr(sip.payload, '__bytes__') else getattr(sip.payload, 'load', b'')
                                if sd_load:
                                    # 简单提取 service ID from SD entry (offset 8+4=12 from SD start)
                                    if len(sd_load) >= 16:
                                        svc = (sd_load[12] << 8) | sd_load[13]
                                        count["services"].add(svc)
                        except Exception:
                            pass

    print(f"  [{iface[-8:]}] {addr} - 开始监听 {duration}s ...")
    try:
        sniff(iface=iface, prn=handler, store=0, timeout=duration)
    except Exception as e:
        print(f"  [{iface[-8:]}] {addr} - 抓包异常: {e}")

    with lock:
        results[addr] = count

# 扫描所有 192.168.62.x 接口
targets = []
for iface in get_if_list():
    try:
        addr = get_if_addr(iface)
        if addr.startswith("192.168.62."):
            mac = get_if_hwaddr(iface)
            targets.append((iface, addr, mac))
    except Exception:
        pass

print("=" * 60)
print(f"  ICC VLAN {VLAN_ID} L2 扫描诊断")
print(f"  发现 {len(targets)} 个 192.168.62.x 接口:")
for iface, addr, mac in targets:
    print(f"    {addr} ({mac}) [{iface[-8:]}]")
print("=" * 60)

# 并行抓包
threads = []
for iface, addr, mac in targets:
    t = threading.Thread(target=sniff_iface, args=(iface, addr, 8.0))
    threads.append(t)
    t.start()

for t in threads:
    t.join()

# 输出结果
print("\n" + "=" * 60)
print("  扫描结果")
print("=" * 60)
best_iface = None
best_count = 0
for iface, addr, mac in targets:
    r = results.get(addr, {"total": 0, "vlan": 0, "sd": 0, "services": set()})
    print(f"  {addr}:")
    print(f"    总包数: {r['total']}, VLAN-{VLAN_ID}包: {r['vlan']}, SD Offer: {r['sd']}")
    if r["services"]:
        svcs = ", ".join(f"0x{s:04X}" for s in sorted(r["services"]))
        print(f"    发现的 Service ID: {svcs}")
    if r["sd"] > best_count:
        best_count = r["sd"]
        best_iface = (iface, addr, mac)

if best_iface:
    print(f"\n  >>> 推荐使用接口: {best_iface[1]} ({best_iface[2]})")
else:
    print(f"\n  >>> 未在任何接口上发现 ICC SD 报文!")
    print(f"  >>> 请检查:")
    print(f"      1. ICC 设备是否已上电并正常工作")
    print(f"      2. 网线是否连接到正确的网口")
    print(f"      3. 交换机 VLAN 配置是否正确")
print("=" * 60)
