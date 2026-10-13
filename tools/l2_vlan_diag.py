#!/usr/bin/env python3
"""L2 抓包诊断: 用 Scapy 直接在网卡层捕获 VLAN  tagged SD 报文。"""
import sys, time, struct, socket
sys.path.insert(0, r"d:\VCC")

from scapy.all import conf, sniff
from scapy.layers.l2 import Ether, Dot1Q
from scapy.layers.inet import IP, UDP
from scapy.contrib.automotive.someip import SOMEIP, SD as SOMEIP_SD, SDEntry_Service, SDOption_IP4_EndPoint
from scapy.arch import get_if_list, get_if_addr

print("=" * 60)
print("  L2 VLAN 抓包诊断")
print("=" * 60)

# 1. 列出所有接口
print(f"\n[1] 可用网络接口:")
for iface in get_if_list():
    try:
        addr = get_if_addr(iface)
        print(f"  {iface} -> {addr}")
    except:
        print(f"  {iface} -> (no IP)")

# 2. 找到 192.168.62.x 对应的接口
target_iface = None
for iface in get_if_list():
    try:
        addr = get_if_addr(iface)
        if addr.startswith("192.168.62."):
            target_iface = iface
            print(f"\n[2] 找到 192.168.62.x 接口: {iface} ({addr})")
            break
    except:
        pass

if not target_iface:
    print("\n[2] 未找到 192.168.62.x 接口，尝试所有接口...")

# 3. 用 Scapy 抓包 15 秒，看能否捕获 VLAN tagged SD 报文
print(f"\n[3] Scapy L2 抓包 (15秒) ...")
print(f"    接口: {target_iface or 'all'}")
print(f"    过滤: UDP port 30490 or 30500\n")

vlan_packets = []
sd_packets = []
all_captured = []

def packet_handler(pkt):
    all_captured.append(pkt)
    
    # 检查是否有 VLAN tag
    has_vlan = Dot1Q in pkt
    vlan_id = pkt[Dot1Q].vlan if has_vlan else None
    
    # 检查是否有 UDP
    if UDP not in pkt:
        return
    
    src_ip = pkt[IP].src if IP in pkt else "?"
    dst_ip = pkt[IP].dst if IP in pkt else "?"
    sport = pkt[UDP].sport
    dport = pkt[UDP].dport
    
    # 尝试解析 SOMEIP
    try:
        udp_payload = bytes(pkt[UDP].payload)
        if len(udp_payload) < 16:
            return
        someip_pkt = SOMEIP(udp_payload)
        
        is_sd = someip_pkt.srv_id == 0xFFFF and someip_pkt.sub_id == 0x8100
        tag_info = f"VLAN={vlan_id}" if has_vlan else "NoVLAN"
        
        if is_sd:
            sd_packets.append((pkt, someip_pkt, vlan_id))
            # 解析 SD entries
            try:
                if isinstance(someip_pkt.payload, SOMEIP_SD):
                    sd_payload = someip_pkt.payload
                elif hasattr(someip_pkt.payload, 'load'):
                    sd_payload = SOMEIP_SD(someip_pkt.payload.load)
                else:
                    sd_payload = None
                
                if sd_payload:
                    for entry in sd_payload.entry_array:
                        if entry.type == 0x01:  # OfferService
                            eps_tcp, eps_udp = [], []
                            for opt in sd_payload.option_array:
                                if isinstance(opt, SDOption_IP4_EndPoint):
                                    ep = (opt.addr, opt.port)
                                    if opt.l4_proto == 0x06:
                                        eps_tcp.append(ep)
                                    elif opt.l4_proto == 0x11:
                                        eps_udp.append(ep)
                            print(f"  [SD-Offer] {src_ip} -> {dst_ip} {tag_info} "
                                  f"Srv=0x{int(entry.srv_id):04X} UDP={eps_udp} TCP={eps_tcp}")
                        elif entry.type == 0x00:  # FindService
                            print(f"  [SD-Find]  {src_ip} -> {dst_ip} {tag_info} "
                                  f"Srv=0x{int(entry.srv_id):04X}")
                else:
                    print(f"  [SD] {src_ip} -> {dst_ip} {tag_info} (parse failed)")
            except Exception as e:
                print(f"  [SD] {src_ip} -> {dst_ip} {tag_info} (error: {e})")
        else:
            print(f"  [SOMEIP] {src_ip}:{sport} -> {dst_ip}:{dport} {tag_info} "
                  f"Srv=0x{someip_pkt.srv_id:04X} Method=0x{someip_pkt.sub_id:04X} "
                  f"Type=0x{someip_pkt.msg_type:02X}")
    except:
        pass

try:
    sniff(iface=target_iface, prn=packet_handler, store=0, timeout=15,
          filter="udp")
except Exception as e:
    print(f"  抓包出错: {e}")
    # 尝试不过滤
    try:
        print("  尝试无过滤器抓包...")
        sniff(iface=target_iface, prn=packet_handler, store=0, timeout=15)
    except Exception as e2:
        print(f"  仍然失败: {e2}")

print(f"\n{'=' * 60}")
print(f"  抓包统计:")
print(f"    总包数: {len(all_captured)}")
print(f"    SD 包数: {len(sd_packets)}")

# 分析 VLAN 情况
vlan_ids = set()
for pkt, someip_pkt, vid in sd_packets:
    if vid is not None:
        vlan_ids.add(vid)

if vlan_ids:
    print(f"    SD 报文 VLAN IDs: {vlan_ids}")
    print(f"\n  结论: ICC 的 SD 报文带有 VLAN 标签!")
    print(f"  你的网卡驱动需要配置 VLAN {vlan_ids} 虚拟适配器，")
    print(f"  或者使用 Scapy L2 发送/接收带 VLAN 标签的包。")
else:
    if sd_packets:
        print(f"    SD 报文不带 VLAN 标签")
        print(f"  结论: 连通性正常，问题可能在 socket 绑定层")
    else:
        print(f"    未捕获到任何 SD 报文")
        print(f"  可能原因:")
        print(f"    - Scapy 抓包接口不正确")
        print(f"    - Npcap 驱动未安装")
        print(f"    - ICC 当前未发送 SD")

print(f"{'=' * 60}")
