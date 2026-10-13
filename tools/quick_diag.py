#!/usr/bin/env python3
"""快速诊断: 检查所有接口上的 SD 流量 + ping + ARP"""
import socket, time, sys, subprocess
sys.path.insert(0, r"d:\VCC")
from scapy.contrib.automotive.someip import SOMEIP, SD as SOMEIP_SD, SDEntry_Service

LOCAL_IP = "192.168.62.55"
TARGET_IP = "192.168.62.31"

print("=" * 60)
print("  快速连通性诊断")
print("=" * 60)

# 1. Ping
print(f"\n[1] Ping {TARGET_IP} ...")
r = subprocess.run(["ping", "-n", "2", "-w", "1000", TARGET_IP], capture_output=True, text=True, timeout=10)
ping_ok = r.returncode == 0
print(f"  {'成功' if ping_ok else '失败'}")

# 2. ARP
print(f"\n[2] ARP 表:")
r = subprocess.run(["arp", "-a", "-N", LOCAL_IP], capture_output=True, text=True, timeout=5)
for line in r.stdout.splitlines():
    if "192.168.62" in line:
        print(f"  {line.strip()}")

# 3. 监听 SD 并发送 FindService
print(f"\n[3] 监听 SD 端口 30490 (10秒) + 发送 FindService ...")
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.settimeout(0.5)
s.bind(("", 30490))
try:
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                 socket.inet_aton("239.71.0.2") + socket.inet_aton(LOCAL_IP))
except: pass
try:
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(LOCAL_IP))
except: pass

# 发送 FindService
sd = SOMEIP_SD(flags=0x80, entry_array=[
    SDEntry_Service(type=0x00, srv_id=0xFFFF, inst_id=0xFFFF, ttl=3)
])
find_pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001, session_id=1, msg_type=0x02) / sd

# 发3次
for i in range(3):
    s.sendto(bytes(find_pkt), ("239.71.0.2", 30490))
    s.sendto(bytes(find_pkt), (TARGET_IP, 30490))
    time.sleep(0.5)

count = 0
from_target = 0
deadline = time.time() + 10
while time.time() < deadline:
    try:
        data, addr = s.recvfrom(65535)
        count += 1
        try:
            pkt = SOMEIP(data)
            is_sd = pkt.srv_id == 0xFFFF and pkt.sub_id == 0x8100
            tag = "SD" if is_sd else f"Srv=0x{pkt.srv_id:04X}"
            print(f"  包#{count}: {addr} {tag} Type=0x{pkt.msg_type:02X}")
            if addr[0] == TARGET_IP:
                from_target += 1
        except:
            print(f"  包#{count}: {addr} raw {len(data)}B")
    except socket.timeout:
        pass
s.close()

print(f"\n  总计: {count} 包, 来自 {TARGET_IP}: {from_target} 包")

# 4. 直接 UDP 探测
print(f"\n[4] UDP 探测 {TARGET_IP}:30500 ...")
s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s2.settimeout(3.0)
s2.bind((LOCAL_IP, 31234))
req = SOMEIP(srv_id=0xA994, sub_id=0x0001, client_id=0x7001, session_id=1, msg_type=0x00) / b'\x00'
s2.sendto(bytes(req), (TARGET_IP, 30500))
try:
    data, addr = s2.recvfrom(65535)
    resp = SOMEIP(data)
    print(f"  收到回复! from {addr} Type=0x{resp.msg_type:02X} Payload={bytes(resp.payload).hex()}")
except socket.timeout:
    print(f"  超时")
s2.close()

# 5. 结论
print(f"\n{'=' * 60}")
if from_target > 0:
    print(f"  连通性 OK! 收到来自 {TARGET_IP} 的 {from_target} 个包")
else:
    print(f"  连通性 FAIL! {TARGET_IP} 无任何回复")
    print(f"\n  请确认:")
    print(f"  1. ICC 设备已上电且 SOME/IP 服务已启动")
    print(f"  2. 交换机端口已配置 VLAN 62")
    print(f"  3. Windows 防火墙未阻止端口 30490/30500")
print(f"{'=' * 60}")
