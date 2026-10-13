#!/usr/bin/env python3
"""持续监听 SD 流量 + 反复发送 FindService，诊断连通性问题。"""
import socket
import struct
import time
import sys
import threading

sys.path.insert(0, r"d:\VCC")

from scapy.contrib.automotive.someip import (
    SOMEIP, SD as SOMEIP_SD, SDEntry_Service, SDOption_IP4_EndPoint,
)

LOCAL_IP = "192.168.62.55"
TARGET_IP = "192.168.62.31"
SD_MCAST = "239.71.0.2"
SD_PORT = 30490

print("=" * 60)
print("  SD 持续监听 + FindService 循环测试")
print("  持续时间: 30 秒")
print("=" * 60)

# 创建 SD socket
sd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sd_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sd_sock.settimeout(0.5)
sd_sock.bind(("", SD_PORT))
try:
    membership = socket.inet_aton(SD_MCAST) + socket.inet_aton(LOCAL_IP)
    sd_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
    print(f"已加入组播组 {SD_MCAST}")
except OSError as e:
    print(f"加入组播组失败: {e}")
try:
    sd_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(LOCAL_IP))
except OSError:
    pass

# 也创建一个业务端口监听
biz_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
biz_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
biz_sock.settimeout(0.5)
biz_sock.bind((LOCAL_IP, 30501))  # 客户端端口
print(f"业务监听: {LOCAL_IP}:30501")

all_packets = []
offer_packets = []
sd_responses = []
lock = threading.Lock()
running = True

def recv_loop(sock, label, target_list):
    while running:
        try:
            data, addr = sock.recvfrom(65535)
            with lock:
                target_list.append((time.time(), addr, data))
            try:
                pkt = SOMEIP(data)
                info = f"Srv=0x{pkt.srv_id:04X} Method=0x{pkt.sub_id:04X} Type=0x{pkt.msg_type:02X}"
                if pkt.srv_id == 0xFFFF and pkt.sub_id == 0x8100:
                    # SD packet
                    if isinstance(pkt.payload, SOMEIP_SD):
                        sd_pkt = pkt.payload
                    elif hasattr(pkt.payload, 'load'):
                        try:
                            sd_pkt = SOMEIP_SD(pkt.payload.load)
                        except:
                            sd_pkt = None
                    else:
                        sd_pkt = None

                    if sd_pkt:
                        for entry in sd_pkt.entry_array:
                            if entry.type == 0x00:
                                print(f"  [{label}] {addr} FindService(0x{int(entry.srv_id):04X})")
                            elif entry.type == 0x01:
                                eps_tcp, eps_udp = [], []
                                for opt in sd_pkt.option_array:
                                    if isinstance(opt, SDOption_IP4_EndPoint):
                                        ep = (opt.addr, opt.port)
                                        if opt.l4_proto == 0x06:
                                            eps_tcp.append(ep)
                                        elif opt.l4_proto == 0x11:
                                            eps_udp.append(ep)
                                print(f"  [{label}] {addr} OfferService(0x{int(entry.srv_id):04X}) "
                                      f"UDP={eps_udp} TCP={eps_tcp}")
                            elif entry.type == 0x06:
                                print(f"  [{label}] {addr} SubscribeEventGroup(Srv=0x{int(entry.srv_id):04X})")
                            elif entry.type == 0x07:
                                print(f"  [{label}] {addr} SubscribeAck(Srv=0x{int(entry.srv_id):04X})")
                else:
                    print(f"  [{label}] {addr} {info} len={len(data)}")
            except Exception as e:
                print(f"  [{label}] {addr} raw len={len(data)} (parse error: {e})")
        except socket.timeout:
            continue
        except OSError:
            break

# 启动接收线程
t1 = threading.Thread(target=recv_loop, args=(sd_sock, "SD", all_packets), daemon=True)
t2 = threading.Thread(target=recv_loop, args=(biz_sock, "BIZ", all_packets), daemon=True)
t1.start()
t2.start()

# 循环发送 FindService
def send_find_service():
    sd = SOMEIP_SD(flags=0x80, entry_array=[
        SDEntry_Service(type=0x00, srv_id=0xFFFF, inst_id=0xFFFF, ttl=3)
    ])
    return SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001,
                  session_id=1, msg_type=0x02) / sd

find_pkt = send_find_service()
send_count = 0

print(f"\n开始循环发送 FindService (每 2 秒一次)...")
print(f"同时监听所有 SD 和业务端口流量...\n")

start_time = time.time()
duration = 30.0

while time.time() - start_time < duration:
    # 发送组播 Find
    try:
        sd_sock.sendto(bytes(find_pkt), (SD_MCAST, SD_PORT))
        send_count += 1
    except Exception as e:
        print(f"组播发送失败: {e}")

    # 发送单播 Find 到目标
    try:
        sd_sock.sendto(bytes(find_pkt), (TARGET_IP, SD_PORT))
        send_count += 1
    except Exception as e:
        print(f"单播发送失败: {e}")

    # 每 5 次发送一个特定服务的 Find
    if send_count % 10 == 0:
        for svc_id in [0xA994, 0xAB00, 0xAA02]:
            sd_specific = SOMEIP_SD(flags=0x80, entry_array=[
                SDEntry_Service(type=0x00, srv_id=svc_id, inst_id=0xFFFF, ttl=3)
            ])
            pkt = SOMEIP(srv_id=0xFFFF, sub_id=0x8100, client_id=0x7001,
                         session_id=send_count, msg_type=0x02) / sd_specific
            try:
                sd_sock.sendto(bytes(pkt), (TARGET_IP, SD_PORT))
            except:
                pass

    elapsed = time.time() - start_time
    remaining = duration - elapsed
    if int(elapsed) % 5 == 0 and int(elapsed) > 0 and int(remaining) % 5 == 0:
        with lock:
            print(f"  --- 已运行 {int(elapsed)}s, 剩余 {int(remaining)}s, "
                  f"已发送 {send_count} 包, 收到 {len(all_packets)} 包 ---")

    time.sleep(2.0)

running = False
time.sleep(1)

with lock:
    total = len(all_packets)
    from_self = sum(1 for _, addr, _ in all_packets if addr[0] == LOCAL_IP)
    from_target = sum(1 for _, addr, _ in all_packets if addr[0] == TARGET_IP)
    other = total - from_self - from_target

print(f"\n{'=' * 60}")
print(f"  统计结果 ({duration}s)")
print(f"{'=' * 60}")
print(f"  发送 FindService: {send_count} 次")
print(f"  收到总包数: {total}")
print(f"    来自自己 (回环): {from_self}")
print(f"    来自 {TARGET_IP}: {from_target}")
print(f"    来自其他: {other}")

if from_target == 0:
    print(f"\n  结论: 未收到来自 {TARGET_IP} 的任何回复!")
    print(f"  可能原因:")
    print(f"    1. ICC 设备未运行/未启动 SOME/IP 服务")
    print(f"    2. 网络交换机未配置 VLAN 62 标签转发")
    print(f"    3. ICC 防火墙阻止了来自 {LOCAL_IP} 的请求")
    print(f"    4. 你的网卡 (以太网 6) 发出的包没有 VLAN 62 标签")
    print(f"       但 ICC 期望收到带 VLAN 62 标签的包")
    print(f"\n  建议:")
    print(f"    - 确认 ICC 设备已上电且 SOME/IP 服务已启动")
    print(f"    - 确认网络交换机端口已配置 VLAN 62")
    print(f"    - 在 Windows 设备管理器中为网卡配置 VLAN 62:")
    print(f"      网络适配器 -> Realtek USB GbE -> 属性 -> 高级 -> VLAN")
    print(f"      或创建虚拟适配器: netsh interface ipv4 add interface ...")
else:
    print(f"\n  收到来自 {TARGET_IP} 的 {from_target} 个包!")
    print(f"  连通性正常!")

sd_sock.close()
biz_sock.close()
print(f"\n{'=' * 60}")
