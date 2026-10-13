#!/usr/bin/env python3
"""基础网络诊断: 检查 VLAN 适配器、SD 监听、UDP 连通性。"""
import socket
import struct
import time
import sys
import subprocess

sys.path.insert(0, r"d:\VCC")

from scapy.contrib.automotive.someip import (
    SOMEIP, SD as SOMEIP_SD, SDEntry_Service, SDOption_IP4_EndPoint,
)

LOCAL_IP = "192.168.62.55"
TARGET_IP = "192.168.62.31"
SD_MCAST = "239.71.0.2"
SD_PORT = 30490
BIZ_PORT = 30500

print("=" * 60)
print("  基础网络诊断")
print("=" * 60)

# 1. Ping 测试
print(f"\n[1] Ping {TARGET_IP} ...")
ret = subprocess.run(["ping", "-n", "2", "-w", "1000", TARGET_IP],
                     capture_output=True, text=True, timeout=10)
print(ret.stdout[-500:] if len(ret.stdout) > 500 else ret.stdout)
ping_ok = ret.returncode == 0
print(f"  Ping {'成功' if ping_ok else '失败'}")

# 2. 监听 SD 组播 (被动等待 5 秒，看能否收到 ICC 的 Offer)
print(f"\n[2] 监听 SD 组播 {SD_MCAST}:{SD_PORT} (5秒)...")
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.settimeout(1.0)
s.bind(("", SD_PORT))
try:
    membership = socket.inet_aton(SD_MCAST) + socket.inet_aton(LOCAL_IP)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
    print(f"  已加入组播组 {SD_MCAST}")
except OSError as e:
    print(f"  加入组播组失败: {e}")

sd_packets = []
deadline = time.time() + 5.0
while time.time() < deadline:
    try:
        data, addr = s.recvfrom(65535)
        try:
            pkt = SOMEIP(data)
            if pkt.srv_id == 0xFFFF and pkt.sub_id == 0x8100:
                sd_packets.append((addr, data))
                print(f"  收到 SD 包: from {addr} len={len(data)}")
        except:
            print(f"  收到非 SOMEIP 包: from {addr} len={len(data)}")
    except socket.timeout:
        pass
s.close()
print(f"  共收到 {len(sd_packets)} 个 SD 包")

# 3. 发送 FindService 并监听回复
print(f"\n[3] 发送 FindService 到组播 {SD_MCAST}:{SD_PORT} 并监听回复...")
s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s2.settimeout(1.0)
s2.bind((LOCAL_IP, SD_PORT))
try:
    membership = socket.inet_aton(SD_MCAST) + socket.inet_aton(LOCAL_IP)
    s2.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
except OSError:
    pass
try:
    s2.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(LOCAL_IP))
except OSError:
    pass

# 构建 FindService for 0xFFFF (通配)
sd = SOMEIP_SD(flags=0x80, entry_array=[
    SDEntry_Service(type=0x00, srv_id=0xFFFF, inst_id=0xFFFF, ttl=3)
])
find_pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001,
                  session_id=1, msg_type=0x02) / sd

s2.sendto(bytes(find_pkt), (SD_MCAST, SD_PORT))
print(f"  已发送 FindService(0xFFFF) -> {SD_MCAST}:{SD_PORT}")

# 也发送单播到目标
s2.sendto(bytes(find_pkt), (TARGET_IP, SD_PORT))
print(f"  已发送 FindService(0xFFFF) -> {TARGET_IP}:{SD_PORT} (单播)")

# 等待回复
responses = []
deadline = time.time() + 5.0
while time.time() < deadline:
    try:
        data, addr = s2.recvfrom(65535)
        try:
            pkt = SOMEIP(data)
            if pkt.srv_id == 0xFFFF and pkt.sub_id == 0x8100:
                responses.append((addr, data))
                print(f"  收到 SD 回复: from {addr} len={len(data)}")
                # 解析 SD
                if isinstance(pkt.payload, SOMEIP_SD):
                    sd_pkt = pkt.payload
                elif hasattr(pkt.payload, 'load'):
                    try:
                        sd_pkt = SOMEIP_SD(pkt.payload.load)
                    except:
                        continue
                else:
                    continue
                for entry in sd_pkt.entry_array:
                    if entry.type == 0x01:
                        print(f"    OfferService: Srv=0x{int(entry.srv_id):04X} "
                              f"Inst=0x{int(getattr(entry, 'inst_id', 0)):04X}")
        except:
            pass
    except socket.timeout:
        pass
s2.close()
print(f"  共收到 {len(responses)} 个回复")

# 4. 直接 UDP 连通性测试 (发到业务端口)
print(f"\n[4] 直接 UDP 测试 -> {TARGET_IP}:{BIZ_PORT}")
s3 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s3.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s3.settimeout(3.0)
s3.bind((LOCAL_IP, 31000))

# 发送一个简单的 SOME/IP Request
req = SOMEIP(srv_id=0xA994, sub_id=0x0001, client_id=0x7001,
             session_id=1, msg_type=0x00, retcode=0x00) / b'\x00'
s3.sendto(bytes(req), (TARGET_IP, BIZ_PORT))
print(f"  已发送 SOMEIP Request (Service=0xA994, Method=0x0001)")

try:
    data, addr = s3.recvfrom(65535)
    resp = SOMEIP(data)
    print(f"  收到回复: from {addr} Srv=0x{resp.srv_id:04X} "
          f"Method=0x{resp.sub_id:04X} Type=0x{resp.msg_type:02X}")
    print(f"  Payload: {bytes(resp.payload).hex()}")
except socket.timeout:
    print(f"  超时 - 未收到回复")
except Exception as e:
    print(f"  错误: {e}")
s3.close()

# 5. 检查 ARP 表
print(f"\n[5] ARP 表 (192.168.62.*):")
ret = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5)
for line in ret.stdout.splitlines():
    if "192.168.62" in line:
        print(f"  {line.strip()}")

# 6. 路由表
print(f"\n[6] 路由表 (192.168.62.*):")
ret = subprocess.run(["route", "print", "192.168.62.*"], capture_output=True, text=True, timeout=5)
for line in ret.stdout.splitlines():
    if "192.168.62" in line:
        print(f"  {line.strip()}")

print(f"\n{'=' * 60}")
print("  诊断完成")
print(f"{'=' * 60}")
